"""Execute the reference migration only on the selected disposable test database."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine


def _revision() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[3]
        / "migrations/versions/20261103_mysql_identity_precision.py"
    )
    spec = importlib.util.spec_from_file_location("mysql_reference_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migrate(connection: Connection, downgrade: bool = False) -> None:
    revision = _revision()
    with Operations.context(MigrationContext.configure(connection)):
        if downgrade:
            revision.downgrade()
        else:
            revision.upgrade()


async def test_reference_migration_round_trip(engine: AsyncEngine) -> None:
    """Legacy schema upgrades and empty rollback preserve metadata constraints."""

    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: _migrate(sync, True))
        await connection.run_sync(_migrate)
        if engine.dialect.name == "mysql":
            collation = await connection.scalar(
                text(
                    "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='notification_recipient' "
                    "AND COLUMN_NAME='recipient_id'"
                )
            )
            assert collation == "utf8mb4_0900_bin"
            columns = await connection.run_sync(
                lambda sync: inspect(sync).get_columns("notification")
            )
            temporal = next(
                column["type"] for column in columns if column["name"] == "expires_at"
            )
            assert isinstance(temporal, DATETIME)
            assert temporal.fsp == 6
        await connection.run_sync(lambda sync: _migrate(sync, True))
        await connection.run_sync(_migrate)


@pytest.mark.parametrize("precision_loss", [False, True])
async def test_mysql_rollback_refuses_data_loss_before_any_ddl(
    engine: AsyncEngine, precision_loss: bool
) -> None:
    if engine.dialect.name != "mysql":
        pytest.skip("Requires actual MySQL collation and temporal DDL")
    async with engine.begin() as connection:
        await connection.run_sync(_migrate)
        for identity in ["HostUser"] if precision_loss else ["HostUser", "hostuser"]:
            await connection.execute(
                text(
                    "INSERT INTO notification_preference "
                    "(user_id, category, channel, enabled, updated_at) "
                    "VALUES (:identity, 'orders', 'email', 1, :instant)"
                ),
                {
                    "identity": identity,
                    "instant": (
                        "2030-01-02 03:04:05.123456"
                        if precision_loss
                        else "2030-01-02 03:04:05"
                    ),
                },
            )
        with pytest.raises(
            RuntimeError,
            match="lose microseconds" if precision_loss else "alias identifiers",
        ):
            await connection.run_sync(lambda sync: _migrate(sync, True))
        # recipient is the first proposed ALTER; a preflight rejection must leave it intact.
        assert (
            await connection.scalar(
                text(
                    "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='notification_recipient' "
                    "AND COLUMN_NAME='recipient_id'"
                )
            )
            == "utf8mb4_0900_bin"
        )
        assert await connection.scalar(
            text("SELECT COUNT(*) FROM notification_preference")
        ) == (1 if precision_loss else 2)
