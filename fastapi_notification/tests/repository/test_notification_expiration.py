"""SQLite execution tests for expiration visibility and retention cleanup."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from fastapi_notification.identity import IdentityAdapter
from fastapi_notification.models.base import Base
from fastapi_notification.models.content_type import ContentType
from fastapi_notification.models.deleted_notification import DeletedNotification
from fastapi_notification.models.notification import Notification, notification_group
from fastapi_notification.models.notification_recipient import NotificationRecipient
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.settings.conf import configure


class AsyncExecutionAdapter:
    """Provide the async session surface used by DAL helpers over SQLite sync IO."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, statement: Any) -> Any:
        return self.session.execute(statement)

    async def flush(self) -> None:
        self.session.flush()

    async def get(self, model: Any, identifier: Any) -> Any:
        return self.session.get(model, identifier)

    def get_bind(self) -> Any:
        return self.session.get_bind()

    def add(self, instance: Any) -> None:
        self.session.add(instance)


@pytest.mark.asyncio
async def test_expired_direct_and_group_notifications_are_hidden_everywhere() -> None:
    """Inbox, seen/unseen, summary and preview all apply the same expiry rule."""
    configure(IDENTITY_ADAPTER=IdentityAdapter)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    user = SimpleNamespace(id=10)
    cutoff = now - timedelta(seconds=1)

    try:
        with Session(engine) as session:
            content_type = ContentType(app_label="tests", model="actor")
            session.add(content_type)
            session.flush()
            notifications = [
                Notification(
                    verb="expired direct",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=True,
                    expires_at=cutoff,
                ),
                Notification(
                    verb="expired group",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=True,
                    expires_at=cutoff,
                ),
                Notification(
                    verb="active direct",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=True,
                    expires_at=now + timedelta(days=1),
                ),
                Notification(
                    verb="active group",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=True,
                ),
                Notification(
                    verb="expired unsent",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=False,
                    expires_at=cutoff,
                ),
            ]
            session.add_all(notifications)
            session.flush()
            session.add_all(
                [
                    NotificationRecipient(
                        notification_id=notifications[0].id, recipient_id="10"
                    ),
                    NotificationRecipient(
                        notification_id=notifications[2].id, recipient_id="10"
                    ),
                    NotificationSeen(
                        notification_id=notifications[3].id, user_id="10"
                    ),
                ]
            )
            session.execute(
                notification_group.insert().values(
                    [
                        {"notification_id": notifications[1].id, "group_id": "team"},
                        {"notification_id": notifications[3].id, "group_id": "team"},
                        {"notification_id": notifications[4].id, "group_id": "team"},
                    ]
                )
            )
            session.flush()

            dal = NotificationDataAccessLayer(
                AsyncExecutionAdapter(session)  # type: ignore[arg-type]
            )
            visible_statement = dal.sent_statement(
                recipients=user,
                exclude_deleted_by=user,
                groups=["team"],
                display_detail=True,
            )
            visible = session.scalars(visible_statement).all()
            assert {item.id for item in visible} == {
                notifications[2].id,
                notifications[3].id,
            }

            include_expired = dal.sent_statement(
                recipients=user,
                groups=["team"],
                display_detail=True,
                include_expired=True,
            )
            assert notifications[0].id in {
                item.id for item in session.scalars(include_expired).all()
            }

            unsent_statement = dal.unsent_statement(
                recipients=user, groups=["team"], display_detail=True
            )
            assert session.scalars(unsent_statement).all() == []

            summary = await dal.summary(visible_statement, user)
            preview = await dal.preview(visible_statement, user, limit=5)
            assert summary == {
                "total": 2,
                "unread": 1,
                "read": 1,
                "by_category": {
                    "general": {"total": 2, "unread": 1, "read": 1}
                },
                "by_priority": {
                    "normal": {"total": 2, "unread": 1, "read": 1}
                },
            }
            assert {row["id"] for row in preview} == {
                notifications[2].id,
                notifications[3].id,
            }
            assert all("expires_at" in row for row in preview)
            assert all("category" in row and "priority" in row for row in preview)

            # Raw/all queries deliberately retain expired records for audit.
            raw = dal.all_notifications_statement(display_detail=True)
            assert len(session.scalars(raw).all()) == 5
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_expired_notifications_cannot_change_read_state() -> None:
    """Direct model/DAL state changes reject expired notifications."""
    configure(IDENTITY_ADAPTER=IdentityAdapter)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    user = SimpleNamespace(id=10)

    try:
        with Session(engine) as session:
            content_type = ContentType(app_label="tests", model="actor")
            session.add(content_type)
            session.flush()
            notification = Notification(
                verb="expired",
                actor_content_type_id=content_type.id,
                actor_object_id="1",
                is_sent=True,
                expires_at=now - timedelta(seconds=1),
            )
            session.add(notification)
            session.flush()
            session.add(
                NotificationRecipient(
                    notification_id=notification.id, recipient_id="10"
                )
            )
            session.flush()
            adapter = AsyncExecutionAdapter(session)

            with pytest.raises(PermissionError, match="expired"):
                await notification.mark_as_seen(adapter, user)  # type: ignore[arg-type]
            with pytest.raises(PermissionError, match="expired"):
                await notification.mark_as_unseen(
                    adapter, user  # type: ignore[arg-type]
                )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_purge_expired_is_staff_only_retention_aware_and_cascades() -> None:
    """Explicit cleanup honors cutoff/limit and removes dependent state rows."""
    configure(IDENTITY_ADAPTER=IdentityAdapter)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    staff = SimpleNamespace(id=99, is_staff=True)
    regular = SimpleNamespace(id=10, is_staff=False)
    retention_cutoff = now - timedelta(days=30)

    try:
        with Session(engine) as session:
            content_type = ContentType(app_label="tests", model="actor")
            session.add(content_type)
            session.flush()
            notifications = [
                Notification(
                    verb="old expired one",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    expires_at=now - timedelta(days=45),
                ),
                Notification(
                    verb="old expired two",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    expires_at=now - timedelta(days=40),
                ),
                Notification(
                    verb="recently expired",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    expires_at=now - timedelta(days=10),
                ),
                Notification(
                    verb="not expired",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    expires_at=now + timedelta(days=1),
                ),
                Notification(
                    verb="never expires",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                ),
            ]
            session.add_all(notifications)
            session.flush()
            old_id = notifications[0].id
            second_old_id = notifications[1].id
            recent_id = notifications[2].id
            future_id = notifications[3].id
            never_id = notifications[4].id
            session.add_all(
                [
                    NotificationRecipient(notification_id=old_id, recipient_id="10"),
                    NotificationSeen(notification_id=old_id, user_id="10"),
                    DeletedNotification(notification_id=old_id, user_id="10"),
                ]
            )
            session.execute(
                notification_group.insert().values(
                    notification_id=old_id, group_id="team"
                )
            )
            session.flush()

            dal = NotificationDataAccessLayer(
                AsyncExecutionAdapter(session)  # type: ignore[arg-type]
            )
            with pytest.raises(PermissionError, match="Staff permission"):
                await dal.purge_expired(retention_cutoff, actor=regular)

            with pytest.raises(ValueError, match="timezone-aware"):
                await dal.purge_expired(datetime(2026, 11, 1), actor=staff)

            purged = await dal.purge_expired(
                retention_cutoff, limit=1, actor=staff
            )
            assert purged == 1
            session.expire_all()
            assert session.get(Notification, old_id) is None
            assert session.scalar(
                select(func.count()).select_from(NotificationRecipient).where(
                    NotificationRecipient.notification_id == old_id
                )
            ) == 0
            assert session.scalar(
                select(func.count()).select_from(NotificationSeen).where(
                    NotificationSeen.notification_id == old_id
                )
            ) == 0
            assert session.scalar(
                select(func.count()).select_from(DeletedNotification).where(
                    DeletedNotification.notification_id == old_id
                )
            ) == 0
            assert session.scalar(
                select(func.count()).select_from(notification_group).where(
                    notification_group.c.notification_id == old_id
                )
            ) == 0

            # A second batch purges the next old item; recent/future/never-expiring
            # records remain until their own retention cutoff is reached.
            assert await dal.purge_expired(retention_cutoff, limit=1, actor=staff) == 1
            session.expire_all()
            assert session.get(Notification, second_old_id) is None
            assert session.get(Notification, recent_id) is not None
            assert session.get(Notification, future_id) is not None
            assert session.get(Notification, never_id) is not None
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_purge_rejects_future_cutoff_and_invalid_limit() -> None:
    """Cleanup cannot purge notifications that have not expired yet."""
    configure(IDENTITY_ADAPTER=IdentityAdapter)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    staff = SimpleNamespace(id=99, is_staff=True)

    try:
        with Session(engine) as session:
            dal = NotificationDataAccessLayer(
                AsyncExecutionAdapter(session)  # type: ignore[arg-type]
            )
            assert await dal.purge_expired(
                datetime.now(timezone.utc), actor=staff
            ) == 0
            with pytest.raises(ValueError, match="must not be in the future"):
                await dal.purge_expired(
                    datetime.now(timezone.utc) + timedelta(seconds=1), actor=staff
                )
            with pytest.raises(ValueError, match="positive integer"):
                await dal.purge_expired(
                    datetime.now(timezone.utc), limit=0, actor=staff
                )
            with pytest.raises(ValueError, match="positive integer"):
                await dal.purge_expired(
                    datetime.now(timezone.utc),
                    limit=1.5,  # type: ignore[arg-type]
                    actor=staff,
                )
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_dal_can_create_update_and_clear_expiration() -> None:
    """The DAL accepts aware expiry values and can explicitly remove them."""
    configure(IDENTITY_ADAPTER=IdentityAdapter)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    actor = SimpleNamespace(id=1)
    initial_expiry = datetime.now(timezone.utc) + timedelta(days=2)
    updated_expiry = datetime.now(timezone.utc) + timedelta(days=5)

    try:
        with Session(engine) as session:
            dal = NotificationDataAccessLayer(
                AsyncExecutionAdapter(session)  # type: ignore[arg-type]
            )
            notification = await dal.create_notification(
                verb="expires",
                actor=actor,
                expires_at=initial_expiry,
            )
            assert notification.expires_at == initial_expiry
            session.expire(notification, ["expires_at"])
            assert notification.expires_at.utcoffset() == timedelta(0)

            await dal.update_notification(
                notification.id,
                expires_at=updated_expiry,
            )
            assert notification.expires_at == updated_expiry

            await dal.update_notification(
                notification.id,
                clear_expires_at=True,
            )
            assert notification.expires_at is None

            with pytest.raises(ValueError, match="not both"):
                await dal.update_notification(
                    notification.id,
                    expires_at=updated_expiry,
                    clear_expires_at=True,
                )

            with pytest.raises(ValueError, match="timezone-aware"):
                await dal.create_notification(
                    verb="invalid expiry",
                    actor=actor,
                    expires_at=datetime(2026, 11, 2, 12, 0),
                )
    finally:
        engine.dispose()
