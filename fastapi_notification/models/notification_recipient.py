from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.models.base import Base
from fastapi_notification.utils.username import get_username


class NotificationRecipient(Base):
    """The association between a notification and one of its recipients.

    Attributes:
        notification_id (int): The notification being delivered.
        recipient_id (str): The host user identifier receiving the notification.
    """

    __tablename__ = "notification_recipient"
    __table_args__ = (
        UniqueConstraint(
            "recipient_id", "notification_id", name="notification_recipient_unique"
        ),
        Index("notification_recipient_idx", "notification_id", "recipient_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notification.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[str] = mapped_column(String(255), nullable=False)

    def __str__(self) -> str:
        """Return a description of the recipient association.

        Returns:
            str: A representation naming the notification and the recipient.
        """
        notification = getattr(self, "notification", None)
        recipient = getattr(self, "recipient", None)
        username = get_username(recipient) if recipient is not None else "Unknown"
        recipient_id = (
            get_identity_adapter().get_user_id(recipient)
            if recipient is not None
            else self.recipient_id
        )
        return (
            f"Notification: {notification}, Recipient: {username} (ID: {recipient_id})"
        )
