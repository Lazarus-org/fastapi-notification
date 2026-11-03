import asyncio
import json
import sys
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

import asyncpg
import pytest
from migration_check import check_migration
from sqlalchemy.engine import URL

root = Path(__file__).resolve().parents[3]
out = root / "validation/issue17-2-runtime"
password = getpass("PostgreSQL password (hidden): ")
name = "notification_validation_17_2_" + uuid.uuid4().hex[:10]


async def provision():
    connection = await asyncpg.connect(
        host="127.0.0.1", user="postgres", password=password, database="postgres"
    )
    try:
        version = await connection.fetchval("SELECT version()")
        await connection.execute(
            f"CREATE DATABASE \"{name}\" TEMPLATE template0 ENCODING 'UTF8'"
        )
        return version
    finally:
        await connection.close()


version = asyncio.run(provision())
url = URL.create(
    "postgresql+asyncpg",
    username="postgres",
    password=password,
    host="127.0.0.1",
    port=5432,
    database=name,
)
rendered = url.render_as_string(hide_password=False)
(out / "postgresql-server.json").write_text(
    json.dumps({"version": version, "database": name, "disposable": True}, indent=2),
    encoding="utf-8",
)


class Configure:
    def pytest_configure(self, config):
        config.option.database_url = rendered


class Redact:
    def __init__(self, stream):
        self.stream = stream

    def write(self, value):
        return self.stream.write(
            value.replace(rendered, "<database URL>").replace(password, "<redacted>")
        )

    def flush(self):
        self.stream.flush()

    def isatty(self):
        return False


started = datetime.now(timezone.utc)
with (out / "postgresql-independent.log").open("w", encoding="utf-8") as stream:
    with redirect_stdout(Redact(stream)), redirect_stderr(Redact(stream)):
        code = pytest.main(
            [
                "fastapi_notification/tests/repository/test_state_concurrency.py",
                "fastapi_notification/tests/scheduling/test_scheduling_dal.py",
                "--no-cov",
                "-q",
                "-o",
                "cache_dir=" + str(root / ".validation-cache/pytest-17-2-pg"),
                "--basetemp=" + str(root / ".validation-cache/17-2-pg"),
                "--junitxml=" + str(out / "postgresql-independent.xml"),
            ],
            plugins=[Configure()],
        )
(out / "postgresql-independent.result.json").write_text(
    json.dumps(
        {
            "exit_code": int(code),
            "started_utc": started.isoformat(),
            "ended_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version,
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("PostgreSQL independent-session/scheduling suite exit", int(code), flush=True)
label = sys.argv[1] if len(sys.argv) > 1 else "postgresql-migration-initial"
with (out / (label + ".log")).open("w", encoding="utf-8") as stream:
    with redirect_stdout(Redact(stream)), redirect_stderr(Redact(stream)):
        try:
            asyncio.run(check_migration(url, label))
        except Exception:
            import traceback

            traceback.print_exc()
            print("Migration failed; see dedicated JSON result.")
print("PostgreSQL Alembic execution finished.", flush=True)
