from typing import Any, Callable

import pytest
from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from fastapi_notification.api.dependencies.auth import (
    apply_extra_permission,
    check_extra_permission,
    get_authenticated_user,
    get_current_user,
    make_admin_dependency,
    make_authenticated_dependency,
    make_extra_permission_dependency,
    require_admin_user,
)
from fastapi_notification.api.dependencies.db import get_session
from fastapi_notification.api.dependencies.throttling import (
    check_throttle,
    enforce_throttle,
)
from fastapi_notification.api.routers.notification import create_router
from fastapi_notification.identity import IdentityAdapter
from fastapi_notification.models.auth import User
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.api, pytest.mark.api_dependencies]


class Viewer:
    """A stand-in user for dependencies that do not touch the database."""

    def __init__(
        self,
        identifier: int = 1,
        is_staff: bool = False,
        is_superuser: bool = False,
    ) -> None:
        self.id = identifier
        self.is_staff = is_staff
        self.is_superuser = is_superuser


def make_request() -> Request:
    """Build a bare request.

    Returns:
        Request: The request.

    """
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
    )


async def test_the_session_placeholder_explains_itself() -> None:
    """The unconfigured session dependency says how to configure it."""
    with pytest.raises(NotImplementedError, match="needs a database session"):
        await anext(get_session())


async def test_the_user_placeholder_explains_itself() -> None:
    """The unconfigured user dependency says how to configure it."""
    with pytest.raises(NotImplementedError, match="who is making the request"):
        await get_current_user()


async def test_the_authentication_guard_passes_a_real_user() -> None:
    """A resolved user is handed straight through."""
    viewer = Viewer()
    guard = make_authenticated_dependency(lambda: viewer)

    assert await guard(user=viewer) is viewer


async def test_the_authentication_guard_refuses_nobody() -> None:
    """A dependency that resolves to nothing means an unauthenticated caller."""
    guard = make_authenticated_dependency(lambda: None)

    with pytest.raises(HTTPException) as raised:
        await guard(user=None)

    assert raised.value.status_code == 401


async def test_the_admin_guard_passes_staff() -> None:
    """A staff user satisfies the admin guard."""
    staff = Viewer(is_staff=True)
    guard = make_admin_dependency(lambda: staff)

    assert await guard(user=staff) is staff


async def test_the_admin_guard_refuses_regular_users() -> None:
    """A regular user does not satisfy the admin guard."""
    guard = make_admin_dependency(lambda: Viewer())

    with pytest.raises(HTTPException) as raised:
        await guard(user=Viewer())

    assert raised.value.status_code == 403


async def test_the_packaged_admin_guard_refuses_regular_users() -> None:
    """The default admin dependency behaves the same way."""
    with pytest.raises(HTTPException) as raised:
        await require_admin_user(user=Viewer())

    assert raised.value.status_code == 403


async def test_the_packaged_admin_guard_passes_staff() -> None:
    """The default admin dependency lets staff through."""
    staff = Viewer(is_staff=True)

    assert await require_admin_user(user=staff) is staff


async def test_no_extra_permission_means_no_check() -> None:
    """With nothing configured, the extra permission is a no-op."""
    assert await apply_extra_permission(make_request(), Viewer()) is None


async def test_an_allowing_extra_permission_passes() -> None:
    """A permission that returns true lets the request through."""
    configure(
        API_EXTRA_PERMISSION_CLASS=(
            "fastapi_notification.tests.api.dependencies.test_dependencies.AllowAll"
        )
    )

    assert await apply_extra_permission(make_request(), Viewer()) is None


async def test_a_refusing_extra_permission_blocks() -> None:
    """A permission that returns false refuses the request."""
    configure(
        API_EXTRA_PERMISSION_CLASS=(
            "fastapi_notification.tests.api.dependencies.test_dependencies.DenyAll"
        )
    )

    with pytest.raises(HTTPException) as raised:
        await apply_extra_permission(make_request(), Viewer())

    assert raised.value.status_code == 403


async def test_an_async_extra_permission_is_awaited() -> None:
    """A permission returning a coroutine is awaited before being judged."""
    configure(
        API_EXTRA_PERMISSION_CLASS=(
            "fastapi_notification.tests.api.dependencies.test_dependencies.AsyncDenyAll"
        )
    )

    with pytest.raises(HTTPException) as raised:
        await apply_extra_permission(make_request(), Viewer())

    assert raised.value.status_code == 403


def test_no_throttle_class_means_no_limit() -> None:
    """With no throttle class, nothing is ever refused."""
    configure(API_THROTTLE_CLASS=None)

    assert check_throttle(Viewer()) is None


def test_the_throttle_refuses_a_burst() -> None:
    """Exceeding the rate is refused with a retry hint."""
    configure(AUTHENTICATED_USER_THROTTLE_RATE="1/minute")
    viewer = Viewer()

    check_throttle(viewer)

    with pytest.raises(HTTPException) as raised:
        check_throttle(viewer)

    assert raised.value.status_code == 429
    assert "Retry-After" in raised.value.headers


