import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.notification import Notification
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)

pytestmark = [pytest.mark.models, pytest.mark.models_notification_seen]


async def test_create_records_the_viewer(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """Creating a seen record links the notification and the user."""
    seen = await NotificationSeen.create(session, notification, user)
    await session.commit()

    assert seen.notification_id == notification.id
    assert seen.user_id == str(user.id)
    assert seen.seen_at is not None


async def test_create_rejects_an_unrelated_user(
    notification: Notification, other_user: User, session: AsyncSession
) -> None:
    """A user with no claim on a notification cannot record seeing it."""
    with pytest.raises(PermissionError, match="mark as seen"):
        await NotificationSeen.create(session, notification, other_user)


async def test_create_allows_a_group_member(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
) -> None:
    """Membership of a targeted group is enough to record a view."""
    created = await dal.create_notification(
        verb="announced", actor=user, groups=group, is_sent=True
    )
    await session.commit()

    seen = await NotificationSeen.create(session, created, group_user)
    await session.commit()

    assert seen.user_id == str(group_user.id)


async def test_str_names_the_user_and_notification(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """The string form names who saw what."""
    seen = await NotificationSeen.create(session, notification, user)
    await session.commit()

    rendered = str(seen)

    assert "Unknown" in rendered
    assert str(seen.user_id) in rendered


async def test_str_uses_loaded_relationships(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """When the relationships are loaded, the string form uses them."""
    seen = await NotificationSeen.create(session, notification, user)
    await session.commit()

    seen.user = user
    seen.notification = notification

    assert str(seen).startswith("ann (ID:")
    assert "liked your post" in str(seen)
