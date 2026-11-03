"""Remove only empty, UUID-named disposable databases created by this campaign."""

import asyncio
import json
import sys
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path

import asyncpg
import pymysql

root = Path(__file__).resolve().parents[3]
out = root / "validation/issue17-2-runtime"
backend = sys.argv[1]
names = set()
for path in [
    *out.glob(backend + "-server*.json"),
    *out.glob(backend + "-migration*.json"),
]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "database" in data:
        names.add(data["database"])
assert names and all(
    name.startswith("notification_validation_17_2_") and name.replace("_", "").isalnum()
    for name in names
)
if backend == "postgresql":
    password = getpass("PostgreSQL password for disposable-database cleanup (hidden): ")

    async def cleanup():
        admin = await asyncpg.connect(
            host="127.0.0.1", user="postgres", password=password, database="postgres"
        )
        try:
            for name in sorted(names):
                connection = await asyncpg.connect(
                    host="127.0.0.1", user="postgres", password=password, database=name
                )
                try:
                    assert (
                        await connection.fetchval(
                            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
                        )
                        == 0
                    )
                finally:
                    await connection.close()
                await admin.execute(f'DROP DATABASE "{name}"')
        finally:
            await admin.close()

    asyncio.run(cleanup())
    stopped = False
else:
    connection = pymysql.connect(host="127.0.0.1", port=33306, user="root", password="")
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@datadir,@@port")
        directory, port = cursor.fetchone()
        assert (
            Path(directory).resolve()
            == (root / ".validation-mysql/data-issue17-1").resolve()
            and port == 33306
        )
        for name in sorted(names):
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s",
                (name,),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                f"REVOKE ALL PRIVILEGES ON `{name}`.* FROM 'notification'@'localhost'"
            )
            cursor.execute(f"DROP DATABASE `{name}`")
        cursor.execute("SHUTDOWN")
    connection.close()
    stopped = True
record = {
    "dropped_empty_disposable_databases": sorted(names),
    "workspace_mysql_shutdown_acknowledged": stopped,
    "existing_postgresql_service_stopped": False,
    "completed_utc": datetime.now(timezone.utc).isoformat(),
}
(out / (backend + "-cleanup.json")).write_text(
    json.dumps(record, indent=2), encoding="utf-8"
)
print(backend, "cleanup complete:", len(names), "empty disposable databases removed.")
