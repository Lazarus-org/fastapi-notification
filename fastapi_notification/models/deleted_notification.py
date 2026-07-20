from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.models.base import Base, utcnow
from fastapi_notification.models.permissions.notification_permission import (
    NotificationPermission,
)
from fastapi_notification.utils.loading import ensure_loaded
from fastapi_notification.utils.user_model import get_username


class DeletedNotification(Base):
    """A record of a notification having been soft deleted by a user.

    Soft deletions are stored rather than applied, so a notification can stay
    available to its other recipients and remain auditable or restorable.

    Attributes:
        notification_id (int): The notification that was soft deleted.
        user_id (int): The user who deleted it.
        deleted_at (datetime): When the notification was deleted.

    """

    __tablename__ = "deleted_notifications"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "notification_id", name="deleted_notification_unique"
        ),
        Index("deleted_notification_user_idx", "notification_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notification.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __str__(self) -> str:
        """Return a description of the deletion record.

        Returns:
            str: A representation naming the notification and the deleting user.

        """
        user = getattr(self, "user", None)
        notification = getattr(self, "notification", None)
        username = get_username(user) if user is not None else "Unknown"
        user_id = user.id if user is not None else self.user_id
        return f"{notification} deleted by {username} (ID: {user_id})"

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        notification: Any,
        user: Any,
        deleted_at: Optional[datetime] = None,
    ) -> "DeletedNotification":
        """Record that a user has soft deleted a notification.

        Args:
            session (AsyncSession): The session used to write.
            notification (Any): The notification being deleted.
            user (Any): The user performing the deletion.
            deleted_at (Optional[datetime]): When it was deleted. Defaults to
                now.

        Returns:
            DeletedNotification: The persisted deletion record.

        Raises:
            PermissionError: If the user is not allowed to delete the
                notification.

        """
        await ensure_loaded(session, user, "groups")
        NotificationPermission(notification).validate_permission(user, "delete")

        instance = cls(
            notification_id=notification.id,
            user_id=user.id,
            deleted_at=deleted_at or utcnow(),
        )
        session.add(instance)
        await session.flush()
        return instance
