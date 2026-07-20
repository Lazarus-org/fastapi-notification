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


class Base(DeclarativeBase):
    """Declarative base shared by every model in the package.

    Host applications that already own a declarative base can rebind the package
    models onto it, but the common case is to let ``fastapi-notification`` create
    its own tables from this metadata.

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
