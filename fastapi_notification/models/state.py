"""Concurrency-safe persistence helpers for per-user notification state."""

from typing import Any, Mapping, Sequence, Tuple, Type, Union

from sqlalchemy import Integer, select, true
from sqlalchemy.dialects.mysql import Insert as MySQLInsert
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import Insert as PostgreSQLInsert
from sqlalchemy.dialects.sqlite import Insert as SQLiteInsert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import CompoundSelect, Select

from fastapi_notification.utils.sqlalchemy import execute_dml


def _dialect_insert(
    session: AsyncSession, model: Type[Any]
) -> Union[SQLiteInsert, PostgreSQLInsert, None]:
    """Return a dialect-specific INSERT supporting ON CONFLICT, if available."""
    dialect_name = session.get_bind().dialect.name
    if dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return sqlite_insert(model)
    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as postgresql_insert

        return postgresql_insert(model)
    return None


def _existing_row_statement(
    session: AsyncSession, model: Type[Any], criteria: Sequence[Any]
) -> Any:
    """Build a duplicate lookup, using a current read on MySQL-family engines."""
    statement = select(model).where(*criteria)
    if session.get_bind().dialect.name in {"mysql", "mariadb"}:
        # InnoDB REPEATABLE READ can hide a concurrently committed duplicate
        # from a snapshot read. A shared current read also avoids upgrading the
        # shared duplicate-key lock left by the portable savepoint fallback.
        statement = statement.with_for_update(read=True)
    return statement


def _mysql_insert(
    session: AsyncSession, model: Type[Any], values: Mapping[str, Any]
) -> Union[MySQLInsert, None]:
    """Build a no-op duplicate update for an auto-increment integer primary key."""
    if session.get_bind().dialect.name != "mysql":
        return None
    primary_key = model.__table__.autoincrement_column
    if primary_key is None or not isinstance(primary_key.type, Integer):
        return None
    # Acquire the duplicate row's exclusive lock during INSERT, rather than
    # upgrading shared locks concurrently after an IntegrityError. Do not assign
    # LAST_INSERT_ID(id): the unchanged-row lastrowid=0 identifies a duplicate.
    return (
        mysql_insert(model)
        .values(**dict(values))
        .on_duplicate_key_update({primary_key.key: primary_key})
    )


async def _mysql_insert_or_existing(
    session: AsyncSession,
    model: Type[Any],
    values: Mapping[str, Any],
    criteria: Sequence[Any],
) -> Union[Tuple[Any, bool], None]:
    """Serialize MySQL duplicate writes without ending the caller's transaction."""
    statement = _mysql_insert(session, model, values)
    if statement is None:
        return None
    result = await execute_dml(session, statement)
    existing_result = await session.execute(
        _existing_row_statement(session, model, criteria)
    )
    existing = existing_result.scalar_one_or_none()
    if existing is None:
        # A different unique constraint must not silently suppress an insert.
        raise IntegrityError(
            str(statement),
            dict(values),
            ValueError("Conflicting row does not match the requested natural key."),
        )
    return existing, bool(result.lastrowid)


async def insert_if_absent(
    session: AsyncSession,
    model: Type[Any],
    values: Mapping[str, Any],
    unique_columns: Sequence[str],
) -> Tuple[Any, bool]:
    """Atomically insert a row or return the row that already exists.

    SQLite and PostgreSQL use their native ``ON CONFLICT DO NOTHING`` support.
    MySQL uses a native no-op duplicate update for auto-increment integer keys;
    other models and dialects use a savepoint and the database unique constraint.
    MySQL-family duplicate recovery uses shared current reads to avoid stale
    repeatable-read snapshots. The caller retains ownership of the
    outer transaction; this helper never commits or rolls it back.

    Returns:
        A tuple containing the persisted ORM instance and whether this call
        inserted it.

    Raises:
        RuntimeError: If a completed insert cannot be retrieved.
        IntegrityError: If the insert fails for a reason other than a duplicate
            natural key, or if the conflicting row cannot be found afterwards.
    """
    criteria = [getattr(model, column) == values[column] for column in unique_columns]
    mysql_result = await _mysql_insert_or_existing(session, model, values, criteria)
    if mysql_result is not None:
        return mysql_result
    dialect_statement = _dialect_insert(session, model)

    if dialect_statement is not None:
        statement = dialect_statement.values(**dict(values)).on_conflict_do_nothing(
            index_elements=[getattr(model, column) for column in unique_columns]
        )
        result = await execute_dml(session, statement)
        inserted = result.rowcount == 1
    else:
        instance = model(**dict(values))
        try:
            async with session.begin_nested():
                session.add(instance)
                await session.flush()
            inserted = True
        except IntegrityError:
            existing_result = await session.execute(
                _existing_row_statement(session, model, criteria)
            )
            existing = existing_result.scalar_one_or_none()
            if existing is None:
                raise
            return existing, False

    existing_result = await session.execute(select(model).where(*criteria))
    existing = existing_result.scalar_one_or_none()
    if existing is None:
        raise RuntimeError(
            f"{model.__name__} insert completed without a retrievable row."
        )
    return existing, inserted


async def insert_many_from_select_if_absent(
    session: AsyncSession,
    model: Type[Any],
    column_names: Sequence[str],
    source: Union[Select, CompoundSelect],
    unique_columns: Sequence[str],
) -> int:
    """Insert rows selected by ``source`` without duplicate-key races.

    On SQLite and PostgreSQL the entire operation is one atomic
    ``INSERT ... SELECT ... ON CONFLICT DO NOTHING`` statement. Other dialects
    use the savepoint-backed single-row helper. The returned count is the number
    of rows newly inserted by this call, not the number of candidate rows.
    """
    dialect_statement = _dialect_insert(session, model)
    if dialect_statement is not None:
        # SQLAlchemy needs a plain SELECT to append Python-side column defaults.
        if isinstance(source, CompoundSelect):
            source = select(*source.subquery().c)
        # SQLite also needs a WHERE clause to disambiguate ON CONFLICT syntax.
        if session.get_bind().dialect.name == "sqlite":
            source = source.where(true())
        statement = dialect_statement.from_select(list(column_names), source)
        statement = statement.on_conflict_do_nothing(
            index_elements=[getattr(model, column) for column in unique_columns]
        )
        result = await execute_dml(session, statement)
        return max(int(result.rowcount or 0), 0)

    inserted_count = 0
    async with session.begin_nested():
        source_result = await session.execute(source)
        for row in source_result.all():
            values = dict(zip(column_names, row))
            _, inserted = await insert_if_absent(session, model, values, unique_columns)
            inserted_count += int(inserted)
    return inserted_count


__all__ = ["insert_if_absent", "insert_many_from_select_if_absent"]
