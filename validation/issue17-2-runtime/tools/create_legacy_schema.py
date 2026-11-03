"""Create the actual committed Issue 17.1 schema in an empty disposable DB."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LEGACY = ROOT / ".validation-cache/issue17-1-schema"
LEGACY.mkdir(parents=True, exist_ok=True)
assert LEGACY.resolve().is_relative_to(ROOT.resolve())
names = subprocess.check_output(
    ["git", "ls-tree", "-r", "--name-only", "ae79ca7", "--", "fastapi_notification"],
    cwd=ROOT,
    text=True,
).splitlines()
for name in names:
    if not name.endswith(".py"):
        continue
    destination = LEGACY / name
    assert destination.resolve().is_relative_to(LEGACY.resolve())
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(
        subprocess.check_output(["git", "show", "ae79ca7:" + name], cwd=ROOT)
    )
sys.path.insert(0, str(LEGACY))
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

import fastapi_notification
from fastapi_notification.models.base import AuthBase, Base
from fastapi_notification.models.notification_digest import NotificationDigestBatch

assert Path(fastapi_notification.__file__).resolve().parent.parent == LEGACY
assert (
    "last_error" in NotificationDigestBatch.__table__.c
    and "claim_token" not in NotificationDigestBatch.__table__.c
)
if "--check-source" in sys.argv:
    print("Verified the immutable Issue 17.1 schema from commit ae79ca7.")
    raise SystemExit(0)


async def main():
    engine = create_async_engine(json.load(sys.stdin)["url"])
    assert engine.url.database.startswith("notification_validation_17_2_")
    async with engine.begin() as connection:
        assert (
            await connection.run_sync(lambda sync: inspect(sync).get_table_names())
            == []
        )
        await connection.run_sync(Base.metadata.create_all)
        await connection.run_sync(AuthBase.metadata.create_all)
    await engine.dispose()
    print("Created actual Issue 17.1 package and auth metadata.")


asyncio.run(main())
