"""Per-user quiet-hour rules for notification delivery."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Boolean, CheckConstraint, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.models.base import Base, UTCDateTime, utcnow


def validate_timezone(value: str) -> str:
    """Validate and return an IANA timezone name."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timezone must be a non-empty IANA timezone name.")
    value = value.strip()
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown IANA timezone: {value}") from exc
    return value


class NotificationQuietHours(Base):
    """A user's recurring local-time quiet window for one delivery channel."""

    __tablename__ = "notification_quiet_hours"
    __table_args__ = (
        UniqueConstraint("user_id", "channel", name="notification_quiet_hours_unique"),
        CheckConstraint(
            "start_time <> end_time", name="ck_notification_quiet_hours_window"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_urgent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"NotificationQuietHours(user_id={self.user_id!r}, "
            f"channel={self.channel!r}, enabled={self.enabled!r})"
        )


__all__ = ["NotificationQuietHours", "validate_timezone"]
