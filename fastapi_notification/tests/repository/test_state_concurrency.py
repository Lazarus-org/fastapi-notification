"""Concurrency and transaction-boundary tests for notification state writes."""

import asyncio
from typing import Any, AsyncIterator, Tuple

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastapi_notification.identity import BuiltInIdentityAdapter
from fastapi_notification.models.auth import User
from fastapi_notification.models.base import AuthBase, Base
from fastapi_notification.models.deleted_notification import DeletedNotification
from fastapi_notification.models.notification import Notification
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.models, pytest.mark.managers]


@pytest_asyncio.fixture
async def concurrency_store(
    tmp_path: Any,
    request: Any,
) -> AsyncIterator[Tuple[async_sessionmaker, int, int]]:
    """Create a file-backed SQLite database for independent concurrent sessions."""
    database_path = tmp_path / "notification-concurrency.sqlite3"
    database_url = request.config.getoption("--database-url")
    if database_url == "sqlite+aiosqlite:///:memory:":
        database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(
        database_url,
        **(
            {"connect_args": {"timeout": 30}}
            if database_url.startswith("sqlite")
            else {}
        ),
    )

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite_connection(dbapi_connection: Any, _: Any) -> None:
        """Enable WAL and a bounded wait for concurrent writers."""
        if engine.dialect.name != "sqlite":
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
        dbapi_connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def begin_immediate(connection: Any) -> None:
        """Serialize SQLite test transactions before their read/write sequence."""
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    configure(IDENTITY_ADAPTER=BuiltInIdentityAdapter)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(AuthBase.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(username="concurrent", email="concurrent@example.com")
        session.add(user)
        await session.flush()
        notification = await NotificationDataAccessLayer(session).create_notification(
            verb="changed state", actor=user, recipients=user, is_sent=True
        )
        await session.commit()
        user_id = user.id
        notification_id = notification.id

    try:
        yield factory, user_id, notification_id
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(AuthBase.metadata.drop_all)
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def _count_state_rows(
    factory: async_sessionmaker, model: Any, notification_id: int
) -> int:
    """Count a notification's per-user state records in a fresh session."""
    async with factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(model)
            .where(model.notification_id == notification_id)
        )
        return int(result.scalar_one())


async def test_concurrent_mark_as_seen_creates_one_record(
    concurrency_store: Tuple[async_sessionmaker, int, int],
) -> None:
    """Independent sessions racing to mark one notification create one row."""
    factory, user_id, notification_id = concurrency_store

    async def mark_seen() -> None:
        async with factory() as session:
            user = await session.get(User, user_id)
            notification = await session.get(Notification, notification_id)
            assert user is not None
            assert notification is not None
            await notification.mark_as_seen(session, user)
            await session.commit()

    await asyncio.gather(*(mark_seen() for _ in range(8)))

    assert await _count_state_rows(factory, NotificationSeen, notification_id) == 1


async def test_concurrent_mark_as_unseen_is_idempotent(
    concurrency_store: Tuple[async_sessionmaker, int, int],
) -> None:
    """Independent sessions can safely retry removal of one seen record."""
    factory, user_id, notification_id = concurrency_store

    async with factory() as session:
        user = await session.get(User, user_id)
        notification = await session.get(Notification, notification_id)
        assert user is not None
        assert notification is not None
        await notification.mark_as_seen(session, user)
        await session.commit()

    async def mark_unseen() -> bool:
        async with factory() as session:
            user = await session.get(User, user_id)
            notification = await session.get(Notification, notification_id)
            assert user is not None
            assert notification is not None
            changed = await notification.mark_as_unseen(session, user)
            await session.commit()
            return changed

    results = await asyncio.gather(*(mark_unseen() for _ in range(8)))

    assert sum(results) == 1
    assert await _count_state_rows(factory, NotificationSeen, notification_id) == 0


async def test_concurrent_create_seen_returns_one_persisted_record(
    concurrency_store: Tuple[async_sessionmaker, int, int],
) -> None:
    """Concurrent calls to the public seen factory are idempotent."""
    factory, user_id, notification_id = concurrency_store

    async def create_seen() -> int:
        async with factory() as session:
            user = await session.get(User, user_id)
            notification = await session.get(Notification, notification_id)
            assert user is not None
            assert notification is not None
            instance = await NotificationSeen.create(session, notification, user)
            await session.commit()
            return instance.id

    record_ids = await asyncio.gather(*(create_seen() for _ in range(8)))

    assert len(set(record_ids)) == 1
    assert await _count_state_rows(factory, NotificationSeen, notification_id) == 1


