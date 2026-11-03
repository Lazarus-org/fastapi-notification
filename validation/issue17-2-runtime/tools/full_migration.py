import asyncio
import json
import sys
import uuid
from contextlib import redirect_stderr, redirect_stdout
from getpass import getpass
from pathlib import Path

import asyncpg
import pymysql
from migration_check import check_migration
from sqlalchemy.engine import URL

root = Path(__file__).resolve().parents[3]
out = root / "validation/issue17-2-runtime"
backend = sys.argv[1]
name = "notification_validation_17_2_" + uuid.uuid4().hex[:10]
password = (
    getpass("PostgreSQL password (hidden): ")
    if backend == "postgresql"
    else "notification"
)
if backend == "postgresql":

    async def provision():
        connection = await asyncpg.connect(
            host="127.0.0.1", user="postgres", password=password, database="postgres"
        )
        try:
            await connection.execute(
                f"CREATE DATABASE \"{name}\" TEMPLATE template0 ENCODING 'UTF8'"
            )
        finally:
            await connection.close()

    asyncio.run(provision())
    url = URL.create(
        "postgresql+asyncpg",
        username="postgres",
        password=password,
        host="127.0.0.1",
        port=5432,
        database=name,
    )
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
        cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
        cursor.execute(
            f"GRANT ALL PRIVILEGES ON `{name}`.* TO 'notification'@'localhost'"
        )
    connection.close()
    url = URL.create(
        "mysql+aiomysql",
        username="notification",
        password=password,
        host="127.0.0.1",
        port=33306,
        database=name,
        query={"charset": "utf8mb4"},
    )
rendered = url.render_as_string(hide_password=False)


class Redact:
    def __init__(self, stream):
        self.stream = stream

    def write(self, value):
        return self.stream.write(
            value.replace(rendered, "<database URL>").replace(password, "<redacted>")
        )

    def flush(self):
        self.stream.flush()


label = backend + "-migration-full"
with (out / (label + ".log")).open("w", encoding="utf-8") as stream:
    with redirect_stdout(Redact(stream)), redirect_stderr(Redact(stream)):
        asyncio.run(check_migration(url, label))
print(backend, "actual Issue 17.1 schema -> Alembic upgrade/downgrade: PASS")
