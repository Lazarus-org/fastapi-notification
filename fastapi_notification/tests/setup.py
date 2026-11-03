from typing import Any, AsyncIterator, Callable, Dict, Optional

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi_notification.api.routers.notification import create_router
from fastapi_notification.identity import BuiltInIdentityAdapter
from fastapi_notification.models.auth import User
from fastapi_notification.settings.conf import configure


def build_app(
    session_factory: async_sessionmaker,
    current_user: Dict[str, Optional[int]],
    prefix: str = "",
) -> FastAPI:
    """Build a FastAPI application mounting the package routers.

    Args:
        session_factory (async_sessionmaker): Factory producing test sessions.
        current_user (Dict[str, Optional[int]]): A mutable holder whose ``"id"``
            key names the user each request is made as, so a test can switch
            identity without rebuilding the app.
        prefix (str): A path prefix for the routers.

    Returns:
        FastAPI: The configured application.
    """

    async def get_session() -> AsyncIterator[AsyncSession]:
        """Yield a session for the request.

        Yields:
            AsyncSession: The session.
        """

        async with session_factory() as session:
            yield session

    async def get_user() -> Any:
        """Return the user the current test is acting as.

        Returns:
            Any: The user, or ``None`` when the test is anonymous.
        """
        user_id = current_user.get("id")
        if user_id is None:
            return None

        async with session_factory() as session:
            return await session.get(User, user_id)

    configure(IDENTITY_ADAPTER=BuiltInIdentityAdapter)
    app = FastAPI()
    app.include_router(
        create_router(
            session_dependency=get_session,
            current_user_dependency=get_user,
            prefix=prefix,
        )
    )

    return app


def make_app_factory(
    session_factory: async_sessionmaker,
    current_user: Dict[str, Optional[int]],
) -> Callable[..., FastAPI]:
    """Return a helper that builds applications sharing the test session.

    Args:
        session_factory (async_sessionmaker): Factory producing test sessions.
        current_user (Dict[str, Optional[int]]): The acting user holder.

    Returns:
        Callable[..., FastAPI]: The application factory.
    """

    def factory(prefix: str = "") -> FastAPI:
        return build_app(session_factory, current_user, prefix=prefix)

    return factory
