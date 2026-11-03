"""Runtime metadata and constraint verification on the selected test backend."""

from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import User
from fastapi_notification.models.base import Base
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)


async def test_schema_constraints_indexes_and_foreign_key_enforcement(
    engine: Any, session: Any
) -> None:
    async with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            await connection.exec_driver_sql("PRAGMA foreign_keys=ON")

        def verify(sync_connection: Any) -> None:
            inspector = inspect(sync_connection)
            assert set(Base.metadata.tables) <= set(inspector.get_table_names())
            for table in Base.metadata.sorted_tables:
                assert set(
                    inspector.get_pk_constraint(table.name)["constrained_columns"]
                ) == {column.name for column in table.primary_key}
                actual_indexes = {
                    index["name"] for index in inspector.get_indexes(table.name)
                }
                assert {index.name for index in table.indexes} <= actual_indexes
                actual_foreign_keys = {
                    tuple(key["constrained_columns"])
                    for key in inspector.get_foreign_keys(table.name)
                }
                assert {
                    tuple(column.name for column in constraint.columns)
                    for constraint in table.foreign_key_constraints
                } <= actual_foreign_keys
                actual_unique = {
                    tuple(constraint["column_names"])
                    for constraint in inspector.get_unique_constraints(table.name)
                }
                from sqlalchemy import CheckConstraint, UniqueConstraint

                assert {
                    tuple(column.name for column in constraint.columns)
                    for constraint in table.constraints
                    if isinstance(constraint, UniqueConstraint)
                } <= actual_unique
                actual_checks = {
                    constraint["name"]
                    for constraint in inspector.get_check_constraints(table.name)
                }
                assert {
                    constraint.name
                    for constraint in table.constraints
                    if isinstance(constraint, CheckConstraint)
                } <= actual_checks

        await connection.run_sync(verify)
        await connection.commit()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(
                NotificationSeen(notification_id=999999999, user_id="unrelated")
            )
            await session.flush()
    assert session.is_active


@pytest.mark.parametrize("bulk", [False, True])
async def test_permanent_deletion_cleans_all_associations(
    session: Any, dal: Any, user: Any, staff_user: Any, group: Any, bulk: bool
) -> None:
    from sqlalchemy import func, select

    from fastapi_notification.models.deduplication import NotificationDeduplication
    from fastapi_notification.models.deleted_notification import DeletedNotification
    from fastapi_notification.models.notification import (
        Notification,
        notification_group,
    )
    from fastapi_notification.models.notification_recipient import NotificationRecipient
    from fastapi_notification.models.notification_seen import NotificationSeen

    notification = await dal.create_notification(
        verb="delete completely",
        actor=user,
        recipients=user,
        groups=group,
        deduplication_key="delete-completely",
        is_sent=True,
    )
    await notification.mark_as_seen(session, user)
    await DeletedNotification.create(session, notification, user)
    await session.commit()
    notification_id = notification.id
    if bulk:
        assert (
            await dal.delete_many(
                select(Notification).where(Notification.id == notification_id),
                actor=staff_user,
            )
            == 1
        )
    else:
        await dal.delete_notification(
            notification_id, soft_delete=False, actor=staff_user
        )
    await session.commit()
    model: Any
    for model in [
        NotificationRecipient,
        NotificationSeen,
        DeletedNotification,
        NotificationDeduplication,
    ]:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.notification_id == notification_id)
            )
            == 0
        )
    assert (
        await session.scalar(
            select(func.count())
            .select_from(notification_group)
            .where(notification_group.c.notification_id == notification_id)
        )
        == 0
    )
    assert await session.get(Notification, notification_id) is None
    recreated = await dal.create_notification(
        verb="recreated",
        actor=user,
        recipients=user,
        groups=group,
        deduplication_key="delete-completely",
        is_sent=True,
    )
    await session.commit()
    assert (
        await session.scalar(
            select(func.count())
            .select_from(NotificationRecipient)
            .where(NotificationRecipient.notification_id == recreated.id)
        )
        == 1
    )


@pytest.mark.parametrize(
    "left,right", [("HostUser", "hostuser"), ("cafe", "café"), ("user", "user ")]
)
async def test_opaque_recipient_identifiers_remain_distinct(
    session: AsyncSession,
    dal: NotificationDataAccessLayer,
    user: User,
    left: str,
    right: str,
) -> None:
    """Database collation must not grant another opaque identity inbox access."""
    first = await dal.create_notification(
        verb="first inbox", actor=user, recipients=left, is_sent=True
    )
    second = await dal.create_notification(
        verb="second inbox", actor=user, recipients=right, is_sent=True
    )
    await session.commit()
    assert [row.id for row in await dal.sent(recipients=left, display_detail=True)] == [
        first.id
    ]
    assert [
        row.id for row in await dal.sent(recipients=right, display_detail=True)
    ] == [second.id]