async def test_concurrent_soft_delete_creates_one_record(
    concurrency_store: Tuple[async_sessionmaker, int, int],
) -> None:
    """Independent sessions racing to clear one notification create one row."""
    factory, user_id, notification_id = concurrency_store

    async def delete_for_user() -> int:
        async with factory() as session:
            user = await session.get(User, user_id)
            notification = await session.get(Notification, notification_id)
            assert user is not None
            assert notification is not None
            instance = await DeletedNotification.create(session, notification, user)
            await session.commit()
            return instance.id

    record_ids = await asyncio.gather(*(delete_for_user() for _ in range(8)))

    assert len(set(record_ids)) == 1
    assert await _count_state_rows(factory, DeletedNotification, notification_id) == 1


async def test_concurrent_bulk_mark_as_seen_counts_only_new_rows(
    concurrency_store: Tuple[async_sessionmaker, int, int],
) -> None:
    """Concurrent bulk requests report only records inserted by each request."""
    factory, user_id, notification_id = concurrency_store

    async def mark_all_seen() -> int:
        async with factory() as session:
            user = await session.get(User, user_id)
            assert user is not None
            count = await NotificationDataAccessLayer(session).mark_all_as_seen(user)
            await session.commit()
            return count

    counts = await asyncio.gather(*(mark_all_seen() for _ in range(8)))

    assert sum(counts) == 1
    assert await _count_state_rows(factory, NotificationSeen, notification_id) == 1


async def test_concurrent_bulk_clear_creates_one_deletion_record(
    concurrency_store: Tuple[async_sessionmaker, int, int],
) -> None:
    """Concurrent clear-all requests cannot duplicate soft-deletion rows."""
    factory, user_id, notification_id = concurrency_store

    async with factory() as session:
        user = await session.get(User, user_id)
        notification = await session.get(Notification, notification_id)
        assert user is not None
        assert notification is not None
        await notification.mark_as_seen(session, user)
        await session.commit()

    async def clear_all() -> None:
        async with factory() as session:
            user = await session.get(User, user_id)
            assert user is not None
            await NotificationDataAccessLayer(session).clear_all(user)
            await session.commit()

    await asyncio.gather(*(clear_all() for _ in range(8)))

    assert await _count_state_rows(factory, DeletedNotification, notification_id) == 1


async def test_mark_as_seen_does_not_commit_the_callers_transaction(
    concurrency_store: Tuple[async_sessionmaker, int, int],
) -> None:
    """The host application retains commit and rollback ownership."""
    factory, user_id, notification_id = concurrency_store

    async with factory() as session:
        user = await session.get(User, user_id)
        notification = await session.get(Notification, notification_id)
        assert user is not None
        assert notification is not None
        await notification.mark_as_seen(session, user)
        await session.rollback()

    assert await _count_state_rows(factory, NotificationSeen, notification_id) == 0


async def test_digest_claims_and_due_generation_use_independent_sessions(
    concurrency_store: Any,
) -> None:
    from datetime import datetime, time, timezone

    from fastapi_notification.models.notification_digest import NotificationDigestBatch
    from fastapi_notification.repository.manager.scheduling import (
        NotificationSchedulingDataAccessLayer,
    )

    factory, user_id, _ = concurrency_store
    async with factory() as session:
        schedule = await NotificationSchedulingDataAccessLayer(
            session
        ).set_digest_schedule(
            user_id,
            local_time=time(9),
            now=datetime(2026, 11, 2, 8, tzinfo=timezone.utc),
        )
        due = schedule.next_run_at
        await session.commit()

    async def generate() -> Any:
        async with factory() as session:
            batches = await NotificationSchedulingDataAccessLayer(
                session
            ).create_due_batches(now=due)
            ids = [batch.id for batch in batches]
            await session.commit()
            return ids

    generated = await asyncio.gather(*(generate() for _ in range(4)))
    batch_ids = [identifier for identifiers in generated for identifier in identifiers]
    assert len(batch_ids) == 1
    batch_id = batch_ids[0]

    async def claim() -> Any:
        async with factory() as session:
            claimed = await NotificationSchedulingDataAccessLayer(session).claim_batch(
                batch_id, now=due
            )
            won = claimed is not None
            await session.commit()
            return won

    assert sum(await asyncio.gather(*(claim() for _ in range(8)))) == 1
    async with factory() as session:
        batch = await session.get(NotificationDigestBatch, batch_id)
        assert batch.status == "processing"
        assert batch.attempts == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(NotificationDigestBatch)
            )
            == 1
        )


