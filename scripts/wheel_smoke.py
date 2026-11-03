"""Run with the clean wheel interpreter, isolated from the source checkout."""

import asyncio
import importlib.metadata as metadata
import json
from pathlib import Path
import sys
import fastapi_notification as package
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

assert "site-packages" in str(Path(package.__file__)).lower()
assert all(hasattr(package, name) for name in package.__all__)
assert not (Path(package.__file__).parent / "tests").exists()
for name in ["pytest", "black", "alembic", "mypy", "httpx"]:
    try:
        metadata.version(name)
    except metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError(f"Development dependency installed: {name}")


class HostActor(package.Base):
    __tablename__ = "host_actor"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(package.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_dependency():
        async with factory() as session:
            yield session

    async def user_dependency():
        return None

    app = FastAPI()
    app.include_router(
        package.create_router(
            session_dependency=session_dependency,
            current_user_dependency=user_dependency,
        )
    )
    paths = app.openapi()["paths"]
    assert "/notifications/summary/" in paths
    assert "/notifications/quiet-hours/" in paths
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/notifications/",
            "raw_path": b"/notifications/",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "server": ("test", 80),
            "client": ("test", 1234),
        },
        receive,
        send,
    )
    assert next(m for m in sent if m["type"] == "http.response.start")["status"] == 401
    async with factory() as session:
        actor = HostActor(id="actor-1")
        session.add(actor)
        await session.flush()
        n = await package.NotificationDataAccessLayer(session).create_notification(
            verb="wheel smoke", actor=actor, recipients="recipient-1", is_sent=True
        )
        await session.commit()
        identifier = n.id
    async with factory() as session:
        n = await session.get(package.Notification, identifier)
        assert n.verb == "wheel smoke"
    await engine.dispose()
    print(
        json.dumps(
            {
                "result": "PASS",
                "python": sys.version,
                "package_file": package.__file__,
                "exports": len(package.__all__),
                "openapi_paths": len(paths),
            }
        )
    )


asyncio.run(main())
