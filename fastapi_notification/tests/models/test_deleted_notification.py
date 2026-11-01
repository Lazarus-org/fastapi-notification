import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import User
from fastapi_notification.models.deleted_notification import DeletedNotification
from fastapi_notification.models.notification import Notification

pytestmark = [pytest.mark.models, pytest.mark.models_deleted_notification]


async def test_create_records_the_deletion(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """Creating a deletion record links the notification and the user."""
    deleted = await DeletedNotification.create(session, notification, user)
    await session.commit()

    assert deleted.notification_id == notification.id
    assert deleted.user_id == str(user.id)
    assert deleted.deleted_at is not None


async def test_create_rejects_an_unrelated_user(
    notification: Notification, other_user: User, session: AsyncSession
) -> None:
    """A user with no claim on a notification cannot delete it."""
    with pytest.raises(PermissionError, match="delete"):
        await DeletedNotification.create(session, notification, other_user)


async def test_create_rejects_staff_without_audience_membership(
    notification: Notification, staff_user: User, session: AsyncSession
) -> None:
    """Staff cannot soft-delete another user's personal notification."""
    with pytest.raises(PermissionError, match="delete"):
        await DeletedNotification.create(session, notification, staff_user)


async def test_create_rejects_superuser_without_audience_membership(
    notification: Notification, superuser_only: User, session: AsyncSession
) -> None:
    """Superuser status alone does not grant permission to soft-delete."""
    with pytest.raises(PermissionError, match="delete"):
        await DeletedNotification.create(session, notification, superuser_only)


async def test_str_falls_back_when_relationships_are_absent(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """The string form still renders without loaded relationships."""
    deleted = await DeletedNotification.create(session, notification, user)
    await session.commit()

    assert "deleted by Unknown" in str(deleted)


async def test_str_uses_loaded_relationships(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """When the relationships are loaded, the string form uses them."""
    deleted = await DeletedNotification.create(session, notification, user)
    await session.commit()

    deleted.user = user
    deleted.notification = notification

    assert "deleted by ann" in str(deleted)