@pytest.mark.parametrize(
    "left_scope,right_scope,left_key,right_key",
    [
        ("Tenant", "tenant", "event", "event"),
        ("tenant", "tenant", "Event", "event"),
    ],
)
async def test_opaque_deduplication_scopes_and_keys_remain_distinct(
    session: AsyncSession,
    dal: NotificationDataAccessLayer,
    user: User,
    left_scope: str,
    right_scope: str,
    left_key: str,
    right_key: str,
) -> None:
    first = await dal.create_notification(
        verb="first event",
        actor=user,
        deduplication_scope=left_scope,
        deduplication_key=left_key,
    )
    second = await dal.create_notification(
        verb="second event",
        actor=user,
        deduplication_scope=right_scope,
        deduplication_key=right_key,
    )
    await session.commit()
    assert first.id != second.id


async def test_opaque_identity_settings_and_group_isolation(
    session: AsyncSession,
    dal: NotificationDataAccessLayer,
    user: User,
) -> None:
    from datetime import time

    from fastapi_notification.repository.manager.preferences import (
        NotificationPreferenceDataAccessLayer,
    )
    from fastapi_notification.repository.manager.scheduling import (
        NotificationSchedulingDataAccessLayer,
    )

    preferences = NotificationPreferenceDataAccessLayer(session)
    await preferences.set_preference(
        "HostUser", category="orders", channel="email", enabled=False
    )
    await preferences.set_preference(
        "hostuser", category="orders", channel="email", enabled=True
    )
    assert (
        await preferences.is_enabled("HostUser", category="orders", channel="email")
        is False
    )
    assert (
        await preferences.is_enabled("hostuser", category="orders", channel="email")
        is True
    )
    scheduling = NotificationSchedulingDataAccessLayer(session)
    await scheduling.set_quiet_hours("HostUser", start_time=time(22), end_time=time(7))
    assert await scheduling.list_quiet_hours("hostuser") == []
    first = await dal.create_notification(
        verb="upper group", actor=user, groups="Operations", is_sent=True
    )
    second = await dal.create_notification(
        verb="lower group", actor=user, groups="operations", is_sent=True
    )
    await session.commit()
    assert [
        row.id for row in await dal.sent(groups="Operations", display_detail=True)
    ] == [first.id]
    assert [
        row.id for row in await dal.sent(groups="operations", display_detail=True)
    ] == [second.id]


async def test_utc_and_local_time_microseconds_round_trip(
    session: AsyncSession, dal: NotificationDataAccessLayer, user: User
) -> None:
    from datetime import datetime, time, timezone

    from fastapi_notification.repository.manager.scheduling import (
        NotificationSchedulingDataAccessLayer,
    )

    instant = datetime(2030, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
    notification = await dal.create_notification(
        verb="precise expiry", actor=user, expires_at=instant
    )
    scheduling = NotificationSchedulingDataAccessLayer(session)
    quiet = await scheduling.set_quiet_hours(
        user, start_time=time(22, 0, 0, 123456), end_time=time(7, 0, 0, 654321)
    )
    await session.commit()
    await session.refresh(notification)
    await session.refresh(quiet)
    assert notification.expires_at == instant
    assert quiet.start_time == time(22, 0, 0, 123456)
    assert quiet.end_time == time(7, 0, 0, 654321)


async def test_timestamp_ties_and_grouped_read_state_are_portable(
    session: AsyncSession, dal: NotificationDataAccessLayer, user: User
) -> None:
    """Equal timestamps have stable order and strict SQL grouping preserves state."""
    from datetime import datetime, timezone

    from sqlalchemy import update

    from fastapi_notification.models.notification import Notification

    first = await dal.create_notification(
        verb="read", actor=user, recipients=user, is_sent=True
    )
    second = await dal.create_notification(
        verb="unread", actor=user, recipients=user, is_sent=True
    )
    await session.execute(
        update(Notification).values(timestamp=datetime(2030, 1, 2, tzinfo=timezone.utc))
    )
    await first.mark_as_seen(session, user)
    await session.commit()
    assert [row.id for row in await dal.sent(recipients=user, display_detail=True)] == [
        second.id,
        first.id,
    ]
    summary = await dal.summary(
        dal.sent_statement(recipients=user, exclude_deleted_by=user), user
    )
    assert (summary["total"], summary["read"], summary["unread"]) == (2, 1, 1)