async def test_the_extra_permission_gates_the_routes(
    session_factory: async_sessionmaker, user: User
) -> None:
    """A refusing extra permission blocks the routes themselves."""
    configure(
        API_EXTRA_PERMISSION_CLASS=(
            "fastapi_notification.tests.api.dependencies.test_dependencies.DenyAll"
        )
    )

    async def get_test_session() -> Any:
        async with session_factory() as session:
            yield session

    async def get_test_user() -> Any:
        async with session_factory() as session:
            return await session.get(User, user.id)

    app = FastAPI()
    app.include_router(
        create_router(
            session_dependency=get_test_session, current_user_dependency=get_test_user
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/notifications/")

    assert response.status_code == 403


class AllowAll:
    """An extra permission that lets every request through."""

    def __call__(self, request: Any, user: Any) -> bool:
        return True


class DenyAll:
    """An extra permission that refuses every request."""

    def __call__(self, request: Any, user: Any) -> bool:
        return False


class AsyncDenyAll:
    """An extra permission that refuses every request, asynchronously."""

    async def __call__(self, request: Any, user: Any) -> bool:
        return False


async def test_the_packaged_authentication_guard_passes_a_real_user() -> None:
    """The default authentication dependency hands a real user through."""
    viewer = Viewer()

    assert await get_authenticated_user(user=viewer) is viewer


async def test_the_packaged_authentication_guard_refuses_nobody() -> None:
    """The default authentication dependency refuses an absent user."""
    with pytest.raises(HTTPException) as raised:
        await get_authenticated_user(user=None)

    assert raised.value.status_code == 401


async def test_the_packaged_extra_permission_dependency_passes() -> None:
    """The default extra permission dependency hands the user through."""
    viewer = Viewer()

    assert await check_extra_permission(make_request(), user=viewer) is viewer


async def test_the_packaged_throttle_dependency_passes() -> None:
    """The default throttling dependency hands the user through."""
    viewer = Viewer()

    assert await enforce_throttle(user=viewer) is viewer


async def test_the_admin_guard_refuses_superuser_without_staff() -> None:
    """Superuser status alone does not satisfy the explicit staff admin guard."""
    superuser = Viewer(is_staff=False, is_superuser=True)
    guard = make_admin_dependency(lambda: superuser)

    with pytest.raises(HTTPException) as error:
        await guard(user=superuser)

    assert error.value.status_code == 403


class AdminFlagUser:
    """A host identity with a custom administrative flag."""

    id = "custom-admin"
    is_root = False
    is_admin = True


class AdminFlagIdentityAdapter(IdentityAdapter):
    staff_attribute = "is_admin"
    superuser_attribute = "is_root"


async def test_admin_guard_uses_custom_identity_adapter_role_mapping() -> None:
    """The staff-only administrative policy follows the configured adapter."""
    configure(IDENTITY_ADAPTER=AdminFlagIdentityAdapter)
    user = AdminFlagUser()
    guard = make_admin_dependency(lambda: user)

    assert await guard(user=user) is user


async def test_extra_permission_dependency_uses_the_bound_user() -> None:
    """The custom permission receives the same host identity as the route."""
    user = Viewer(identifier=77)
    seen = []

    class CaptureUserPermission:
        def __call__(self, request: Request, candidate: Any) -> bool:
            seen.append((request.url.path, candidate))
            return candidate is user

    configure(API_EXTRA_PERMISSION_CLASS=CaptureUserPermission)
    dependency = make_extra_permission_dependency(lambda: user)

    result = await dependency(request=make_request(), user=user)

    assert result is user
    assert seen == [("/", user)]


async def test_extra_permission_dependency_refuses_a_false_result() -> None:
    """A configured permission remains an additional deny-only boundary."""
    user = Viewer(identifier=78)

    class DenyPermission:
        def __call__(self, request: Request, candidate: Any) -> bool:
            del request, candidate
            return False

    configure(API_EXTRA_PERMISSION_CLASS=DenyPermission)
    dependency = make_extra_permission_dependency(lambda: user)

    with pytest.raises(HTTPException) as raised:
        await dependency(request=make_request(), user=user)

    assert raised.value.status_code == 403


async def test_extra_permission_also_gates_administrative_routes() -> None:
    """The global extra-permission dependency cannot be bypassed by staff."""
    configure(
        API_EXTRA_PERMISSION_CLASS=DenyAll,
        API_INCLUDE_HARD_DELETE=True,
    )

    async def get_test_session() -> Any:
        yield None

    async def get_staff_user() -> Any:
        return Viewer(is_staff=True)

    app = FastAPI()
    app.include_router(
        create_router(
            session_dependency=get_test_session,
            current_user_dependency=get_staff_user,
        )
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.delete("/activities/delete_activities/")

    assert response.status_code == 403


async def test_admin_guard_accepts_superuser_who_is_also_staff() -> None:
    """A superuser may administer when the host also marks them as staff."""
    user = Viewer(is_staff=True, is_superuser=True)
    guard = make_admin_dependency(lambda: user)

    assert await guard(user=user) is user
