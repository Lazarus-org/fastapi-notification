import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.models.associations import notification_group
from fastapi_notification.models.notification_recipient import NotificationRecipient
from fastapi_notification.utils.username import get_username


class NotificationPermission:
    """Determine whether a host identity may act on a notification.

    Permission checks use the notification's opaque recipient/group association
    identifiers and the configured identity adapter. Staff and superuser flags do not
    grant access to another user's personal notification. Administrative operations are
    authorized separately at their dedicated API boundaries.
    """

    def __init__(self, notification: Any) -> None:
        self.notification = notification

    def user_has_permission(self, user: Any) -> bool:
        """Check permission against identity collections already in memory.

        This synchronous helper is limited to already-hydrated notification and identity
        data. An adapter with database-backed group membership must implement
        ``get_user_group_ids_sync`` as well. Database-backed application code should use
        :meth:`validate_permission_async`, which calls the authoritative asynchronous
        adapter method.
        """
        adapter = get_identity_adapter()
        user_id = adapter.get_user_id(user)
        is_recipient = any(
            adapter.get_user_id(recipient) == user_id
            for recipient in getattr(self.notification, "recipient", [])
        )
        if is_recipient:
            return True

        group_resolver = getattr(adapter, "get_user_group_ids_sync", None)
        if not callable(group_resolver):
            raise RuntimeError(
                "The configured identity adapter does not expose "
                "get_user_group_ids_sync(); use validate_permission_async() or "
                "implement the synchronous membership resolver."
            )
        user_group_ids = set(group_resolver(user))
        notification_group_ids = {
            adapter.get_group_id(group)
            for group in getattr(self.notification, "group", [])
        }
        return is_recipient or bool(user_group_ids.intersection(notification_group_ids))

    def validate_permission(self, user: Any, action: str) -> None:
        """Validate permission using already hydrated identity collections."""
        if not self.user_has_permission(user):
            self._raise_permission_error(user, action)
        self._validate_expiration(action)

    async def validate_permission_async(
        self, session: AsyncSession, user: Any, action: str
    ) -> None:
        """Validate permission using opaque IDs and the host identity adapter."""
        adapter = get_identity_adapter()
        user_id = adapter.get_user_id(user)

        recipient_result = await session.execute(
            select(NotificationRecipient.id).where(
                NotificationRecipient.notification_id == self.notification.id,
                NotificationRecipient.recipient_id == user_id,
            )
        )
        if recipient_result.scalar_one_or_none() is not None:
            self._validate_expiration(action)
            return

        group_ids = await adapter.get_user_group_ids(session, user)
        if group_ids:
            group_result = await session.execute(
                select(notification_group.c.notification_id).where(
                    notification_group.c.notification_id == self.notification.id,
                    notification_group.c.group_id.in_(list(group_ids)),
                )
            )
            if group_result.scalar_one_or_none() is not None:
                self._validate_expiration(action)
                return

        self._raise_permission_error(user, action)

    def _validate_expiration(self, action: str) -> None:
        """Prevent read-state changes after a notification expires."""
        if (
            action in {"mark as seen", "mark as unseen"}
            and getattr(self.notification, "is_expired", lambda: False)()
        ):
            raise PermissionError(f"An expired notification cannot be {action}.")

    def _raise_permission_error(self, user: Any, action: str) -> None:
        """Log and raise a consistent permission error."""
        adapter = get_identity_adapter()
        username = get_username(user)
        user_id = adapter.get_user_id(user)
        logging.warning(
            "User %s (ID: %s) tried to %s notification %s without permission.",
            username,
            user_id,
            action,
            self.notification.id,
        )
        raise PermissionError(
            f"Sorry! you don't have permission to {action} this notification."
        )
