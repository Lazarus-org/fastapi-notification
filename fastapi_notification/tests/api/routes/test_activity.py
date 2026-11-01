from typing import Any, Callable, List

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.notification import Notification
from fastapi_notification.models.notification_seen import NotificationSeen
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


async def test_staff_cannot_list_another_users_activity_even_with_legacy_seen_row(
    client: AsyncClient,
    notification: Notification,
    staff_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """A legacy seen record does not bypass the notification audience."""
    session.add(
        NotificationSeen(
            notification_id=notification.id, user_id=str(staff_user.id)
        )
    )
    await session.commit()
    as_user(staff_user)

    response = await client.get("/activities/")

    assert response.status_code == 200
    assert response.json()["count"] == 0


async def test_superuser_cannot_list_another_users_activity_even_with_legacy_seen_row(
    client: AsyncClient,
    notification: Notification,
    superuser_only: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """A superuser's legacy seen row does not widen personal activity access."""
    session.add(
        NotificationSeen(
            notification_id=notification.id, user_id=str(superuser_only.id)
        )
    )
    await session.commit()
    as_user(superuser_only)

    response = await client.get("/activities/")

    assert response.status_code == 200
    assert response.json()["count"] == 0


async def test_staff_cannot_retrieve_another_users_activity(
    client: AsyncClient,
    notification: Notification,
    staff_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Staff cannot retrieve another user's activity by knowing its ID."""
    session.add(
        NotificationSeen(notification_id=notification.id, user_id=str(staff_user.id))
    )
    await session.commit()
    as_user(staff_user)

    response = await client.get(f"/activities/{notification.id}/")

    assert response.status_code == 404


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

    response = await client.delete(f"/activities/{notification.id}/clear_notification/")

    assert response.status_code == 204
    assert (await client.get("/activities/")).json()["count"] == 0
    assert await session.get(Notification, notification.id) is not None


async def test_get_cannot_soft_delete_an_activity(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    notification: Notification,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """GET is read-only and cannot soft-delete an activity."""
    await mark_seen(dal, user, session)
    as_user(user)

    response = await client.get(
        f"/activities/{notification.id}/clear_notification/"
    )

    assert response.status_code == 405
    assert (await client.get("/activities/")).json()["count"] == 3
    assert await session.get(Notification, notification.id) is not None


async def test_get_cannot_soft_delete_all_activities(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    notifications: List[Notification],
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """GET is read-only and cannot clear the activity collection."""
    await mark_seen(dal, user, session)
    as_user(user)

    response = await client.get("/activities/clear_activities/")

    assert response.status_code == 405
    assert (await client.get("/activities/")).json()["count"] == 3


async def test_clear_notification_reports_a_missing_activity(
    client: AsyncClient, user: User, as_user: Callable[[Any], None]
) -> None:
    """Clearing something that is not there gives a 404."""
    as_user(user)

    response = await client.delete("/activities/9999/clear_notification/")
    assert response.status_code == 404


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

    response = await client.delete("/activities/clear_activities/")

    assert response.status_code == 204
    assert (await client.get("/activities/")).json()["count"] == 0


async def test_group_member_can_clear_group_activities(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """The clear-all API action includes seen notifications addressed to groups."""
    notification = await dal.create_notification(
        verb="group activity", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    await dal.mark_all_as_seen(group_user)
    await session.commit()
    as_user(group_user)

    response = await client.delete("/activities/clear_activities/")

    assert response.status_code == 204
    assert (await client.get("/activities/")).json()["count"] == 0
    assert await session.get(Notification, notification.id) is not None
    assert len(await dal.deleted(group_user)) == 1


async def test_soft_delete_routes_can_be_switched_off(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """With soft delete disabled, the clearing routes are absent."""
    as_user(user)

    async with client_factory(API_INCLUDE_SOFT_DELETE=False) as client:
        assert (await client.delete("/activities/clear_activities/")).status_code == 404
        response = await client.delete(
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

    assert (await client.delete("/activities/delete_activities/")).status_code == 404
    response = await client.delete(
        f"/activities/{notification.id}/delete_notification/"
    )

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
        response = await client.delete(
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
        response = await client.delete("/activities/9999/delete_notification/")

    assert response.status_code == 404


async def test_delete_activities_destroys_sent_notifications_as_admin(
    client_factory: Callable[..., AsyncClient],
    notifications: List[Notification],
    staff_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """The explicit staff-only operation can delete sent notifications globally."""
    as_user(staff_user)
    notification_ids = [item.id for item in notifications]

    async with client_factory(API_INCLUDE_HARD_DELETE=True) as client:
        response = await client.delete("/activities/delete_activities/")

    assert response.status_code == 204
    session.expire_all()
    remaining = [
        await session.get(Notification, item_id) for item_id in notification_ids
    ]
    assert all(item is None for item in remaining)


async def test_get_cannot_permanently_delete_notifications(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    staff_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """GET cannot trigger either administrative deletion operation."""
    as_user(staff_user)
    notification_id = notification.id

    async with client_factory(API_INCLUDE_HARD_DELETE=True) as client:
        single = await client.get(
            f"/activities/{notification_id}/delete_notification/"
        )
        bulk = await client.get("/activities/delete_activities/")

    assert single.status_code == 405
    assert bulk.status_code == 405
    session.expire_all()
    assert await session.get(Notification, notification_id) is not None


async def test_hard_delete_is_refused_to_regular_users(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Permanent deletion is reserved for admins."""
    as_user(user)

    async with client_factory(API_INCLUDE_HARD_DELETE=True) as client:
        single = await client.delete(
            f"/activities/{notification.id}/delete_notification/"
        )
        everything = await client.delete("/activities/delete_activities/")

    assert single.status_code == 403
    assert everything.status_code == 403


async def test_hard_delete_is_refused_to_superuser_without_staff(
    client_factory: Callable[..., AsyncClient],
    notification: Notification,
    superuser_only: User,
    as_user: Callable[[Any], None],
) -> None:
    """Superuser status alone does not grant the explicit admin permission."""
    as_user(superuser_only)

    async with client_factory(API_INCLUDE_HARD_DELETE=True) as client:
        response = await client.delete(
            f"/activities/{notification.id}/delete_notification/"
        )

    assert response.status_code == 403


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
