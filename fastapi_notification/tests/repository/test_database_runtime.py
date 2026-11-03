"""Runtime metadata and constraint verification on the selected test backend."""

from typing import Any

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from fastapi_notification.models.base import Base
from fastapi_notification.models.notification_seen import NotificationSeen


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
