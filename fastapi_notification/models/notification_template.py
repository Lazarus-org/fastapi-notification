"""Database-backed, localized notification templates."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates

from fastapi_notification.models.base import Base, UTCDateTime, utcnow
from fastapi_notification.models.helper.enums import normalize_category
from fastapi_notification.utils.templates import validate_template

_TEMPLATE_KEY = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")
_LOCALE = re.compile(r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*$")


def normalize_template_key(value: str) -> str:
    """Validate and normalize a stable application event key."""
    if not isinstance(value, str):
        raise TypeError("template_key must be a string.")
    normalized = value.strip().lower()
    if not _TEMPLATE_KEY.fullmatch(normalized):
        raise ValueError("template_key must be a valid key of at most 128 characters.")
    return normalized


def normalize_locale(value: str) -> str:
    """Normalize a simple BCP-47 locale identifier."""
    if not isinstance(value, str):
        raise TypeError("locale must be a string.")
    normalized = value.strip().replace("_", "-")
    if not _LOCALE.fullmatch(normalized):
        raise ValueError("locale must be a valid language or language-region tag.")
    parts = normalized.split("-")
    normalized_parts = [parts[0].lower()]
    normalized_parts.extend(
        part.upper() if len(part) == 2 else part for part in parts[1:]
    )
    return "-".join(normalized_parts)


class NotificationTemplate(Base):
    """One localized version of a notification event template.

    The pair ``(key, locale)`` is unique. Rendered notifications retain their text
    snapshot and do not change when this record is later edited.
    """

    __tablename__ = "notification_template"
    __table_args__ = (
        UniqueConstraint(
            "key", "locale", name="notification_template_key_locale_unique"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    locale: Mapped[str] = mapped_column(String(35), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    verb_template: Mapped[str] = mapped_column(String(127), nullable=False)
    description_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow
    )

    @validates("key")
    def _validate_key(self, key: str, value: str) -> str:
        """Normalize template keys on direct ORM assignment."""
        del key
        return normalize_template_key(value)

    @validates("locale")
    def _validate_locale(self, key: str, value: str) -> str:
        """Normalize locale identifiers on direct ORM assignment."""
        del key
        return normalize_locale(value)

    @validates("category")
    def _validate_category(self, key: str, value: str) -> str:
        """Validate the category associated with a template."""
        del key
        return normalize_category(value)

    @validates("verb_template")
    def _validate_verb_template(self, key: str, value: str) -> str:
        """Validate template syntax and the notification verb column limit."""
        del key
        validate_template(value)
        if len(value) > 127:
            raise ValueError("verb_template must not exceed 127 characters.")
        return value

    @validates("description_template")
    def _validate_description_template(
        self, key: str, value: Optional[str]
    ) -> Optional[str]:
        """Validate optional description template syntax."""
        del key
        if value is not None:
            validate_template(value)
        return value

    def __repr__(self) -> str:
        return f"NotificationTemplate(key={self.key!r}, locale={self.locale!r})"


__all__ = ["NotificationTemplate", "normalize_locale", "normalize_template_key"]
