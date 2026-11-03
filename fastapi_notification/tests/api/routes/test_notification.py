from typing import Any, Callable, List

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.api.routers.notification import create_router
from fastapi_notification.identity import BuiltInIdentityAdapter
from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.settings.conf import configure

pytestmark = [
    pytest.mark.api,
    pytest.mark.api_routes,
    pytest.mark.api_routes_notification,
]


def test_openapi_documents_state_changes_with_write_methods() -> None:
    """OpenAPI exposes POST/DELETE for state changes and no GET variants."""

    async def session_dependency() -> Any:
        yield None

    async def user_dependency() -> Any:
        return object()

    configure(
        IDENTITY_ADAPTER=BuiltInIdentityAdapter,
        API_INCLUDE_HARD_DELETE=True,
    )
    app = FastAPI()
    app.include_router(
        create_router(
            session_dependency=session_dependency,
            current_user_dependency=user_dependency,
        )
    )
    paths = app.openapi()["paths"]

    assert set(paths["/notifications/mark_all_as_seen/"]) == {"post"}
    assert set(paths["/notifications/{notification_id}/mark_as_seen/"]) == {"post"}
    assert set(paths["/notifications/{notification_id}/mark_as_unseen/"]) == {"post"}
    assert set(paths["/activities/clear_activities/"]) == {"delete"}
    assert set(paths["/activities/delete_activities/"]) == {"delete"}
    assert set(paths["/activities/{notification_id}/clear_notification/"]) == {"delete"}
    assert set(paths["/activities/{notification_id}/delete_notification/"]) == {
        "delete"
    }
    assert set(paths["/notifications/{notification_id}/"]) == {"get"}
    assert set(paths["/activities/{notification_id}/"]) == {"get"}


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

    assert set(result) == {
        "title",
        "id",
        "description",
        "status",
        "category",
        "priority",
        "link",
        "timestamp",
        "expires_at",
        "template_key",
        "locale",
    }


