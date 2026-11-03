"""Typed bridge for SQLAlchemy 2.x non-returning DML execution."""

from typing import Tuple, Union, cast

from sqlalchemy import CursorResult, Delete, Insert, Update
from sqlalchemy.ext.asyncio import AsyncSession


async def execute_dml(
    session: AsyncSession, statement: Union[Delete, Insert, Update]
) -> CursorResult[Tuple[object, ...]]:
    """Return the DBAPI cursor result for INSERT/UPDATE/DELETE without RETURNING.

    SQLAlchemy types AsyncSession.execute as Result for both SELECT and DML. Non-
    returning DML has a CursorResult at runtime, exposing its rowcount. The cast is
    isolated here; callers keep their real async session and transaction.
    """
    return cast(CursorResult[Tuple[object, ...]], await session.execute(statement))
