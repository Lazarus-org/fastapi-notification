import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import User
from fastapi_notification.models.notification import Notification
from fastapi_notification.models.notification_recipient import NotificationRecipient

pytestmark = [pytest.mark.models, pytest.mark.models_notification_recipient]


async def test_recipients_are_linked_to_the_notification(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """Addressing a notification creates the association row."""
    result = await session.execute(
        select(NotificationRecipient).where(
            NotificationRecipient.notification_id == notification.id
        )
    )
    links = result.scalars().all()

    assert [link.recipient_id for link in links] == [str(user.id)]


async def test_str_falls_back_when_relationships_are_absent(
    notification: Notification, session: AsyncSession
) -> None:
    """The string form still renders without loaded relationships."""
    result = await session.execute(select(NotificationRecipient))
    link = result.scalars().one()

    assert "Recipient: Unknown" in str(link)


async def test_str_uses_loaded_relationships(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """When the relationships are loaded, the string form uses them."""
    result = await session.execute(select(NotificationRecipient))
    link = result.scalars().one()

    setattr(link, "recipient", user)
    setattr(link, "notification", notification)

    assert "Recipient: ann" in str(link)
    assert "liked your post" in str(link)
