from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """Return the current time as a timezone aware UTC datetime.

    This is the package wide replacement for ``django.utils.timezone.now`` and is
    used as the default for every timestamp column.

    Returns:
        datetime: The current moment in UTC.

    """
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Store timezone-aware datetimes in UTC and restore UTC on every backend.

    SQLite's native ``DateTime(timezone=True)`` storage drops timezone metadata.
    This type decorator keeps the package's expiration contract consistent by
    normalizing bind values to UTC and attaching UTC to naive database results.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        """Normalize aware datetime values before persistence."""
        del dialect
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("UTCDateTime values must be datetime instances.")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime values must be timezone-aware.")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """Return loaded datetime values as timezone-aware UTC instants."""
        del dialect
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class AuthBase(DeclarativeBase):
    """Declarative base for optional built-in authentication example models."""


class Base(DeclarativeBase):
    """Declarative base for notification persistence models.

    The optional built-in authentication examples use :class:`AuthBase` and a
    separate metadata collection, so applications using their own identities do
    not create or depend on package-owned user and group tables.

    """

    def to_dict(self) -> Dict[str, Any]:
        """Return the mapped columns of the instance as a plain dictionary.

        Returns:
            Dict[str, Any]: A mapping of column name to column value.

        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns  # type: ignore[attr-defined]
        }
