"""Identity normalization and persistence for notification audiences."""

from typing import Any, List, Sequence

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.constants.qs_types import Groups, Recipients
from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.models.deduplication import NotificationDeduplication
from fastapi_notification.models.deleted_notification import DeletedNotification
from fastapi_notification.models.notification import Notification, notification_group
from fastapi_notification.models.notification_recipient import NotificationRecipient
from fastapi_notification.models.notification_seen import NotificationSeen


def _as_sequence(value: Any) -> Sequence[Any]:
    """Normalize one identity or a collection of identities."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or hasattr(value, "id"):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]


def _ids(value: Any, identity_type: str = "user") -> List[str]:
    """Extract normalized user or group identifiers through the adapter."""
    adapter = get_identity_adapter()
    getter = adapter.get_user_id if identity_type == "user" else adapter.get_group_id
    return [getter(item) for item in _as_sequence(value)]


async def add_recipients(
    session: AsyncSession, notification: Notification, recipients: Recipients
) -> None:
    """Address an existing notification to further recipients.

    Args:
        session (AsyncSession): The session used to write.
        notification (Notification): The notification to address.
        recipients (Recipients): The users to address it to.
    """
    recipient_objects = list(_as_sequence(recipients))
    notification.recipient = list(notification.recipient) + recipient_objects
    session.add_all(
        [
            NotificationRecipient(
                notification_id=notification.id, recipient_id=recipient_id
            )
            for recipient_id in _ids(recipients, "user")
        ]
    )
    await session.flush()


async def add_groups(
    session: AsyncSession, notification: Notification, groups: Groups
) -> None:
    """Address an existing notification to further groups.

    The association rows are inserted directly rather than by appending to the
    relationship, which would require the collection to be loaded first.

    Args:
        session (AsyncSession): The session used to write.
        notification (Notification): The notification to address.
        groups (Groups): The groups to address it to.
    """
    group_objects = list(_as_sequence(groups))
    notification.group = list(notification.group) + group_objects
    group_ids = _ids(groups, "group")
    if not group_ids:
        return

    await session.execute(
        insert(notification_group),
        [
            {"notification_id": notification.id, "group_id": group_id}
            for group_id in group_ids
        ],
    )
    await session.flush()


async def _delete_notification_associations(
    session: AsyncSession, notification_ids: Sequence[int]
) -> None:
    """Remove dependent rows even when database foreign keys are disabled."""
    for model in (
        NotificationDeduplication,
        NotificationSeen,
        DeletedNotification,
        NotificationRecipient,
    ):
        await session.execute(
            delete(model).where(model.notification_id.in_(notification_ids))
        )
    await session.execute(
        delete(notification_group).where(
            notification_group.c.notification_id.in_(notification_ids)
        )
    )
