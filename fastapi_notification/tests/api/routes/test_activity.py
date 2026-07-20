from typing import Any, Callable, List

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import User
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)

pytestmark = [
    pytest.mark.api,
    pytest.mark.api_routes,
    pytest.mark.api_routes_activity,
]


async def mark_seen(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Mark everything addressed to a user as seen.

    Args:
        dal (NotificationDataAccessLayer): The data access layer.
        user (User): The user who has seen them.
        session (AsyncSession): The session used to write.

    """
    await dal.mark_all_as_seen(user)
    await session.commit()


async def test_list_returns_seen_notifications(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    notifications: List[Notification],
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Activities are the notifications the caller has already seen."""
    await mark_seen(dal, user, session)
    as_user(user)

    response = await client.get("/activities/")

    assert response.status_code == 200
    assert response.json()["count"] == 3


async def test_list_excludes_unseen_notifications(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """A notification not yet read is not an activity."""
    as_user(user)

    assert (await client.get("/activities/")).json()["count"] == 0


async def test_list_serves_full_details_to_staff(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    notification: Notification,
    staff_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Staff get the detailed representation."""
    await mark_seen(dal, staff_user, session)
    as_user(staff_user)

    result = (await client.get("/activities/")).json()["results"][0]

    assert "recipient" in result


async def test_retrieve_serves_a_seen_notification(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    notification: Notification,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """A seen notification can be read again in full."""
    await mark_seen(dal, user, session)
    as_user(user)

    response = await client.get(f"/activities/{notification.id}/")

    assert response.status_code == 200
    assert response.json()["verb"] == "liked your post"


async def test_retrieve_reports_a_missing_activity(
    client: AsyncClient, user: User, as_user: Callable[[Any], None]
) -> None:
    """Asking for an activity that is not there gives a 404."""
    as_user(user)

    assert (await client.get("/activities/9999/")).status_code == 404


async def test_clear_notification_soft_deletes_it(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    notification: Notification,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Clearing one activity hides it without destroying it."""
    await mark_seen(dal, user, session)
    as_user(user)

    response = await client.get(f"/activities/{notification.id}/clear_notification/")

    assert response.status_code == 204
    assert (await client.get("/activities/")).json()["count"] == 0
    assert await session.get(Notification, notification.id) is not None


async def test_clear_notification_reports_a_missing_activity(
    client: AsyncClient, user: User, as_user: Callable[[Any], None]
) -> None:
    """Clearing something that is not there gives a 404."""
    as_user(user)

    assert (await client.get("/activities/9999/clear_notification/")).status_code == 404


async def test_clear_activities_soft_deletes_everything(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    notifications: List[Notification],
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Clearing everything empties the activity list."""
    await mark_seen(dal, user, session)
    as_user(user)

    response = await client.get("/activities/clear_activities/")

    assert response.status_code == 204
    assert (await client.get("/activities/")).json()["count"] == 0


async def test_soft_delete_routes_can_be_switched_off(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """With soft delete disabled, the clearing routes are absent."""
    as_user(user)

    async with client_factory(API_INCLUDE_SOFT_DELETE=False) as client:
        assert (await client.get("/activities/clear_activities/")).status_code == 404
        response = await client.get(
            f"/activities/{notification.id}/clear_notification/"
        )

    assert response.status_code == 404


async def test_hard_delete_routes_are_absent_by_default(
    client: AsyncClient,
    notification: Notification,
    staff_user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Permanent deletion is off unless it is asked for."""
    as_user(staff_user)

    assert (await client.get("/activities/delete_activities/")).status_code == 404
    response = await client.get(f"/activities/{notification.id}/delete_notification/")

    assert response.status_code == 404


async def test_delete_notification_destroys_it(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    staff_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """An admin can permanently delete a single notification."""
    as_user(staff_user)
    notification_id = notification.id

    async with client_factory(API_INCLUDE_HARD_DELETE=True) as client:
        response = await client.get(
            f"/activities/{notification_id}/delete_notification/"
        )

    assert response.status_code == 204

    # The request ran in its own session, so drop what this one has cached.
    session.expire_all()
    assert await session.get(Notification, notification_id) is None


async def test_delete_notification_reports_a_missing_activity(
    client_factory: Callable[..., AsyncClient],
    staff_user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Deleting something that is not there gives a 404."""
    as_user(staff_user)

    async with client_factory(API_INCLUDE_HARD_DELETE=True) as client:
        response = await client.get("/activities/9999/delete_notification/")

    assert response.status_code == 404


async def test_delete_activities_destroys_everything_seen(
    client_factory: Callable[..., AsyncClient],
    dal: NotificationDataAccessLayer,
    notifications: List[Notification],
    staff_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """An admin can permanently delete every activity they can see."""
    await mark_seen(dal, staff_user, session)
    as_user(staff_user)

    async with client_factory(API_INCLUDE_HARD_DELETE=True) as client:
        response = await client.get("/activities/delete_activities/")
        remaining = (await client.get("/activities/")).json()["count"]

    assert response.status_code == 204
    assert remaining == 0


async def test_hard_delete_is_refused_to_regular_users(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Permanent deletion is reserved for admins."""
    as_user(user)

    async with client_factory(API_INCLUDE_HARD_DELETE=True) as client:
        single = await client.get(
            f"/activities/{notification.id}/delete_notification/"
        )
        everything = await client.get("/activities/delete_activities/")

    assert single.status_code == 403
    assert everything.status_code == 403


async def test_listing_can_be_switched_off(
    client_factory: Callable[..., AsyncClient],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """With listing disabled, the route is absent entirely."""
    as_user(user)

    async with client_factory(API_ALLOW_LIST=False) as client:
        assert (await client.get("/activities/")).status_code == 404


async def test_retrieval_can_be_switched_off(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """With retrieval disabled, the route is absent entirely."""
    as_user(user)

    async with client_factory(API_ALLOW_RETRIEVE=False) as client:
        response = await client.get(f"/activities/{notification.id}/")

    assert response.status_code == 404


async def test_an_anonymous_caller_is_refused(
    client: AsyncClient, as_user: Callable[[Any], None]
) -> None:
    """Without an authenticated user, nothing is served."""
    as_user(None)

    assert (await client.get("/activities/")).status_code == 401
