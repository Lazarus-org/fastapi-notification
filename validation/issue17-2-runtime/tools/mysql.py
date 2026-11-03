import asyncio
import json
import sys
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import pymysql
import pytest
from migration_check import check_migration
from sqlalchemy.engine import URL

root = Path(__file__).resolve().parents[3]
out = root / "validation/issue17-2-runtime"
name = "notification_validation_17_2_" + uuid.uuid4().hex[:10]
connection = pymysql.connect(host="127.0.0.1", port=33306, user="root", password="")
with connection.cursor() as cursor:
    cursor.execute(
        "SELECT @@datadir,@@port,VERSION(),@@transaction_isolation,@@sql_mode"
    )
    directory, port, version, isolation, sql_mode = cursor.fetchone()
    assert (
        Path(directory).resolve()
        == (root / ".validation-mysql/data-issue17-1").resolve()
        and port == 33306
    )
    assert (
        version.startswith("8.4.")
        and isolation == "REPEATABLE-READ"
        and "ONLY_FULL_GROUP_BY" in sql_mode
    )
    cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
    cursor.execute(f"GRANT ALL PRIVILEGES ON `{name}`.* TO 'notification'@'localhost'")
connection.close()
url = URL.create(
    "mysql+aiomysql",
    username="notification",
    password="notification",
    host="127.0.0.1",
    port=33306,
    database=name,
    query={"charset": "utf8mb4"},
)
(out / "mysql-server.json").write_text(
    json.dumps(
        {
            "version": version,
            "database": name,
            "data_directory": directory,
            "port": port,
            "isolation": isolation,
            "sql_mode": sql_mode,
            "disposable": True,
        },
        indent=2,
    ),
    encoding="utf-8",
)


class Configure:
    def pytest_configure(self, config):
        config.option.database_url = url.render_as_string(hide_password=False)


started = datetime.now(timezone.utc)
with (out / "mysql-independent.log").open("w", encoding="utf-8") as stream:
    with redirect_stdout(stream), redirect_stderr(stream):
        code = pytest.main(
            [
                "fastapi_notification/tests/repository/test_state_concurrency.py",
                "fastapi_notification/tests/scheduling/test_scheduling_dal.py",
                "--no-cov",
                "-q",
                "-o",
                "cache_dir=" + str(root / ".validation-cache/pytest-17-2-mysql"),
                "--basetemp=" + str(root / ".validation-cache/17-2-mysql"),
                "--junitxml=" + str(out / "mysql-independent.xml"),
            ],
            plugins=[Configure()],
        )
(out / "mysql-independent.result.json").write_text(
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
print("MySQL independent-session/scheduling suite exit", int(code), flush=True)
label = sys.argv[1] if len(sys.argv) > 1 else "mysql-migration-initial"
with (out / (label + ".log")).open("w", encoding="utf-8") as stream:
    with redirect_stdout(stream), redirect_stderr(stream):
        try:
            asyncio.run(check_migration(url, label))
        except Exception:
            import traceback

            traceback.print_exc()
            print("Migration failed; see dedicated JSON result.")
print("MySQL Alembic execution finished.", flush=True)
