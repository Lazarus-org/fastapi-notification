"""Tests for scoped notification creation idempotency."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session

from fastapi_notification.identity import BuiltInIdentityAdapter
from fastapi_notification.models.auth import User
from fastapi_notification.models.base import AuthBase, Base
from fastapi_notification.models.content_type import ContentType
from fastapi_notification.models.deduplication import NotificationDeduplication
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.settings.conf import configure


class AsyncExecutionAdapter:
    """Expose the async session methods used by the DAL over sync SQLite IO."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, statement: Any) -> Any:
        return self.session.execute(statement)

    async def flush(self) -> None:
        self.session.flush()

    async def get(self, model: Any, identifier: Any) -> Any:
        return self.session.get(model, identifier)

    async def delete(self, instance: Any) -> None:
        self.session.delete(instance)

    async def refresh(self, instance: Any, attributes: Any) -> None:
        self.session.refresh(instance, attribute_names=attributes)

    def add(self, instance: Any) -> None:
        self.session.add(instance)

    def add_all(self, instances: Any) -> None:
        self.session.add_all(instances)

    def get_bind(self) -> Any:
        return self.session.get_bind()

    @asynccontextmanager
    async def begin_nested(self) -> Any:
        with self.session.begin_nested():
            yield


@pytest.fixture(autouse=True)
def built_in_identity_adapter() -> None:
    configure(IDENTITY_ADAPTER=BuiltInIdentityAdapter)


def _database() -> Any:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    AuthBase.metadata.create_all(engine)
    return engine


def _dal(session: Session) -> NotificationDataAccessLayer:
    """Bind the DAL to the synchronous test adapter."""
    return NotificationDataAccessLayer(  # type: ignore[arg-type]
        AsyncExecutionAdapter(session)
    )