async def test_concurrent_seen_and_deletion_preserve_hidden_inbox(
    concurrency_store: Any,
) -> None:
    factory, user_id, notification_id = concurrency_store

    async def transition(clear: bool) -> None:
        async with factory() as session:
            user = await session.get(User, user_id)
            notification = await session.get(Notification, notification_id)
            assert user is not None and notification is not None
            if clear:
                await DeletedNotification.create(session, notification, user)
            else:
                await notification.mark_as_seen(session, user)
            await session.commit()

    await asyncio.gather(*(transition(index % 2 == 0) for index in range(8)))
    assert await _count_state_rows(factory, NotificationSeen, notification_id) == 1
    assert await _count_state_rows(factory, DeletedNotification, notification_id) == 1
    async with factory() as session:
        user = await session.get(User, user_id)
        assert (
            await NotificationDataAccessLayer(session).sent(
                recipients=user, exclude_deleted_by=user
            )
            == []
        )


async def test_concurrent_async_key_reclamation_scope_and_release(
    concurrency_store: Any,
) -> None:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    from fastapi_notification.models.deduplication import NotificationDeduplication

    factory, user_id, _ = concurrency_store

    async def create(scope: str) -> int:
        async with factory() as session:
            user = await session.get(User, user_id)
            notification = await NotificationDataAccessLayer(
                session
            ).create_notification(
                verb="key race",
                actor=user,
                recipients=user,
                is_sent=True,
                deduplication_key="shared-event",
                deduplication_scope=scope,
            )
            await session.commit()
            return notification.id

    initial = await asyncio.gather(*(create("scope-a") for _ in range(8)))
    assert len(set(initial)) == 1
    other_scope_id = await create("scope-b")
    assert other_scope_id != initial[0]
    async with factory() as session:
        await session.execute(
            update(NotificationDeduplication)
            .where(NotificationDeduplication.scope == "scope-a")
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await session.commit()

    reclaimed = await asyncio.gather(*(create("scope-a") for _ in range(8)))
    assert len(set(reclaimed)) == 1
    assert reclaimed[0] != initial[0]
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Notification)) == 4
        assert (
            await session.scalar(
                select(func.count()).select_from(NotificationDeduplication)
            )
            == 2
        )
        ledger = await session.scalar(
            select(NotificationDeduplication).where(
                NotificationDeduplication.scope == "scope-a"
            )
        )
        assert ledger.notification_id == reclaimed[0]
        user = await session.get(User, user_id)
        user.is_staff = True
        await session.flush()
        await NotificationDataAccessLayer(session).delete_notification(
            reclaimed[0], soft_delete=False, actor=user
        )
        await session.commit()
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(NotificationDeduplication)
            )
            == 1
        )
        assert await session.get(Notification, initial[0]) is not None
    await create("scope-a")
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(NotificationDeduplication)
            )
            == 2
        )


async def test_partial_notification_work_rolls_back_at_savepoint(
    concurrency_store: Any,
) -> None:
    factory, user_id, _ = concurrency_store
    async with factory() as session:
        user = await session.get(User, user_id)
        with pytest.raises(RuntimeError, match="provider preparation failed"):
            async with session.begin_nested():
                await NotificationDataAccessLayer(session).create_notification(
                    verb="must roll back",
                    actor=user,
                    recipients=user,
                    deduplication_key="rolled-back-event",
                )
                raise RuntimeError("provider preparation failed")
        await session.commit()
    from fastapi_notification.models.deduplication import NotificationDeduplication
    from fastapi_notification.models.notification_recipient import NotificationRecipient

    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Notification)) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(NotificationRecipient)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(NotificationDeduplication)
            )
            == 0
        )
