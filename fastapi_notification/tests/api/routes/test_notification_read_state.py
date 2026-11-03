"""Tests for explicit notification read/unread API actions."""

from typing import Any, Callable

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


async def test_post_marks_notification_as_unseen_and_updates_inbox_views(
    client: AsyncClient,
    notification: Notification,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Unseeing restores the item to the inbox and updates summary/preview."""
    await notification.mark_as_seen(session, user)
    await session.commit()
    as_user(user)
    path = f"/notifications/{notification.id}/mark_as_unseen/"

    response = await client.post(path)

    assert response.status_code == 204
    assert (await client.get("/notifications/")).json()["count"] == 1
    assert (await client.get("/activities/")).json()["count"] == 0
    assert (await client.get("/notifications/summary/")).json() == {
        "total": 1,
        "unread": 1,
        "read": 0,
        "by_category": {"general": {"total": 1, "unread": 1, "read": 0}},
        "by_priority": {"normal": {"total": 1, "unread": 1, "read": 0}},
    }
    preview = (await client.get("/notifications/preview/")).json()
    assert preview["results"][0]["is_seen"] is False


async def test_post_mark_as_unseen_is_idempotent(
    client: AsyncClient,
    notification: Notification,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Repeating mark-as-unseen remains a successful no-op."""
    await notification.mark_as_seen(session, user)
    await session.commit()
    as_user(user)
    path = f"/notifications/{notification.id}/mark_as_unseen/"

    first = await client.post(path)
    second = await client.post(path)

    assert first.status_code == 204
    assert second.status_code == 204
    assert (await client.get("/notifications/")).json()["count"] == 1
    assert (await client.get("/activities/")).json()["count"] == 0


async def test_get_cannot_mark_notification_as_unseen(
    client: AsyncClient,
    notification: Notification,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """GET is not registered for the state-changing action."""
    await notification.mark_as_seen(session, user)
    await session.commit()
    as_user(user)

    response = await client.get(f"/notifications/{notification.id}/mark_as_unseen/")

    assert response.status_code == 405
    assert (await client.get("/activities/")).json()["count"] == 1


async def test_group_member_can_mark_group_notification_as_unseen(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Current group membership grants access to the read-state transition."""
    notification = await dal.create_notification(
        verb="group update", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    await notification.mark_as_seen(session, group_user)
    await session.commit()
    as_user(group_user)

    response = await client.post(f"/notifications/{notification.id}/mark_as_unseen/")

    assert response.status_code == 204
    assert (await client.get("/notifications/")).json()["count"] == 1
    assert (await client.get("/activities/")).json()["count"] == 0


async def test_mark_as_unseen_hides_another_users_notification(
    client: AsyncClient,
    notification: Notification,
    other_user: User,
    as_user: Callable[[Any], None],
) -> None:
    """An unrelated user cannot change another user's read state."""
    as_user(other_user)

    response = await client.post(f"/notifications/{notification.id}/mark_as_unseen/")

    assert response.status_code == 404


async def test_mark_as_unseen_hides_a_cleared_notification(
    client: AsyncClient,
    notification: Notification,
    user: User,
    session: AsyncSession,
    dal: NotificationDataAccessLayer,
    as_user: Callable[[Any], None],
) -> None:
    """A cleared item cannot be restored to the inbox by changing read state."""
    await notification.mark_as_seen(session, user)
    await dal.delete_notification(notification.id, recipient=user, soft_delete=True)
    await session.commit()
    as_user(user)

    response = await client.post(f"/notifications/{notification.id}/mark_as_unseen/")

    assert response.status_code == 404
    assert (await client.get("/notifications/")).json()["count"] == 0
    assert (await client.get("/activities/")).json()["count"] == 0


async def test_mark_as_unseen_hides_an_unsent_notification(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Unsent notifications are not exposed by the state-changing endpoint."""
    notification = await dal.create_notification(
        verb="draft", actor=user, recipients=user, is_sent=False
    )
    await session.commit()
    as_user(user)

    response = await client.post(f"/notifications/{notification.id}/mark_as_unseen/")

    assert response.status_code == 404


async def test_mark_as_unseen_is_a_noop_when_already_unseen(
    client: AsyncClient,
    notification: Notification,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """The action succeeds even when the current user has no seen row."""
    as_user(user)

    response = await client.post(f"/notifications/{notification.id}/mark_as_unseen/")

    assert response.status_code == 204
    assert (await client.get("/notifications/")).json()["count"] == 1
