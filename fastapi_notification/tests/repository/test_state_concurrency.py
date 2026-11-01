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
) -> AsyncIterator[Tuple[async_sessionmaker, int, int]]:
    """Create a file-backed SQLite database for independent concurrent sessions."""
    database_path = tmp_path / "notification-concurrency.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 30},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite_connection(dbapi_connection: Any, _: Any) -> None:
        """Enable WAL and a bounded wait for concurrent writers."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
        dbapi_connection.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def begin_immediate(connection: Any) -> None:
        """Serialize SQLite test transactions before their read/write sequence."""
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

    yield factory, user_id, notification_id
    await engine.dispose()


async def _count_state_rows(
    factory: async_sessionmaker, model: Any, notification_id: int
) -> int:
    """Count a notification's per-user state records in a fresh session."""
    async with factory() as session:
        result = await session.execute(
            select(func.count()).select_from(model).where(
                model.notification_id == notification_id
            )
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
