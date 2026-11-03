from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield the database session used to serve the current request.

    This is a placeholder: the package does not own the application's engine or
    session factory. Provide a real one either by passing
    ``session_dependency`` to the router factory, or by overriding this function
    through FastAPI's ``dependency_overrides``.

    Yields:
        AsyncSession: The session for this request.

    Raises:
        NotImplementedError: Always, until the host supplies a dependency.
    """
    raise NotImplementedError(
        "fastapi-notification needs a database session. Pass session_dependency="
        " to the router factory, or override"
        " fastapi_notification.api.dependencies.db.get_session through"
        " app.dependency_overrides."
    )
    yield  # pragma: no cover
