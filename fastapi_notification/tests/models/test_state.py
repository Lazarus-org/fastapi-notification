"""Tests for portable, conflict-safe notification state persistence."""

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import literal, select
from sqlalchemy.dialects import mysql, postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.notification import Notification
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.models.state import (
    _dialect_insert,
    _existing_row_statement,
    insert_if_absent,
    insert_many_from_select_if_absent,
)

pytestmark = pytest.mark.models


def test_dialect_insert_supports_postgresql_upsert() -> None:
    """The PostgreSQL strategy builds a native conflict-safe insert."""
    fake_session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    )
    statement = _dialect_insert(fake_session, NotificationSeen)
    compiled = str(
        statement.values(notification_id=1, user_id="42")
        .on_conflict_do_nothing(
            index_elements=[
                NotificationSeen.notification_id,
                NotificationSeen.user_id,
            ]
        )
        .compile(dialect=postgresql.dialect())
    )

    assert "ON CONFLICT (notification_id, user_id) DO NOTHING" in compiled


async def test_insert_if_absent_uses_savepoint_fallback(
    monkeypatch: Any,
    session: AsyncSession,
    notification: Notification,
    user: Any,
) -> None:
    """Dialects without native upsert use the unique constraint and savepoint."""
    from fastapi_notification.models import state

    monkeypatch.setattr(state, "_dialect_insert", lambda *_: None)
    values = {"notification_id": notification.id, "user_id": str(user.id)}

    first, inserted_first = await insert_if_absent(
        session, NotificationSeen, values, ("notification_id", "user_id")
    )
    second, inserted_second = await insert_if_absent(
        session, NotificationSeen, values, ("notification_id", "user_id")
    )

    assert inserted_first is True
    assert inserted_second is False
    assert first.id == second.id


async def test_bulk_insert_fallback_is_idempotent(
    monkeypatch: Any,
    session: AsyncSession,
    notification: Notification,
    user: Any,
) -> None:
    """The portable bulk fallback inserts each unique state row once."""
    from fastapi_notification.models import state

    monkeypatch.setattr(state, "_dialect_insert", lambda *_: None)
    source = select(literal(notification.id), literal(str(user.id)))

    first_count = await insert_many_from_select_if_absent(
        session,
        NotificationSeen,
        ("notification_id", "user_id"),
        source,
        ("notification_id", "user_id"),
    )
    second_count = await insert_many_from_select_if_absent(
        session,
        NotificationSeen,
        ("notification_id", "user_id"),
        source,
        ("notification_id", "user_id"),
    )

    assert first_count == 1
    assert second_count == 0


def test_dialect_insert_returns_none_for_unknown_dialect() -> None:
    """Unknown dialects use the portable savepoint fallback."""
    fake_session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="mysql"))
    )

    assert _dialect_insert(fake_session, NotificationSeen) is None


async def test_insert_if_absent_reraises_non_duplicate_integrity_errors(
    monkeypatch: Any,
    session: AsyncSession,
    notification: Notification,
) -> None:
    """The savepoint fallback does not hide unrelated integrity violations."""
    from sqlalchemy.exc import IntegrityError

    from fastapi_notification.models import state

    monkeypatch.setattr(state, "_dialect_insert", lambda *_: None)
    with pytest.raises(IntegrityError):
        await insert_if_absent(
            session,
            NotificationSeen,
            {"notification_id": notification.id, "user_id": None},
            ("notification_id", "user_id"),
        )


async def test_bulk_fallback_rolls_back_the_whole_batch_on_failure(
    monkeypatch: Any,
    session: AsyncSession,
    notification: Notification,
    user: Any,
) -> None:
    """A failed fallback batch leaves no partial state rows in the transaction."""
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    from fastapi_notification.models import state

    monkeypatch.setattr(state, "_dialect_insert", lambda *_: None)
    source = select(literal(notification.id), literal(str(user.id))).union_all(
        select(literal(notification.id), literal(None))
    )

    with pytest.raises(IntegrityError):
        await insert_many_from_select_if_absent(
            session,
            NotificationSeen,
            ("notification_id", "user_id"),
            source,
            ("notification_id", "user_id"),
        )

    result = await session.execute(
        select(func.count())
        .select_from(NotificationSeen)
        .where(NotificationSeen.notification_id == notification.id)
    )
    assert result.scalar_one() == 0


async def test_insert_if_absent_raises_if_inserted_row_cannot_be_reloaded() -> None:
    """A successful insert without a retrievable row is treated as corruption."""

    class FakeResult:
        rowcount = 1

        def scalar_one_or_none(self) -> None:
            return None

    class FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        def get_bind(self) -> Any:
            return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        async def execute(self, _: Any) -> FakeResult:
            self.calls += 1
            return FakeResult()

    session = FakeSession()

    with pytest.raises(RuntimeError, match="without a retrievable row"):
        await insert_if_absent(
            session,  # type: ignore[arg-type]
            NotificationSeen,
            {"notification_id": 1, "user_id": "42"},
            ("notification_id", "user_id"),
        )


def test_mysql_duplicate_lookup_uses_a_current_read() -> None:
    """MySQL duplicate recovery bypasses an older repeatable-read snapshot."""
    fake_session = SimpleNamespace(
        get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name="mysql"))
    )
    statement = _existing_row_statement(
        fake_session,
        NotificationSeen,
        (NotificationSeen.notification_id == 1, NotificationSeen.user_id == "42"),
    )

    assert "FOR UPDATE" in str(statement.compile(dialect=mysql.dialect()))
