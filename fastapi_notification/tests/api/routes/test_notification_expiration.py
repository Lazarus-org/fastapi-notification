"""API regression tests for notification expiration visibility."""

from datetime import datetime, timedelta, timezone
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


async def test_expired_direct_notifications_are_hidden_from_inbox_summary_and_preview(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """An expired direct notification disappears consistently from recipient views."""
    now = datetime.now(timezone.utc)
    expired = await dal.create_notification(
        verb="expired direct",
        actor=user,
        recipients=user,
        is_sent=True,
        expires_at=now - timedelta(seconds=1),
    )
    active = await dal.create_notification(
        verb="active direct",
        actor=user,
        recipients=user,
        is_sent=True,
        expires_at=now + timedelta(days=1),
    )
    await session.commit()
    as_user(user)

    inbox = await client.get("/notifications/")
    summary = await client.get("/notifications/summary/")
    preview = await client.get("/notifications/preview/")

    assert inbox.status_code == 200
    assert [row["id"] for row in inbox.json()["results"]] == [active.id]
    assert summary.json() == {"total": 1, "unread": 1, "read": 0}
    assert [row["id"] for row in preview.json()["results"]] == [active.id]
    assert preview.json()["results"][0]["expires_at"] is not None

    seen = await client.post(f"/notifications/{expired.id}/mark_as_seen/")
    unseen = await client.post(f"/notifications/{expired.id}/mark_as_unseen/")
    retrieve = await client.get(f"/notifications/{expired.id}/")
    assert seen.status_code == 404
    assert unseen.status_code == 404
    assert retrieve.status_code == 404


async def test_expiration_is_applied_to_group_recipients_and_activity_history(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Group members lose expired items from both inbox and activity views."""
    now = datetime.now(timezone.utc)
    expired = await dal.create_notification(
        verb="expired group",
        actor=user,
        groups=group,
        is_sent=True,
        expires_at=now + timedelta(days=1),
    )
    active = await dal.create_notification(
        verb="active group",
        actor=user,
        groups=group,
        is_sent=True,
    )
    await expired.mark_as_seen(session, group_user)
    await active.mark_as_seen(session, group_user)
    await dal.update_notification(
        expired.id,
        expires_at=now - timedelta(seconds=1),
    )
    await session.commit()
    as_user(group_user)

    inbox = await client.get("/notifications/")
    activities = await client.get("/activities/")
    summary = await client.get("/notifications/summary/")

    assert [row["id"] for row in inbox.json()["results"]] == []
    assert [row["id"] for row in activities.json()["results"]] == [active.id]
    assert summary.json() == {"total": 1, "unread": 0, "read": 1}


async def test_expired_notifications_remain_in_database_until_explicit_cleanup(
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
) -> None:
    """Expiry changes visibility but does not automatically delete history."""
    expired = await dal.create_notification(
        verb="historical expired",
        actor=user,
        recipients=user,
        is_sent=True,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    await session.commit()

    raw = await dal.all_notifications(display_detail=True)

    assert any(item.id == expired.id for item in raw)
    assert await session.get(Notification, expired.id) is not None
