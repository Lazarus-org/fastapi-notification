"""Inspect fresh package schema on the verified workspace-owned MySQL server."""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path

import fastapi_notification
from fastapi_notification.models.base import AuthBase, Base
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

root = Path(__file__).resolve().parents[2]
out = root / "validation/issue17-1"
expected_data = (root / ".validation-mysql/data-issue17-1").resolve()


async def main():
    engine = create_async_engine("mysql+aiomysql://notification:notification@127.0.0.1:33306/notification_issue17_1?charset=utf8mb4")
    async with engine.connect() as connection:
        identity = (await connection.execute(text("SELECT @@datadir AS datadir, @@port AS port, @@session.transaction_isolation AS isolation_level, @@sql_mode AS sql_mode"))).mappings().one()
        assert Path(identity["datadir"]).resolve() == expected_data
        assert identity["port"] == 33306 and identity["isolation_level"] == "REPEATABLE-READ"
        assert "ONLY_FULL_GROUP_BY" in identity["sql_mode"]
        assert await connection.run_sync(lambda sync: inspect(sync).get_table_names()) == []
        await connection.commit()
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(AuthBase.metadata.create_all)
            rows = (await connection.execute(text("SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, CHARACTER_SET_NAME, COLLATION_NAME, DATETIME_PRECISION, IS_NULLABLE, COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() ORDER BY TABLE_NAME, ORDINAL_POSITION"))).mappings().all()
            columns = {(row["TABLE_NAME"], row["COLUMN_NAME"]): row for row in rows}
            plan = json.loads((out / "mysql-migration-plan.json").read_text(encoding="utf-8"))
            for table, names in plan["identifier_columns"].items():
                for name in names:
                    column = columns[table, name]
                    assert column["DATA_TYPE"] == "varchar" and column["CHARACTER_MAXIMUM_LENGTH"] == 255
                    assert column["CHARACTER_SET_NAME"] == "utf8mb4" and column["COLLATION_NAME"] == "utf8mb4_0900_bin"
            for group, kind in (("utc_datetime_columns", "datetime"), ("local_time_columns", "time")):
                for table, names in plan[group].items():
                    for name in names:
                        assert columns[table, name]["DATA_TYPE"] == kind and columns[table, name]["DATETIME_PRECISION"] == 6
            engines = (await connection.execute(text("SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()"))).all()
            assert all(row[1] == "InnoDB" for row in engines)

            def constraints(sync):
                inspector = inspect(sync)
                return {table: {"primary_key": inspector.get_pk_constraint(table), "indexes": inspector.get_indexes(table), "unique_constraints": inspector.get_unique_constraints(table), "foreign_keys": inspector.get_foreign_keys(table), "check_constraints": inspector.get_check_constraints(table)} for table in sorted(Base.metadata.tables)}

            snapshot = {"observed_utc": datetime.now(timezone.utc).isoformat(), "session": dict(identity), "columns": [dict(row) for row in rows], "engines": [list(row) for row in engines], "constraints": await connection.run_sync(constraints), "identifier_and_precision_assertions": "PASS"}
            (out / "mysql-schema-snapshot.json").write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
            print("Real MySQL identifier types, precision, engines and constraints: PASS")
    finally:
        async with engine.begin() as connection:
            await connection.run_sync(AuthBase.metadata.drop_all)
            await connection.run_sync(Base.metadata.drop_all)
        await engine.dispose()


asyncio.run(main())