async def test_staff_get_the_same_default_representation_for_their_own_notifications(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    staff_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Staff status does not force full notification details."""
    await dal.create_notification(
        verb="staff update", actor=user, recipients=staff_user, is_sent=True
    )
    await session.commit()
    as_user(staff_user)

    result = (await client.get("/notifications/")).json()["results"][0]

    assert set(result) == {
        "title",
        "id",
        "description",
        "status",
        "category",
        "priority",
        "link",
        "timestamp",
        "expires_at",
        "template_key",
        "locale",
    }


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


async def test_retrieve_is_read_only_and_does_not_mark_notification_seen(
    client: AsyncClient,
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """GET retrieves a notification without changing its seen state."""
    as_user(user)

    response = await client.get(f"/notifications/{notification.id}/")

    assert response.status_code == 200
    assert response.json()["verb"] == "liked your post"
    assert (await client.get("/notifications/")).json()["count"] == 1


async def test_post_marks_one_notification_as_seen(
    client: AsyncClient,
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """The explicit POST action moves one notification into activities."""
    as_user(user)

    get_response = await client.get(f"/notifications/{notification.id}/mark_as_seen/")
    assert get_response.status_code == 405
    assert (await client.get("/notifications/")).json()["count"] == 1

    response = await client.post(f"/notifications/{notification.id}/mark_as_seen/")

    assert response.status_code == 204
    assert (await client.get("/notifications/")).json()["count"] == 0
    assert (await client.get("/activities/")).json()["count"] == 1


async def test_post_mark_as_seen_is_idempotent(
    client: AsyncClient,
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Repeating the explicit seen action does not create duplicate seen rows."""
    as_user(user)
    path = f"/notifications/{notification.id}/mark_as_seen/"

    first = await client.post(path)
    second = await client.post(path)

    assert first.status_code == 204
    assert second.status_code == 204
    assert (await client.get("/activities/")).json()["count"] == 1


async def test_get_cannot_mark_all_notifications_as_seen(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """GET cannot invoke the bulk seen action."""
    as_user(user)

    response = await client.get("/notifications/mark_all_as_seen/")

    assert response.status_code == 405
    assert (await client.get("/notifications/")).json()["count"] == 3


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


async def test_group_member_can_mark_group_notification_as_seen(
    client_factory: Callable[..., AsyncClient],
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """A group member can explicitly mark a group-addressed notification seen."""
    notification = await dal.create_notification(
        verb="group update", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    as_user(group_user)

    async with client_factory() as client:
        response = await client.post(f"/notifications/{notification.id}/mark_as_seen/")

    assert response.status_code == 204


async def test_mark_as_seen_hides_another_users_notification(
    client: AsyncClient,
    notification: Notification,
    other_user: User,
    as_user: Callable[[Any], None],
) -> None:
    """The explicit state-changing action cannot bypass audience isolation."""
    as_user(other_user)

    response = await client.post(f"/notifications/{notification.id}/mark_as_seen/")

    assert response.status_code == 404


async def test_mark_all_as_seen_clears_the_list(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Marking everything as seen empties the unseen list."""
    as_user(user)

    response = await client.post("/notifications/mark_all_as_seen/")

    assert response.json() == {"detail": "3 Notifications marked as seen."}
    assert (await client.get("/notifications/")).json()["count"] == 0


async def test_group_member_can_mark_all_group_notifications_as_seen(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """The API bulk action includes notifications addressed to user groups."""
    await dal.create_notification(
        verb="group announcement", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    as_user(group_user)

    response = await client.post("/notifications/mark_all_as_seen/")

    assert response.status_code == 200
    assert response.json() == {"detail": "1 Notifications marked as seen."}
    assert (await client.get("/notifications/")).json()["count"] == 0
    assert (await client.get("/activities/")).json()["count"] == 1


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


async def test_staff_cannot_list_another_users_notification(
    client: AsyncClient,
    notification: Notification,
    staff_user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Staff see only notifications addressed to them or their groups."""
    as_user(staff_user)

    response = await client.get("/notifications/")

    assert response.status_code == 200
    assert response.json()["count"] == 0


async def test_superuser_cannot_list_another_users_notification(
    client: AsyncClient,
    notification: Notification,
    superuser_only: User,
    as_user: Callable[[Any], None],
) -> None:
    """Superuser status does not widen the personal notification audience."""
    as_user(superuser_only)

    response = await client.get("/notifications/")

    assert response.status_code == 200
    assert response.json()["count"] == 0


async def test_staff_cannot_retrieve_another_users_notification(
    client: AsyncClient,
    notification: Notification,
    staff_user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Retrieval does not let staff bypass the notification audience."""
    as_user(staff_user)

    assert (await client.get(f"/notifications/{notification.id}/")).status_code == 404


async def test_superuser_cannot_retrieve_another_users_notification(
    client: AsyncClient,
    notification: Notification,
    superuser_only: User,
    as_user: Callable[[Any], None],
) -> None:
    """Retrieval does not let superusers bypass the notification audience."""
    as_user(superuser_only)

    assert (await client.get(f"/notifications/{notification.id}/")).status_code == 404


async def test_staff_can_list_notifications_addressed_to_their_group(
    client_factory: Callable[..., AsyncClient],
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    staff_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Staff retain ordinary group-audience access without a global bypass."""
    await session.refresh(staff_user, ["groups"])
    staff_user.groups.append(group)
    await dal.create_notification(
        verb="group announcement", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    as_user(staff_user)

    async with client_factory() as client:
        response = await client.get("/notifications/")

    assert response.status_code == 200
    assert response.json()["count"] == 1


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
        mark_seen = await client.post(f"/notifications/{notification.id}/mark_as_seen/")

    assert response.status_code == 404
    assert mark_seen.status_code == 404


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
