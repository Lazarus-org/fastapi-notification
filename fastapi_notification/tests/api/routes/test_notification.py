from typing import Any, Callable, List

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)

pytestmark = [
    pytest.mark.api,
    pytest.mark.api_routes,
    pytest.mark.api_routes_notification,
]


async def test_list_returns_unseen_notifications(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Listing serves the notifications the caller has not seen."""
    as_user(user)

    response = await client.get("/notifications/")

    assert response.status_code == 200
    assert response.json()["count"] == 3


async def test_list_is_paginated(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """A page carries the total, the results and a link onwards."""
    as_user(user)

    body = (await client.get("/notifications/?limit=2")).json()

    assert body["count"] == 3
    assert len(body["results"]) == 2
    assert "offset=2" in body["next"]
    assert body["previous"] is None


async def test_list_serves_summary_fields_to_regular_users(
    client: AsyncClient,
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """A regular user gets the compact representation."""
    as_user(user)

    result = (await client.get("/notifications/")).json()["results"][0]

    assert set(result) == {"title", "id", "description", "status", "link", "timestamp"}


async def test_list_serves_full_details_to_staff(
    client: AsyncClient,
    notification: Notification,
    staff_user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Staff get the detailed representation."""
    as_user(staff_user)

    result = (await client.get("/notifications/")).json()["results"][0]

    assert "recipient" in result
    assert "seen_by" in result
    assert "actor_content_type" in result


async def test_list_can_be_searched(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Searching narrows the listing to matching notifications."""
    as_user(user)

    assert (await client.get("/notifications/?search=thing 1")).json()["count"] == 1


async def test_list_can_be_ordered(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Ordering by an allowed field reorders the listing."""
    as_user(user)

    ascending = (await client.get("/notifications/?ordering=id")).json()["results"]
    descending = (await client.get("/notifications/?ordering=-id")).json()["results"]

    assert [row["id"] for row in ascending] == sorted(row["id"] for row in ascending)
    assert [row["id"] for row in descending] == sorted(
        (row["id"] for row in descending), reverse=True
    )


async def test_list_ignores_an_unpermitted_ordering_field(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """A client cannot order by a field that was not allowed."""
    as_user(user)

    body = (await client.get("/notifications/?ordering=verb")).json()

    assert body["count"] == 3


async def test_list_can_be_filtered_by_status(
    client_factory: Callable[..., AsyncClient],
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Filtering by status narrows the listing."""
    await dal.create_notification(
        verb="urgent", actor=user, recipients=user, status="CRITICAL", is_sent=True
    )
    await dal.create_notification(
        verb="routine", actor=user, recipients=user, is_sent=True
    )
    await session.commit()
    as_user(user)

    async with client_factory() as client:
        body = (await client.get("/notifications/?status=CRITICAL")).json()

    assert body["count"] == 1


async def test_retrieve_serves_the_notification_and_marks_it_seen(
    client: AsyncClient,
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Reading a notification takes it out of the unseen list."""
    as_user(user)

    response = await client.get(f"/notifications/{notification.id}/")

    assert response.status_code == 200
    assert response.json()["verb"] == "liked your post"
    assert (await client.get("/notifications/")).json()["count"] == 0


async def test_retrieve_reports_a_missing_notification(
    client: AsyncClient, user: User, as_user: Callable[[Any], None]
) -> None:
    """Asking for a notification that is not there gives a 404."""
    as_user(user)

    assert (await client.get("/notifications/9999/")).status_code == 404


async def test_retrieve_hides_another_users_notification(
    client: AsyncClient,
    notification: Notification,
    other_user: User,
    as_user: Callable[[Any], None],
) -> None:
    """A notification addressed to someone else is simply not there."""
    as_user(other_user)

    assert (await client.get(f"/notifications/{notification.id}/")).status_code == 404


async def test_mark_all_as_seen_clears_the_list(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Marking everything as seen empties the unseen list."""
    as_user(user)

    response = await client.get("/notifications/mark_all_as_seen/")

    assert response.json() == {"detail": "3 Notifications marked as seen."}
    assert (await client.get("/notifications/")).json()["count"] == 0


async def test_group_members_see_group_notifications(
    client_factory: Callable[..., AsyncClient],
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """A notification addressed to a group reaches its members."""
    await dal.create_notification(
        verb="announced", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    as_user(group_user)

    async with client_factory() as client:
        assert (await client.get("/notifications/")).json()["count"] == 1


async def test_unsent_notifications_are_not_listed(
    client_factory: Callable[..., AsyncClient],
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """A notification that was never sent does not reach anyone."""
    await dal.create_notification(verb="queued", actor=user, recipients=user)
    await session.commit()
    as_user(user)

    async with client_factory() as client:
        assert (await client.get("/notifications/")).json()["count"] == 0


async def test_listing_can_be_switched_off(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """With listing disabled, the route is absent entirely."""
    as_user(user)

    async with client_factory(API_ALLOW_LIST=False) as client:
        assert (await client.get("/notifications/")).status_code == 404


async def test_retrieval_can_be_switched_off(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """With retrieval disabled, the route is absent entirely."""
    as_user(user)

    async with client_factory(API_ALLOW_RETRIEVE=False) as client:
        response = await client.get(f"/notifications/{notification.id}/")

    assert response.status_code == 404


async def test_full_details_can_be_forced_for_everyone(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Turning on full details gives regular users the detailed shape."""
    as_user(user)

    async with client_factory(SERIALIZER_INCLUDE_FULL_DETAILS=True) as client:
        result = (await client.get("/notifications/")).json()["results"][0]

    assert "recipient" in result


async def test_serializer_fields_can_be_narrowed(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """A configured field list is served exactly."""
    as_user(user)

    async with client_factory(SERIALIZER_FIELDS=["id", "verb"]) as client:
        result = (await client.get("/notifications/")).json()["results"][0]

    assert set(result) == {"id", "verb"}


async def test_an_anonymous_caller_is_refused(
    client: AsyncClient, notification: Notification, as_user: Callable[[Any], None]
) -> None:
    """Without an authenticated user, nothing is served."""
    as_user(None)

    assert (await client.get("/notifications/")).status_code == 401


async def test_throttling_refuses_a_burst(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Exceeding the configured rate is refused with a retry hint."""
    as_user(user)

    async with client_factory(AUTHENTICATED_USER_THROTTLE_RATE="2/minute") as client:
        await client.get("/notifications/")
        await client.get("/notifications/")
        response = await client.get("/notifications/")

    assert response.status_code == 429
    assert "Retry-After" in response.headers


async def test_throttling_can_be_switched_off(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """With no throttle class, requests are never rate limited."""
    as_user(user)

    async with client_factory(API_THROTTLE_CLASS=None) as client:
        for _ in range(5):
            response = await client.get("/notifications/")

    assert response.status_code == 200


async def test_pagination_can_be_switched_off(
    client_factory: Callable[..., AsyncClient],
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """With no pagination class, the results are returned unwrapped."""
    as_user(user)

    async with client_factory(API_PAGINATION_CLASS=None) as client:
        body = (await client.get("/notifications/")).json()

    assert isinstance(body, list)
    assert len(body) == 3
