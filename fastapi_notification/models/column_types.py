"""Portable types preserving opaque identifiers and temporal precision on MySQL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Protocol

from sqlalchemy import DateTime, String, Time
from sqlalchemy.dialects import mysql

if TYPE_CHECKING:

    class _VarcharFactory(Protocol):
        def __call__(self, length: int, *, charset: str, collation: str) -> String: ...


# SQLAlchemy's MySQL constructors lack annotations; isolate their typed contracts.
_varchar: _VarcharFactory = mysql.VARCHAR
_datetime: Callable[[bool, int], DateTime] = mysql.DATETIME
_time: Callable[[bool, int], Time] = mysql.TIME


def opaque_identifier() -> String:
    """Preserve case, accents and trailing spaces for host-owned identifiers."""
    return String(255).with_variant(
        _varchar(255, charset="utf8mb4", collation="utf8mb4_0900_bin"), "mysql"
    )


def precise_datetime() -> DateTime:
    """Keep UTCDateTime's accepted microseconds on MySQL."""
    return DateTime(timezone=True).with_variant(_datetime(False, 6), "mysql")


def precise_time() -> Time:
    """Keep local wall-clock microseconds on MySQL."""
    return Time().with_variant(_time(False, 6), "mysql")
