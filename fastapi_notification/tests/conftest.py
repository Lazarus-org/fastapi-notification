from typing import Any, AsyncIterator, Callable, Dict, Iterator, List, Optional

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastapi_notification.api.throttlings.role_base_throttle import history
from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.base import Base
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.settings.conf import configure, reset_config
from fastapi_notification.tests.setup import build_app


@pytest.fixture(autouse=True)
def clean_settings() -> Iterator[None]:
    """Reset the package settings and throttle history around every test.

    The configuration and the throttle history are process wide, so without
    this a test that changes either would leak into the next one.

    Yields:
        None: Control, while the settings are clean.

    """
    reset_config()
    history.clear()
    yield
    reset_config()
    history.clear()


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Provide an in-memory database with the package schema applied.

    Yields:
        AsyncEngine: The engine backing the test database.

    """
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield test_engine

    await test_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    """Provide a session factory bound to the test engine.

    Args:
        engine (AsyncEngine): The test engine.

    Returns:
        async_sessionmaker: The session factory.

    """
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def session(session_factory: async_sessionmaker) -> AsyncIterator[AsyncSession]:
    """Provide a session for tests that talk to the database directly.

    Yields:
        AsyncSession: The session.

    """
    async with session_factory() as test_session:
        yield test_session


@pytest.fixture
def dal(session: AsyncSession) -> NotificationDataAccessLayer:
    """Provide a data access layer bound to the test session.

    Args:
        session (AsyncSession): The test session.

    Returns:
        NotificationDataAccessLayer: The data access layer.

    """
    return NotificationDataAccessLayer(session)


@pytest.fixture
def current_user() -> Dict[str, Optional[int]]:
    """Provide the holder naming the user requests are made as.

    Returns:
        Dict[str, Optional[int]]: The mutable holder.

    """
    return {"id": None}


@pytest_asyncio.fixture
async def group(session: AsyncSession) -> Group:
    """Create a group notifications can be addressed to.

    Args:
        session (AsyncSession): The test session.

    Returns:
        Group: The persisted group.

    """
    instance = Group(name="admins")
    session.add(instance)
    await session.commit()

    return instance


@pytest_asyncio.fixture
async def user(session: AsyncSession) -> User:
    """Create a regular user.

    Args:
        session (AsyncSession): The test session.

    Returns:
        User: The persisted user.

    """
    instance = User(username="ann", email="ann@example.com")
    session.add(instance)
    await session.commit()

    return instance


@pytest_asyncio.fixture
async def other_user(session: AsyncSession) -> User:
    """Create a second regular user, unrelated to the first.

    Args:
        session (AsyncSession): The test session.

    Returns:
        User: The persisted user.

    """
    instance = User(username="bob", email="bob@example.com")
    session.add(instance)
    await session.commit()

    return instance


@pytest_asyncio.fixture
async def group_user(session: AsyncSession, group: Group) -> User:
    """Create a user who belongs to the test group.

    Args:
        session (AsyncSession): The test session.
        group (Group): The group to join.

    Returns:
        User: The persisted user.

    """
    instance = User(username="gil", email="gil@example.com", groups=[group])
    session.add(instance)
    await session.commit()

    return instance


@pytest_asyncio.fixture
async def staff_user(session: AsyncSession) -> User:
    """Create a staff user.

    Args:
        session (AsyncSession): The test session.

    Returns:
        User: The persisted user.

    """
    instance = User(username="sue", email="sue@example.com", is_staff=True)
    session.add(instance)
    await session.commit()

    return instance


@pytest_asyncio.fixture
async def superuser(session: AsyncSession) -> User:
    """Create a superuser.

    Args:
        session (AsyncSession): The test session.

    Returns:
        User: The persisted user.

    """
    instance = User(
        username="root", email="root@example.com", is_staff=True, is_superuser=True
    )
    session.add(instance)
    await session.commit()

    return instance


@pytest_asyncio.fixture
async def notification(dal: NotificationDataAccessLayer, user: User, session: AsyncSession) -> Any:
    """Create a sent notification addressed to the regular user.

    Args:
        dal (NotificationDataAccessLayer): The data access layer.
        user (User): The recipient.
        session (AsyncSession): The test session.

    Returns:
        Any: The persisted notification.

    """
    instance = await dal.create_notification(
        verb="liked your post", actor=user, recipients=user, is_sent=True
    )
    await session.commit()

    return instance


@pytest_asyncio.fixture
async def notifications(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> List[Any]:
    """Create three sent notifications addressed to the regular user.

    Args:
        dal (NotificationDataAccessLayer): The data access layer.
        user (User): The recipient.
        session (AsyncSession): The test session.

    Returns:
        List[Any]: The persisted notifications.

    """
    created = [
        await dal.create_notification(
            verb=f"did thing {index}", actor=user, recipients=user, is_sent=True
        )
        for index in range(3)
    ]
    await session.commit()

    return created


@pytest.fixture
def app_factory(
    session_factory: async_sessionmaker, current_user: Dict[str, Optional[int]]
) -> Callable[..., Any]:
    """Provide a factory building applications against the test database.

    Applications are built lazily so a test can change the settings first; the
    routers read their configuration when they are created.

    Args:
        session_factory (async_sessionmaker): The test session factory.
        current_user (Dict[str, Optional[int]]): The acting user holder.

    Returns:
        Callable[..., Any]: The application factory.

    """

    def factory(**settings: Any) -> Any:
        if settings:
            configure(**settings)
        return build_app(session_factory, current_user)

    return factory


@pytest.fixture
def client_factory(app_factory: Callable[..., Any]) -> Callable[..., AsyncClient]:
    """Provide a factory building HTTP clients for the test application.

    Args:
        app_factory (Callable[..., Any]): The application factory.

    Returns:
        Callable[..., AsyncClient]: The client factory.

    """

    def factory(**settings: Any) -> AsyncClient:
        app = app_factory(**settings)
        return AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        )

    return factory


@pytest_asyncio.fixture
async def client(
    client_factory: Callable[..., AsyncClient]
) -> AsyncIterator[AsyncClient]:
    """Provide an HTTP client for the test application with default settings.

    Yields:
        AsyncClient: The client.

    """
    async with client_factory() as test_client:
        yield test_client


@pytest.fixture
def as_user(current_user: Dict[str, Optional[int]]) -> Callable[[Any], None]:
    """Provide a helper switching which user requests are made as.

    Args:
        current_user (Dict[str, Optional[int]]): The acting user holder.

    Returns:
        Callable[[Any], None]: The helper.

    """

    def switch(target: Any) -> None:
        current_user["id"] = target.id if target is not None else None

    return switch
