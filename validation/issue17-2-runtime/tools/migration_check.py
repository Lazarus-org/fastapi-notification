"""Exercise Alembic's actual version table and data migration on a disposable DB."""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[3]
TARGET = (
    ROOT / "fastapi-notification"
    if (ROOT / "fastapi-notification/pyproject.toml").is_file()
    else ROOT
)
OUT = ROOT / "validation/issue17-2-runtime"


async def check_migration(url, label):
    engine = create_async_engine(url)
    assert engine.url.database.startswith("notification_validation_17_2_")
    scratch = ROOT / ".validation-cache/issue17-2-alembic"
    scratch.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="alembic-", dir=scratch))
    (directory / "versions").mkdir()
    revision = TARGET / "migrations/versions/20261103_digest_claim_ownership.py"
    for source in revision.parent.glob("*.py"):
        shutil.copyfile(source, directory / "versions" / source.name)
    (directory / "env.py").write_text(
        'from alembic import context\nconnection=context.config.attributes["connection"]\ncontext.configure(connection=connection)\nwith context.begin_transaction():\n    context.run_migrations()\n',
        encoding="utf-8",
    )
    config = Config()
    config.set_main_option("script_location", str(directory))
    spec = importlib.util.spec_from_file_location("ownership_revision", revision)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = {
        "revision": module.revision,
        "revision_length": len(module.revision),
        "engine": engine.dialect.name,
        "database": engine.url.database,
        "uses_alembic_version_table": True,
    }

    full_legacy = "-full" in label
    if full_legacy:
        legacy = subprocess.run(
            [
                str(ROOT / ".validation-venv/Scripts/python.exe"),
                str(
                    ROOT / "validation/issue17-2-runtime/tools/create_legacy_schema.py"
                ),
            ],
            input=json.dumps({"url": url.render_as_string(hide_password=False)}),
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        print(legacy.stdout)
        assert legacy.returncode == 0, legacy.stderr
        result["legacy_schema"] = (
            "actual committed Issue 17.1 Base and AuthBase metadata"
        )

    def scenario(connection):
        assert bool(sa.inspect(connection).get_table_names()) == full_legacy
        connection.commit()
        metadata = sa.MetaData()
        table = sa.Table(
            "notification_digest_batch",
            metadata,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("claimed_at", sa.DateTime, nullable=True),
            sa.Column("last_error", sa.Text, nullable=True),
            sa.Column("retained_payload", sa.String(40), nullable=False),
            sa.CheckConstraint(
                "status IN ('pending','processing','sent','failed')",
                name="check_fixture_status",
            ),
            sa.Index("ix_fixture_status", "status"),
        )
        if full_legacy:
            connection.exec_driver_sql(
                "ALTER TABLE notification_digest_batch ADD COLUMN retained_payload VARCHAR(40)"
            )
            table = sa.Table(
                "notification_digest_batch", sa.MetaData(), autoload_with=connection
            )
        else:
            metadata.create_all(connection)
        before_indexes = {
            item["name"] for item in sa.inspect(connection).get_indexes(table.name)
        }
        before_checks = {
            item["name"]
            for item in sa.inspect(connection).get_check_constraints(table.name)
        }
        seed = [
            {
                "id": 1,
                "status": "processing",
                "claimed_at": datetime(2026, 11, 3, 1),
                "last_error": "synthetic provider secret",
                "retained_payload": "first",
            },
            {
                "id": 2,
                "status": "failed",
                "claimed_at": None,
                "last_error": None,
                "retained_payload": "second",
            },
            {
                "id": 3,
                "status": "sent",
                "claimed_at": None,
                "last_error": "",
                "retained_payload": "third",
            },
        ]
        if full_legacy:
            instant = datetime(2026, 11, 3, 1, tzinfo=timezone.utc)
            for row in seed:
                row.update(
                    schedule_id=None,
                    user_id="migration-user",
                    channel="email",
                    scheduled_for=instant,
                    period_start=instant,
                    period_end=instant,
                    attempts=1,
                    available_at=instant,
                    created_at=instant,
                    sent_at=None,
                )
                if row["claimed_at"] is not None:
                    row["claimed_at"] = row["claimed_at"].replace(tzinfo=timezone.utc)
        connection.execute(table.insert(), seed)
        connection.commit()
        config.attributes["connection"] = connection
        try:
            command.upgrade(config, module.revision)
            connection.commit()
            columns = {
                c["name"]: c for c in sa.inspect(connection).get_columns(table.name)
            }
            assert (
                "last_error" not in columns
                and {"claim_token", "last_error_code"} <= columns.keys()
            )
            assert (
                columns["claim_token"]["type"].length == 36
                and columns["last_error_code"]["type"].length == 64
            )
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == module.revision
            )
            rows = (
                connection.execute(
                    sa.text(
                        "SELECT id,status,claimed_at,claim_token,last_error_code,retained_payload FROM notification_digest_batch ORDER BY id"
                    )
                )
                .mappings()
                .all()
            )
            assert (
                rows[0]["status"] == "pending"
                and rows[0]["claimed_at"] is None
                and rows[0]["claim_token"] is None
            )
            assert (
                rows[0]["last_error_code"] == "delivery_failed"
                and rows[1]["last_error_code"] is None
            )
            assert [r["retained_payload"] for r in rows] == ["first", "second", "third"]
            assert {
                i["name"] for i in sa.inspect(connection).get_indexes(table.name)
            } == before_indexes
            assert {
                i["name"]
                for i in sa.inspect(connection).get_check_constraints(table.name)
            } == before_checks
            result["upgraded_rows"] = [dict(row) for row in rows]
            connection.commit()
            command.downgrade(config, "base")
            connection.commit()
            columns = {
                c["name"] for c in sa.inspect(connection).get_columns(table.name)
            }
            assert (
                "last_error" in columns
                and not {"claim_token", "last_error_code"} & columns
            )
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT last_error FROM notification_digest_batch WHERE id=1"
                    )
                )
                == "delivery_failed"
            )
            assert (
                connection.scalar(sa.text("SELECT COUNT(*) FROM alembic_version")) == 0
            )
            result.update(
                status="PASS",
                upgrade="PASS",
                downgrade="PASS",
                data_sanitization="PASS",
                lease_reset="PASS",
                unrelated_data_and_index_preserved=True,
            )
        except Exception as exc:
            connection.rollback()
            result.update(
                status="FAIL",
                error_type=type(exc).__name__,
                error=str(exc),
                post_failure_columns=[
                    c["name"] for c in sa.inspect(connection).get_columns(table.name)
                ],
            )
            raise
        finally:
            connection.rollback()
            cleanup = sa.MetaData()
            cleanup.reflect(connection)
            cleanup.drop_all(connection)
            connection.commit()

    try:
        async with engine.connect() as connection:
            await connection.run_sync(scenario)
    finally:
        await engine.dispose()
        (OUT / (label + ".json")).write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
