from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """Return the current time as a timezone aware UTC datetime.

    This is the package wide replacement for ``django.utils.timezone.now`` and is
    used as the default for every timestamp column.

    Returns:
        datetime: The current moment in UTC.

    """
    return datetime.now(timezone.utc)


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
