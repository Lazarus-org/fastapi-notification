"""Per-user notification delivery preferences."""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.models.base import Base, UTCDateTime, utcnow
from fastapi_notification.models.column_types import opaque_identifier

_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")


def normalize_preference_key(value: str, *, allow_wildcard: bool = False) -> str:
    """Normalize and validate a category/channel preference key."""
    if not isinstance(value, str):
        raise TypeError("Preference keys must be strings.")
    normalized = value.strip().lower()
    if allow_wildcard and normalized == "*":
        return normalized
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Preference keys must start with a letter or digit and contain at most "
            "64 lowercase letters, digits, dots, underscores or hyphens."
        )
    return normalized


class NotificationPreference(Base):
    """A user's opt-in/opt-out rule for a category and delivery channel.

    ``*`` is supported as a category or channel wildcard. More-specific rules override
    less-specific rules. Missing rules default to enabled.
    """

    __tablename__ = "notification_preference"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category", "channel", name="notification_preference_unique"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(opaque_identifier(), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"NotificationPreference(user_id={self.user_id!r}, "
            f"category={self.category!r}, channel={self.channel!r}, "
            f"enabled={self.enabled!r})"
        )


__all__ = ["NotificationPreference", "normalize_preference_key"]
