from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.models.base import Base, utcnow
from fastapi_notification.models.permissions.notification_permission import (
    NotificationPermission,
)
from fastapi_notification.models.state import insert_if_absent
from fastapi_notification.utils.username import get_username


class NotificationSeen(Base):
    """A record of a user having seen a specific notification.

    Attributes:
        notification_id (int): The notification that was seen.
        user_id (str): The host user identifier who saw the notification.
        seen_at (datetime): When the notification was marked as seen.

    Usage Example:
        Use :meth:`create` so the user's permission to view the notification is
        validated before the record is written::

            seen = await NotificationSeen.create(session, notification, user)

    """

    __tablename__ = "notification_seen"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="notification_seen_unique"),
        Index("notification_seen_user_idx", "notification_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notification.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __str__(self) -> str:
        """Return a description of the seen record.

        Returns:
            str: A representation naming the user and the notification.
        """
        user = getattr(self, "user", None)
        notification = getattr(self, "notification", None)
        username = get_username(user) if user is not None else "Unknown"
        user_id = (
            get_identity_adapter().get_user_id(user)
            if user is not None
            else self.user_id
        )
        return f"{username} (ID: {user_id}) has seen ({notification})"

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        notification: Any,
        user: Any,
        seen_at: Optional[datetime] = None,
    ) -> "NotificationSeen":
        """Record that a user has seen a notification.

        Args:
            session (AsyncSession): The session used to write.
            notification (Any): The notification that was seen.
            user (Any): The user who saw it.
            seen_at (Optional[datetime]): When it was seen. Defaults to now.

        Returns:
            NotificationSeen: The persisted seen record.

        Raises:
            PermissionError: If the user is not allowed to see the notification.
        """
        await NotificationPermission(notification).validate_permission_async(
            session, user, "mark as seen"
        )

        instance, _ = await insert_if_absent(
            session,
            cls,
            {
                "notification_id": notification.id,
                "user_id": get_identity_adapter().get_user_id(user),
                "seen_at": seen_at or utcnow(),
            },
            ("notification_id", "user_id"),
        )
        return instance
