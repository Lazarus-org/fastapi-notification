"""Independent-session tests for concurrent notification idempotency."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List

import pytest
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
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




def _use_immediate_sqlite_transactions(engine: Any) -> None:
    """Serialize SQLite writers before their first read to avoid lock upgrades."""

    @event.listens_for(engine, "connect")
    def _disable_driver_begin(connection: Any, _record: Any) -> None:
        connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")

@pytest.mark.asyncio
async def test_concurrent_creates_with_same_key_produce_one_notification(
    tmp_path: Path,
) -> None:
    """Separate sessions racing on one key converge on the same notification."""
    configure(IDENTITY_ADAPTER=BuiltInIdentityAdapter)
    database_path = tmp_path / "notification-deduplication.sqlite3"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 20},
    )
    _use_immediate_sqlite_transactions(engine.sync_engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(AuthBase.metadata.create_all)

        async with factory() as session:
            user = User(username="concurrent", email="concurrent@example.com")
            session.add(user)
            await session.commit()
            user_id = user.id
            # Pre-create the natural content type so the race isolates the
            # idempotency-key constraint rather than the content-type registry.
            await ContentType.get_for_model(session, User)
            await session.commit()

        async def create_once(verb: str) -> int:
            async with factory() as session:
                actor = await session.get(User, user_id)
                notification = await NotificationDataAccessLayer(
                    session
                ).create_notification(
                    verb=verb,
                    actor=actor,
                    recipients=actor,
                    is_sent=True,
                    deduplication_scope="concurrency-test",
                    deduplication_key="event:concurrent:1",
                )
                await session.commit()
                return notification.id

        notification_ids: List[int] = await asyncio.gather(
            create_once("first retry"), create_once("second retry")
        )
        assert notification_ids[0] == notification_ids[1]

        async with factory() as session:
            assert await session.scalar(
                select(func.count()).select_from(Notification)
            ) == 1
            assert await session.scalar(
                select(func.count()).select_from(NotificationDeduplication)
            ) == 1
    finally:
        await engine.dispose()


# The synchronous SQLite concurrency harness below lets the core uniqueness
# race run in environments where the optional aiosqlite driver is unavailable.
class SyncSessionAdapter:
    """Provide the AsyncSession methods used by DAL writes over sync SQLite."""

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


@pytest.mark.asyncio
async def test_concurrent_sync_sqlite_sessions_converge_on_one_key(
    tmp_path: Path,
) -> None:
    """Independent connections rely on the unique constraint, not a pre-check."""
    configure(IDENTITY_ADAPTER=BuiltInIdentityAdapter)
    database_path = tmp_path / "notification-deduplication-sync.sqlite3"
    engine = create_engine(
        f"sqlite:///{database_path}", connect_args={"timeout": 20}
    )
    _use_immediate_sqlite_transactions(engine)
    Base.metadata.create_all(engine)
    AuthBase.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            user = User(username="sync-concurrent", email="sync@example.com")
            session.add(user)
            session.flush()
            user_id = user.id
            session.commit()

        def create_once(verb: str) -> int:
            with Session(engine) as session:
                actor = session.get(User, user_id)
                notification = asyncio.run(
                    NotificationDataAccessLayer(
                        SyncSessionAdapter(session)  # type: ignore[arg-type]
                    ).create_notification(
                        verb=verb,
                        actor=actor,
                        recipients=actor,
                        is_sent=True,
                        deduplication_scope="threaded-sqlite",
                        deduplication_key="event:parallel:1",
                    )
                )
                session.commit()
                return notification.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = list(executor.map(create_once, ["attempt one", "attempt two"]))

        assert ids[0] == ids[1]
        with Session(engine) as session:
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
async def test_concurrent_retries_reclaim_an_expired_key_only_once(
    tmp_path: Path,
) -> None:
    """Two concurrent retries after key expiry still create only one new row."""
    configure(IDENTITY_ADAPTER=BuiltInIdentityAdapter)
    database_path = tmp_path / "notification-deduplication-expiry.sqlite3"
    engine = create_engine(
        f"sqlite:///{database_path}", connect_args={"timeout": 20}
    )
    _use_immediate_sqlite_transactions(engine)
    Base.metadata.create_all(engine)
    AuthBase.metadata.create_all(engine)

    try:
        def create_initial() -> tuple[int, int]:
            with Session(engine) as session:
                user = User(
                    username="expired-race", email="expired-race@example.com"
                )
                session.add(user)
                session.flush()
                user_id = user.id
                asyncio.run(
                    ContentType.get_for_model(
                        SyncSessionAdapter(session), User  # type: ignore[arg-type]
                    )
                )
                session.commit()

                initial = asyncio.run(
                    NotificationDataAccessLayer(
                        SyncSessionAdapter(session)  # type: ignore[arg-type]
                    ).create_notification(
                        verb="original",
                        actor=user,
                        deduplication_scope="expired-race",
                        deduplication_key="event:expired:1",
                        deduplication_key_expires_at=(
                            datetime.now(timezone.utc) + timedelta(days=1)
                        ),
                    )
                )
                initial_id = initial.id
                session.execute(
                    update(NotificationDeduplication)
                    .where(
                        NotificationDeduplication.notification_id == initial_id
                    )
                    .values(
                        expires_at=datetime.now(timezone.utc)
                        - timedelta(seconds=1)
                    )
                )
                session.commit()
                return user_id, initial_id

        user_id, initial_id = await asyncio.to_thread(create_initial)

        def create_once(verb: str) -> int:
            with Session(engine) as session:
                actor = session.get(User, user_id)
                notification = asyncio.run(
                    NotificationDataAccessLayer(
                        SyncSessionAdapter(session)  # type: ignore[arg-type]
                    ).create_notification(
                        verb=verb,
                        actor=actor,
                        deduplication_scope="expired-race",
                        deduplication_key="event:expired:1",
                    )
                )
                session.commit()
                return notification.id

        with ThreadPoolExecutor(max_workers=2) as executor:
            ids = list(executor.map(create_once, ["retry one", "retry two"]))

        assert ids[0] == ids[1]
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(Notification)) == 2
            assert (
                session.scalar(
                    select(func.count()).select_from(NotificationDeduplication)
                )
                == 1
            )
            key_record = session.scalar(select(NotificationDeduplication))
            assert key_record.notification_id == ids[0]
            assert key_record.notification_id != initial_id
    finally:
        engine.dispose()
