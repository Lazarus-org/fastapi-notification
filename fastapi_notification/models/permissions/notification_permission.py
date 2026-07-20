import logging
from typing import Any

from fastapi_notification.utils.user_model import get_username


class NotificationPermission:
    """Determines whether a user may act on a notification.

    Encapsulating the permission logic here keeps it in one place and reusable
    across the models, the data access layer and the API routes.

    Attributes:
        notification (Notification): The notification to check permissions for.

    """

    def __init__(self, notification: Any) -> None:
        self.notification = notification

    def user_has_permission(self, user: Any) -> bool:
        """Check whether the user is a recipient, in a targeted group, or staff.

        The notification's ``recipient`` and ``group`` collections, and the
        user's ``groups`` collection, are eagerly loaded, so this check runs
        without emitting further queries.

        Args:
            user (Any): The user to check.

        Returns:
            bool: Whether the user has permission or not.

        """
        is_recipient = any(
            recipient.id == user.id for recipient in self.notification.recipient
        )

        user_group_ids = {group.id for group in user.groups}
        is_in_group = any(
            group.id in user_group_ids for group in self.notification.group
        )

        return is_recipient or is_in_group or user.is_staff

    def validate_permission(self, user: Any, action: str) -> None:
        """Validate that the user may perform an action on the notification.

        Args:
            user (Any): The user to validate.
            action (str): The action to be performed (e.g. ``"mark as seen"``,
                ``"delete"``).

        Raises:
            PermissionError: If the user does not have permission.

        """
        if not self.user_has_permission(user):
            username = get_username(user)
            logging.warning(
                "User %s (ID: %s) tried to %s notification %s without permission.",
                username,
                user.id,
                action,
                self.notification.id,
            )
            raise PermissionError(
                f"Sorry! you don't have permission to {action} this notification."
            )
