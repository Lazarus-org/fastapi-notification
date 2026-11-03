"""Persistence model for notification creation idempotency keys."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.models.base import Base, UTCDateTime, utcnow
from fastapi_notification.models.column_types import opaque_identifier


class NotificationDeduplication(Base):
    """Map a scoped idempotency key to the notification created for that event.

    A key remains active until ``expires_at``. A NULL expiry means the key is retained
    for as long as its notification exists. Reusing an active key returns the original
    notification without changing its content or audience. Once a key expires, a new
    notification may atomically claim the same key.
    """

    __tablename__ = "notification_deduplication"
    __table_args__ = (
        UniqueConstraint(
            "scope",
            "deduplication_key",
            name="notification_deduplication_scope_key_unique",
        ),
        UniqueConstraint(
            "notification_id", name="notification_deduplication_notification_unique"
        ),
        Index("notification_deduplication_expiry_idx", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(opaque_identifier(), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(opaque_identifier(), nullable=False)
    notification_id: Mapped[int] = mapped_column(
        ForeignKey("notification.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow
    )


__all__ = ["NotificationDeduplication"]
