"""Runtime tests for the reference digest claim ownership migration."""

import importlib.util
import shutil
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    inspect,
    text,
)


def test_digest_claim_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    """Upgrade sanitizes old errors and resets leases; downgrade restores schema."""
    repository_root = Path(__file__).resolve().parents[3]
    migration_path = (
        repository_root
        / "migrations"
        / "versions"
        / "20261103_digest_claim_ownership.py"
    )
    spec = importlib.util.spec_from_file_location(
        "digest_claim_ownership_migration", migration_path
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    versions = tmp_path / "versions"
    versions.mkdir()
    for source in migration_path.parent.glob("*.py"):
        shutil.copyfile(source, versions / source.name)
    (tmp_path / "env.py").write_text(
        "from alembic import context\n"
        'connection = context.config.attributes["connection"]\n'
        "context.configure(connection=connection)\n"
        "with context.begin_transaction():\n"
        "    context.run_migrations()\n",
        encoding="utf-8",
    )
    config = Config()
    config.set_main_option("script_location", str(tmp_path))
    engine = create_engine("sqlite://")
    metadata = MetaData()
    batch_table = Table(
        "notification_digest_batch",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("status", String(16), nullable=False),
        Column("claimed_at", DateTime, nullable=True),
        Column("last_error", Text, nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            batch_table.insert(),
            [
                {
                    "id": 1,
                    "status": "processing",
                    "claimed_at": None,
                    "last_error": "provider response contained secret data",
                },
                {
                    "id": 2,
                    "status": "failed",
                    "claimed_at": None,
                    "last_error": None,
                },
            ],
        )
        config.attributes["connection"] = connection
        command.upgrade(config, migration.revision)
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == migration.revision
        )
        version_type = next(
            column["type"]
            for column in inspect(connection).get_columns("alembic_version")
            if column["name"] == "version_num"
        )
        assert isinstance(version_type, String) and version_type.length is not None
        assert len(migration.revision) <= version_type.length

        columns = {
            column["name"]
            for column in inspect(connection).get_columns("notification_digest_batch")
        }
        assert "claim_token" in columns
        assert "last_error_code" in columns
        assert "last_error" not in columns
        upgraded = connection.execute(
            text(
                "SELECT status, claimed_at, last_error_code "
                "FROM notification_digest_batch WHERE id = 1"
            )
        ).one()
        assert upgraded.status == "pending"
        assert upgraded.claimed_at is None
        assert upgraded.last_error_code == "delivery_failed"

        command.downgrade(config, "base")
        assert connection.scalar(text("SELECT COUNT(*) FROM alembic_version")) == 0

        columns = {
            column["name"]
            for column in inspect(connection).get_columns("notification_digest_batch")
        }
        assert "last_error" in columns
        assert "claim_token" not in columns
        assert "last_error_code" not in columns
        downgraded = connection.execute(
            text("SELECT last_error FROM notification_digest_batch WHERE id = 1")
        ).one()
        assert downgraded.last_error == "delivery_failed"

    engine.dispose()
