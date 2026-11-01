"""Tests for explicit per-user notification read-state transitions."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.deleted_notification import DeletedNotification
from fastapi_notification.models.notification import Notification
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)

pytestmark = [pytest.mark.models, pytest.mark.models_notification]


async def _seen_count(
    session: AsyncSession, notification_id: int, user_id: int
) -> int:
    """Count a specific user's seen record for one notification."""
    result = await session.execute(
        select(func.count()).select_from(NotificationSeen).where(
            NotificationSeen.notification_id == notification_id,
            NotificationSeen.user_id == str(user_id),
        )
    )
    return int(result.scalar_one())


async def test_mark_as_unseen_removes_the_current_users_seen_state(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """Mark-as-unseen deletes the caller's state and updates a loaded projection."""
    await notification.mark_as_seen(session, user)
    await session.commit()
    await notification.load_identities(session)
    assert [identity.id for identity in notification.seen_by] == [user.id]

    changed = await notification.mark_as_unseen(session, user)
    await session.commit()

    assert changed is True
    assert await _seen_count(session, notification.id, user.id) == 0
    assert notification.seen_by == []


async def test_mark_as_unseen_is_idempotent(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """Repeating mark-as-unseen succeeds without another state change."""
    await notification.mark_as_seen(session, user)
    await session.commit()

    first = await notification.mark_as_unseen(session, user)
    second = await notification.mark_as_unseen(session, user)
    await session.commit()

    assert first is True
    assert second is False
    assert await _seen_count(session, notification.id, user.id) == 0


async def test_mark_as_unseen_does_not_change_other_recipients(
    dal: NotificationDataAccessLayer,
    user: User,
    other_user: User,
    session: AsyncSession,
) -> None:
    """Removing one user's read state leaves every other recipient untouched."""
    notification = await dal.create_notification(
        verb="shared update",
        actor=user,
        recipients=[user, other_user],
        is_sent=True,
    )
    await session.commit()

    await notification.mark_as_seen(session, user)
    await notification.mark_as_seen(session, other_user)
    await session.commit()

    assert await notification.mark_as_unseen(session, user) is True
    await session.commit()

    assert await _seen_count(session, notification.id, user.id) == 0
    assert await _seen_count(session, notification.id, other_user.id) == 1


async def test_group_member_can_mark_group_notification_as_unseen(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
) -> None:
    """Current membership of a targeted group authorizes the transition."""
    notification = await dal.create_notification(
        verb="group update", actor=user, groups=group, is_sent=True
    )
    await session.commit()

    await notification.mark_as_seen(session, group_user)
    await session.commit()

    assert await notification.mark_as_unseen(session, group_user) is True
    await session.commit()
    assert await _seen_count(session, notification.id, group_user.id) == 0


async def test_mark_as_unseen_rejects_an_unrelated_user(
    notification: Notification, other_user: User, session: AsyncSession
) -> None:
    """An unrelated user cannot change another recipient's read state."""
    with pytest.raises(PermissionError, match="mark as unseen"):
        await notification.mark_as_unseen(session, other_user)


async def test_mark_as_unseen_rejects_staff_without_audience_membership(
    notification: Notification, staff_user: User, session: AsyncSession
) -> None:
    """Staff status does not grant access to another user's notification."""
    with pytest.raises(PermissionError, match="mark as unseen"):
        await notification.mark_as_unseen(session, staff_user)


async def test_mark_as_unseen_rejects_an_unsent_notification(
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
) -> None:
    """An unsent notification cannot be moved into a recipient's inbox."""
    notification = await dal.create_notification(
        verb="draft", actor=user, recipients=user, is_sent=False
    )
    await session.commit()

    with pytest.raises(PermissionError, match="unsent"):
        await notification.mark_as_unseen(session, user)


async def test_mark_as_unseen_rejects_a_cleared_notification(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """A user must not restore an item while its soft deletion remains active."""
    await notification.mark_as_seen(session, user)
    await DeletedNotification.create(session, notification, user)
    await session.commit()

    with pytest.raises(PermissionError, match="cleared"):
        await notification.mark_as_unseen(session, user)

    assert await _seen_count(session, notification.id, user.id) == 1


async def test_mark_as_unseen_rejects_superuser_without_audience_membership(
    notification: Notification, superuser_only: User, session: AsyncSession
) -> None:
    """Superuser status alone does not grant access to another inbox."""
    with pytest.raises(PermissionError, match="mark as unseen"):
        await notification.mark_as_unseen(session, superuser_only)


async def test_mark_as_unseen_does_not_commit_the_callers_transaction(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """The host application retains ownership of commit and rollback."""
    await notification.mark_as_seen(session, user)
    await session.commit()

    await notification.mark_as_unseen(session, user)
    await session.rollback()

    assert await _seen_count(session, notification.id, user.id) == 1