@pytest.mark.asyncio
async def test_same_active_key_returns_original_notification_unchanged() -> None:
    """A retry returns the first notification without merging its audience."""
    engine = _database()
    try:
        with Session(engine) as session:
            first_user = User(username="first", email="first@example.com")
            second_user = User(username="second", email="second@example.com")
            session.add_all([first_user, second_user])
            session.flush()
            dal = _dal(session)
            first_key_expiry = datetime.now(timezone.utc) + timedelta(hours=1)

            first = await dal.create_notification(
                verb="paid",
                actor=first_user,
                description="original event",
                recipients=first_user,
                is_sent=True,
                deduplication_key="payment:123",
                deduplication_scope="tenant:acme",
                deduplication_key_expires_at=first_key_expiry,
            )
            first_id = first.id
            session.commit()

            retry = await dal.create_notification(
                verb="refunded",
                actor=second_user,
                description="must not overwrite original",
                recipients=second_user,
                is_sent=True,
                deduplication_key="payment:123",
                deduplication_scope="tenant:acme",
                deduplication_key_expires_at=(
                    datetime.now(timezone.utc) + timedelta(hours=2)
                ),
            )
            session.commit()

            assert retry.id == first_id
            assert retry.verb == "paid"
            assert retry.description == "original event"
            assert [item.id for item in retry.recipient] == [first_user.id]
            key_record = session.scalar(select(NotificationDeduplication))
            assert key_record.expires_at == first_key_expiry
            assert session.scalar(select(func.count()).select_from(Notification)) == 1
            assert (
                session.scalar(
                    select(func.count()).select_from(NotificationDeduplication)
                )
                == 1
            )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_same_key_in_different_scopes_creates_separate_notifications() -> None:
    """The scope namespaces keys so independent tenants do not collide."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="scope-user", email="scope@example.com")
            session.add(user)
            session.flush()
            dal = _dal(session)

            first = await dal.create_notification(
                verb="created",
                actor=user,
                deduplication_key="event-1",
                deduplication_scope="tenant:a",
            )
            second = await dal.create_notification(
                verb="created",
                actor=user,
                deduplication_key="event-1",
                deduplication_scope="tenant:b",
            )
            session.commit()

            assert first.id != second.id
            assert session.scalar(select(func.count()).select_from(Notification)) == 2
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_expired_key_can_be_reused_without_changing_old_notification() -> None:
    """An elapsed key can be claimed by a new event while the old row remains."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="expiry-user", email="expiry@example.com")
            session.add(user)
            session.flush()
            dal = _dal(session)

            first = await dal.create_notification(
                verb="first event",
                actor=user,
                deduplication_key="order:77",
                deduplication_scope="orders",
                deduplication_key_expires_at=datetime.now(timezone.utc)
                + timedelta(hours=1),
            )
            first_id = first.id
            session.execute(
                update(NotificationDeduplication)
                .where(NotificationDeduplication.notification_id == first_id)
                .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
            )
            session.flush()

            second = await dal.create_notification(
                verb="second event",
                actor=user,
                deduplication_key="order:77",
                deduplication_scope="orders",
            )
            session.commit()

            assert second.id != first_id
            assert session.get(Notification, first_id).verb == "first event"
            key_record = session.scalar(
                select(NotificationDeduplication).where(
                    NotificationDeduplication.scope == "orders",
                    NotificationDeduplication.deduplication_key == "order:77",
                )
            )
            assert key_record.notification_id == second.id
            assert key_record.expires_at is None
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_notification_without_key_is_never_deduplicated() -> None:
    """Omitting a key preserves the original always-create behavior."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="no-key", email="no-key@example.com")
            session.add(user)
            session.flush()
            dal = _dal(session)

            first = await dal.create_notification(verb="event", actor=user)
            second = await dal.create_notification(verb="event", actor=user)
            session.commit()

            assert first.id != second.id
            assert session.scalar(select(func.count()).select_from(Notification)) == 2
            assert (
                session.scalar(
                    select(func.count()).select_from(NotificationDeduplication)
                )
                == 0
            )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_key_expiry_requires_a_key() -> None:
    """A key retention policy cannot be supplied without an idempotency key."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="invalid", email="invalid@example.com")
            session.add(user)
            session.flush()
            dal = _dal(session)

            with pytest.raises(ValueError, match="requires deduplication_key"):
                await dal.create_notification(
                    verb="event",
                    actor=user,
                    deduplication_key_expires_at=datetime.now(timezone.utc)
                    + timedelta(hours=1),
                )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_naive_key_expiry_is_rejected() -> None:
    """Key expiration instants must be timezone-aware."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="naive", email="naive@example.com")
            session.add(user)
            session.flush()
            dal = _dal(session)

            with pytest.raises(ValueError, match="timezone-aware"):
                await dal.create_notification(
                    verb="event",
                    actor=user,
                    deduplication_key="event:1",
                    deduplication_key_expires_at=datetime.now(),
                )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_permanent_deletion_releases_deduplication_key() -> None:
    """Hard deletion removes the ledger row so the key can be claimed again."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="author", email="author@example.com")
            staff = User(
                username="staff", email="staff@example.com", is_staff=True
            )
            session.add_all([user, staff])
            session.flush()
            dal = _dal(session)

            first = await dal.create_notification(
                verb="event",
                actor=user,
                recipients=user,
                is_sent=True,
                deduplication_key="event:delete",
            )
            first_id = first.id
            session.commit()

            await dal.delete_notification(
                first_id, soft_delete=False, actor=staff
            )
            session.commit()
            assert session.get(Notification, first_id) is None
            assert session.scalar(
                select(func.count()).select_from(NotificationDeduplication)
            ) == 0

            replacement = await dal.create_notification(
                verb="event again",
                actor=user,
                deduplication_key="event:delete",
            )
            session.commit()

            # SQLite may reuse a deleted INTEGER PRIMARY KEY, so verify the
            # replacement by content rather than requiring a different ID.
            assert replacement.verb == "event again"
            assert session.scalar(
                select(func.count()).select_from(NotificationDeduplication)
            ) == 1
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_content_type_creation_is_idempotent() -> None:
    """Repeated content-type resolution reuses its natural-key row."""
    engine = _database()
    try:
        with Session(engine) as session:
            first = await ContentType.get_for_model(
                AsyncExecutionAdapter(session), User  # type: ignore[arg-type]
            )
            second = await ContentType.get_for_model(
                AsyncExecutionAdapter(session), User  # type: ignore[arg-type]
            )
            session.commit()
            assert first.id == second.id
            assert session.scalar(select(func.count()).select_from(ContentType)) == 1
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_rollback_removes_notification_and_deduplication_claim() -> None:
    """The ledger follows the caller-owned transaction and rolls back with it."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="rollback", email="rollback@example.com")
            session.add(user)
            session.flush()
            dal = _dal(session)

            await dal.create_notification(
                verb="first attempt",
                actor=user,
                deduplication_key="event:rollback",
            )
            session.rollback()

            assert session.scalar(select(func.count()).select_from(Notification)) == 0
            assert (
                session.scalar(
                    select(func.count()).select_from(NotificationDeduplication)
                )
                == 0
            )

            # The same key can be claimed after the first transaction rolls back.
            replacement = await dal.create_notification(
                verb="retry after rollback",
                actor=user,
                deduplication_key="event:rollback",
            )
            session.commit()
            assert replacement.verb == "retry after rollback"
            assert session.scalar(select(func.count()).select_from(Notification)) == 1
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_expired_notification_purge_releases_its_deduplication_key() -> None:
    """Explicitly purging a notification also removes its idempotency record."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="purge-author", email="purge@example.com")
            staff = User(
                username="purge-staff", email="purge-staff@example.com", is_staff=True
            )
            session.add_all([user, staff])
            session.flush()
            dal = _dal(session)

            old_notification = await dal.create_notification(
                verb="old event",
                actor=user,
                expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                deduplication_key="event:purge",
                deduplication_key_expires_at=datetime.now(timezone.utc)
                + timedelta(days=1),
            )
            old_notification_id = old_notification.id
            session.commit()

            purged = await dal.purge_expired(
                datetime.now(timezone.utc), actor=staff
            )
            assert purged == 1
            session.commit()
            assert session.get(Notification, old_notification_id) is None
            assert session.scalar(
                select(func.count()).select_from(NotificationDeduplication)
            ) == 0

            replacement = await dal.create_notification(
                verb="replacement event",
                actor=user,
                deduplication_key="event:purge",
            )
            session.commit()
            assert replacement.verb == "replacement event"
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_blank_deduplication_key_and_scope_are_rejected() -> None:
    """Blank values cannot silently collapse unrelated business events."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="blank", email="blank@example.com")
            session.add(user)
            session.flush()
            dal = _dal(session)

            with pytest.raises(ValueError, match="deduplication_key"):
                await dal.create_notification(
                    verb="event", actor=user, deduplication_key="   "
                )
            with pytest.raises(ValueError, match="deduplication_scope"):
                await dal.create_notification(
                    verb="event",
                    actor=user,
                    deduplication_key="event:1",
                    deduplication_scope="  ",
                )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_key_expiry_must_be_in_the_future() -> None:
    """Expired keys are reclaimed on retry, not registered as already expired."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="past-expiry", email="past-expiry@example.com")
            session.add(user)
            session.flush()
            dal = _dal(session)

            with pytest.raises(ValueError, match="must be in the future"):
                await dal.create_notification(
                    verb="event",
                    actor=user,
                    deduplication_key="event:past-expiry",
                    deduplication_key_expires_at=(
                        datetime.now(timezone.utc) - timedelta(seconds=1)
                    ),
                )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_bulk_permanent_deletion_releases_deduplication_keys() -> None:
    """Administrative bulk deletion removes every associated key record."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="bulk-author", email="bulk-author@example.com")
            staff = User(
                username="bulk-staff", email="bulk-staff@example.com", is_staff=True
            )
            session.add_all([user, staff])
            session.flush()
            dal = _dal(session)

            await dal.create_notification(
                verb="one",
                actor=user,
                is_sent=True,
                deduplication_key="bulk:one",
            )
            await dal.create_notification(
                verb="two",
                actor=user,
                is_sent=True,
                deduplication_key="bulk:two",
            )
            session.commit()

            deleted = await dal.delete_many(
                dal.sent_statement(display_detail=True), actor=staff
            )
            session.commit()

            assert deleted == 2
            assert session.scalar(
                select(func.count()).select_from(NotificationDeduplication)
            ) == 0
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_orphaned_deduplication_record_is_reclaimed() -> None:
    """A stale ledger row cannot permanently block a key after external deletion."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="orphan", email="orphan@example.com")
            session.add(user)
            session.flush()
            session.add(
                NotificationDeduplication(
                    scope="orphan-test",
                    deduplication_key="event:orphan",
                    notification_id=999999,
                )
            )
            session.flush()
            dal = _dal(session)

            created = await dal.create_notification(
                verb="recovered",
                actor=user,
                deduplication_scope="orphan-test",
                deduplication_key="event:orphan",
            )
            session.commit()

            record = session.scalar(
                select(NotificationDeduplication).where(
                    NotificationDeduplication.scope == "orphan-test",
                    NotificationDeduplication.deduplication_key == "event:orphan",
                )
            )
            assert record.notification_id == created.id
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_deduplication_inputs_reject_invalid_types_and_lengths() -> None:
    """Keys, scopes and expiry values are validated before any write occurs."""
    engine = _database()
    try:
        with Session(engine) as session:
            user = User(username="validation", email="validation@example.com")
            session.add(user)
            session.flush()
            dal = _dal(session)

            with pytest.raises(TypeError, match="deduplication_key must be a string"):
                await dal.create_notification(
                    verb="event", actor=user, deduplication_key=123  # type: ignore[arg-type]
                )
            with pytest.raises(ValueError, match="deduplication_key"):
                await dal.create_notification(
                    verb="event", actor=user, deduplication_key="x" * 256
                )
            with pytest.raises(ValueError, match="deduplication_key"):
                await dal.create_notification(
                    verb="event", actor=user, deduplication_key="bad\x00key"
                )
            with pytest.raises(TypeError, match="deduplication_scope must be a string"):
                await dal.create_notification(
                    verb="event",
                    actor=user,
                    deduplication_key="event:1",
                    deduplication_scope=1,  # type: ignore[arg-type]
                )
            with pytest.raises(ValueError, match="deduplication_scope"):
                await dal.create_notification(
                    verb="event",
                    actor=user,
                    deduplication_key="event:1",
                    deduplication_scope="s" * 256,
                )
            with pytest.raises(TypeError, match="deduplication_key_expires_at"):
                await dal.create_notification(
                    verb="event",
                    actor=user,
                    deduplication_key="event:1",
                    deduplication_key_expires_at="tomorrow",  # type: ignore[arg-type]
                )
    finally:
        engine.dispose()
