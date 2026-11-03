"""Tests for notification summary and preview endpoints."""

from datetime import datetime, timezone
from typing import Any, Callable, List

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.api.routers.notification import create_router
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


async def test_summary_counts_total_unread_and_read(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    session: AsyncSession,
    dal: NotificationDataAccessLayer,
    as_user: Callable[[Any], None],
) -> None:
    """Summary counts all visible sent notifications by the caller's read state."""
    await notifications[0].mark_as_seen(session, user)
    await dal.delete_notification(notifications[1].id, recipient=user, soft_delete=True)
    await session.commit()
    as_user(user)

    response = await client.get("/notifications/summary/")

    assert response.status_code == 200
    assert response.json() == {
        "total": 2,
        "unread": 1,
        "read": 1,
        "by_category": {"general": {"total": 2, "unread": 1, "read": 1}},
        "by_priority": {"normal": {"total": 2, "unread": 1, "read": 1}},
    }


async def test_summary_breaks_counts_down_by_category_and_priority(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Summary dimensions retain independent total/read/unread counts."""
    order_read = await dal.create_notification(
        verb="paid order",
        actor=user,
        recipients=user,
        category="orders",
        priority="normal",
        is_sent=True,
    )
    await dal.create_notification(
        verb="urgent order",
        actor=user,
        recipients=user,
        category="orders",
        priority="urgent",
        is_sent=True,
    )
    await dal.create_notification(
        verb="social update",
        actor=user,
        recipients=user,
        category="social",
        priority="low",
        is_sent=True,
    )
    await dal.create_notification(
        verb="security alert",
        actor=user,
        recipients=user,
        category="security",
        priority="high",
        is_sent=True,
    )
    await order_read.mark_as_seen(session, user)
    await session.commit()
    as_user(user)

    response = await client.get("/notifications/summary/")

    assert response.status_code == 200
    assert response.json() == {
        "total": 4,
        "unread": 3,
        "read": 1,
        "by_category": {
            "orders": {"total": 2, "unread": 1, "read": 1},
            "social": {"total": 1, "unread": 1, "read": 0},
            "security": {"total": 1, "unread": 1, "read": 0},
        },
        "by_priority": {
            "normal": {"total": 1, "unread": 0, "read": 1},
            "urgent": {"total": 1, "unread": 1, "read": 0},
            "low": {"total": 1, "unread": 1, "read": 0},
            "high": {"total": 1, "unread": 1, "read": 0},
        },
    }

    filtered = await client.get(
        "/notifications/summary/?category=orders&priority=urgent"
    )
    assert filtered.status_code == 200
    assert filtered.json() == {
        "total": 1,
        "unread": 1,
        "read": 0,
        "by_category": {"orders": {"total": 1, "unread": 1, "read": 0}},
        "by_priority": {"urgent": {"total": 1, "unread": 1, "read": 0}},
    }


async def test_summary_includes_group_notifications(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Group-addressed notifications contribute to the member's counts."""
    notification = await dal.create_notification(
        verb="group announcement", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    as_user(group_user)

    unread = await client.get("/notifications/summary/")
    assert unread.json() == {
        "total": 1,
        "unread": 1,
        "read": 0,
        "by_category": {"general": {"total": 1, "unread": 1, "read": 0}},
        "by_priority": {"normal": {"total": 1, "unread": 1, "read": 0}},
    }

    await notification.mark_as_seen(session, group_user)
    await session.commit()

    read = await client.get("/notifications/summary/")
    assert read.json() == {
        "total": 1,
        "unread": 0,
        "read": 1,
        "by_category": {"general": {"total": 1, "unread": 0, "read": 1}},
        "by_priority": {"normal": {"total": 1, "unread": 0, "read": 1}},
    }


async def test_summary_does_not_double_count_direct_and_group_audience(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """A notification addressed to both audiences is counted once."""
    await dal.create_notification(
        verb="both audiences",
        actor=user,
        recipients=group_user,
        groups=group,
        is_sent=True,
    )
    await session.commit()
    as_user(group_user)

    response = await client.get("/notifications/summary/")

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "unread": 1,
        "read": 0,
        "by_category": {"general": {"total": 1, "unread": 1, "read": 0}},
        "by_priority": {"normal": {"total": 1, "unread": 1, "read": 0}},
    }


async def test_summary_excludes_unsent_and_other_users_notifications(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    other_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Only sent notifications in the authenticated user's audience are counted."""
    await dal.create_notification(
        verb="visible", actor=user, recipients=user, is_sent=True
    )
    await dal.create_notification(
        verb="not sent", actor=user, recipients=user, is_sent=False
    )
    await dal.create_notification(
        verb="someone else's", actor=user, recipients=other_user, is_sent=True
    )
    await session.commit()
    as_user(user)

    response = await client.get("/notifications/summary/")

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "unread": 1,
        "read": 0,
        "by_category": {"general": {"total": 1, "unread": 1, "read": 0}},
        "by_priority": {"normal": {"total": 1, "unread": 1, "read": 0}},
    }


async def test_summary_honours_notification_filters(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Summary counts use the same status filters as notification listings."""
    await dal.create_notification(
        verb="urgent", actor=user, recipients=user, status="CRITICAL", is_sent=True
    )
    await dal.create_notification(
        verb="routine", actor=user, recipients=user, status="INFO", is_sent=True
    )
    await session.commit()
    as_user(user)

    response = await client.get("/notifications/summary/?status=CRITICAL")

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "unread": 1,
        "read": 0,
        "by_category": {"general": {"total": 1, "unread": 1, "read": 0}},
        "by_priority": {"normal": {"total": 1, "unread": 1, "read": 0}},
    }


async def test_preview_returns_recent_read_and_unread_items(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Preview includes both read states and orders newest notifications first."""
    notifications[0].timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc)
    notifications[1].timestamp = datetime(2024, 1, 2, tzinfo=timezone.utc)
    notifications[2].timestamp = datetime(2024, 1, 3, tzinfo=timezone.utc)
    await notifications[0].mark_as_seen(session, user)
    await session.commit()
    as_user(user)

    response = await client.get("/notifications/preview/?limit=3&ordering=id")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["results"]] == [
        notifications[2].id,
        notifications[1].id,
        notifications[0].id,
    ]
    assert [item["is_seen"] for item in body["results"]] == [False, False, True]
    assert set(body["results"][0]) == {
        "id",
        "title",
        "description",
        "status",
        "category",
        "priority",
        "link",
        "timestamp",
        "expires_at",
        "template_key",
        "locale",
        "is_seen",
    }


async def test_preview_includes_category_and_priority(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Preview exposes taxonomy values without changing notification status."""
    await dal.create_notification(
        verb="payment failed",
        actor=user,
        recipients=user,
        status="ERROR",
        category="financial",
        priority="urgent",
        is_sent=True,
    )
    await session.commit()
    as_user(user)

    response = await client.get("/notifications/preview/")

    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["status"] == "ERROR"
    assert item["category"] == "financial"
    assert item["priority"] == "urgent"


async def test_taxonomy_filters_reject_invalid_query_values(
    client: AsyncClient,
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Invalid category and priority query values are rejected as 422."""
    as_user(user)

    invalid_category = await client.get("/notifications/?category=bad%20category")
    invalid_priority = await client.get("/notifications/?priority=immediate")

    assert invalid_category.status_code == 422
    assert invalid_priority.status_code == 422


async def test_preview_is_bounded_and_validates_limit(
    client: AsyncClient,
    notifications: List[Notification],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Preview accepts limits from 1 to 20 and rejects values outside the range."""
    as_user(user)

    valid = await client.get("/notifications/preview/?limit=2")
    too_small = await client.get("/notifications/preview/?limit=0")
    too_large = await client.get("/notifications/preview/?limit=21")

    assert valid.status_code == 200
    assert len(valid.json()["results"]) == 2
    assert too_small.status_code == 422
    assert too_large.status_code == 422


async def test_preview_includes_group_notifications(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Members can preview notifications sent to their groups."""
    await dal.create_notification(
        verb="group preview", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    as_user(group_user)

    response = await client.get("/notifications/preview/")

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["results"][0]["description"] == "ann group preview"


async def test_preview_excludes_cleared_unsent_and_other_users_items(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    other_user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Preview cannot expose unsent, cleared or another user's notifications."""
    visible = await dal.create_notification(
        verb="visible", actor=user, recipients=user, is_sent=True
    )
    cleared = await dal.create_notification(
        verb="cleared", actor=user, recipients=user, is_sent=True
    )
    await dal.create_notification(
        verb="queued", actor=user, recipients=user, is_sent=False
    )
    await dal.create_notification(
        verb="private to other", actor=user, recipients=other_user, is_sent=True
    )
    await session.commit()
    await dal.delete_notification(cleared.id, recipient=user, soft_delete=True)
    await session.commit()
    as_user(user)

    response = await client.get("/notifications/preview/")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["results"]] == [visible.id]


async def test_preview_honours_notification_filters(
    client: AsyncClient,
    dal: NotificationDataAccessLayer,
    user: User,
    session: AsyncSession,
    as_user: Callable[[Any], None],
) -> None:
    """Preview applies the same status filter as the inbox and summary."""
    await dal.create_notification(
        verb="urgent", actor=user, recipients=user, status="CRITICAL", is_sent=True
    )
    await dal.create_notification(
        verb="routine", actor=user, recipients=user, status="INFO", is_sent=True
    )
    await session.commit()
    as_user(user)

    response = await client.get("/notifications/preview/?status=CRITICAL")

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["results"][0]["status"] == "CRITICAL"


async def test_staff_receives_only_their_own_summary_and_preview(
    client: AsyncClient,
    notification: Notification,
    staff_user: User,
    as_user: Callable[[Any], None],
) -> None:
    """Elevated role flags do not widen summary or preview audience access."""
    as_user(staff_user)

    summary = await client.get("/notifications/summary/")
    preview = await client.get("/notifications/preview/")

    assert summary.json() == {
        "total": 0,
        "unread": 0,
        "read": 0,
        "by_category": {},
        "by_priority": {},
    }
    assert preview.json() == {"results": []}


async def test_superuser_receives_only_their_own_summary_and_preview(
    client: AsyncClient,
    notification: Notification,
    superuser_only: User,
    as_user: Callable[[Any], None],
) -> None:
    """Superuser status alone does not widen summary or preview audience access."""
    as_user(superuser_only)

    summary = await client.get("/notifications/summary/")
    preview = await client.get("/notifications/preview/")

    assert summary.json() == {
        "total": 0,
        "unread": 0,
        "read": 0,
        "by_category": {},
        "by_priority": {},
    }
    assert preview.json() == {"results": []}


async def test_summary_and_preview_require_authentication(
    client: AsyncClient,
    as_user: Callable[[Any], None],
) -> None:
    """Both endpoints reject an anonymous caller."""
    as_user(None)

    summary = await client.get("/notifications/summary/")
    preview = await client.get("/notifications/preview/")

    assert summary.status_code == 401
    assert preview.status_code == 401


async def test_summary_and_preview_are_not_registered_when_listing_is_disabled(
    client_factory: Callable[..., AsyncClient],
    user: User,
    as_user: Callable[[Any], None],
) -> None:
    """The list feature flag also controls summary and preview routes."""
    as_user(user)

    async with client_factory(API_ALLOW_LIST=False) as client:
        summary = await client.get("/notifications/summary/")
        preview = await client.get("/notifications/preview/")

    assert summary.status_code == 404
    assert preview.status_code == 404


def test_openapi_documents_summary_and_preview_as_read_only_get_routes() -> None:
    """OpenAPI documents both new read endpoints with their response schemas."""

    async def session_dependency() -> Any:
        yield None

    async def user_dependency() -> Any:
        return object()

    app = FastAPI()
    app.include_router(
        create_router(
            session_dependency=session_dependency,
            current_user_dependency=user_dependency,
        )
    )
    paths = app.openapi()["paths"]

    assert set(paths["/notifications/summary/"]) == {"get"}
    assert set(paths["/notifications/preview/"]) == {"get"}
    assert "NotificationSummaryResponse" in app.openapi()["components"]["schemas"]
    assert "NotificationPreviewResponse" in app.openapi()["components"]["schemas"]
