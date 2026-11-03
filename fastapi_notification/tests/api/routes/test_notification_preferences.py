"""API tests for authenticated notification preference management."""

from typing import Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import User

pytestmark = [pytest.mark.api, pytest.mark.api_routes]


async def test_list_preferences_returns_only_current_users_rules(
    client: AsyncClient,
    user: User,
    other_user: User,
    as_user: Callable[[object], None],
    session: AsyncSession,
) -> None:
    from fastapi_notification.repository.manager.preferences import (
        NotificationPreferenceDataAccessLayer,
    )

    dal = NotificationPreferenceDataAccessLayer(session)
    await dal.set_preference(user, category="orders", channel="email", enabled=False)
    await dal.set_preference(
        other_user, category="security", channel="push", enabled=False
    )
    await session.commit()
    as_user(user)

    response = await client.get("/notifications/preferences/")
    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["results"][0]["category"] == "orders"
    assert response.json()["results"][0]["channel"] == "email"
    assert response.json()["results"][0]["enabled"] is False
    assert response.json()["results"][0]["updated_at"].endswith("Z")


async def test_update_and_reset_preference(
    client: AsyncClient, user: User, as_user: Callable[[object], None]
) -> None:
    as_user(user)
    response = await client.put(
        "/notifications/preferences/",
        json={"category": "Orders", "channel": "email", "enabled": False},
    )
    assert response.status_code == 200
    assert response.json()["category"] == "orders"
    assert response.json()["channel"] == "email"
    assert response.json()["enabled"] is False

    response = await client.delete(
        "/notifications/preferences/?category=orders&channel=email"
    )
    assert response.status_code == 204


async def test_preference_endpoints_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/notifications/preferences/")
    assert response.status_code == 401


async def test_invalid_preference_payload_is_rejected(
    client: AsyncClient, user: User, as_user: Callable[[object], None]
) -> None:
    as_user(user)
    response = await client.put(
        "/notifications/preferences/",
        json={"category": "not valid", "channel": "email", "enabled": False},
    )
    assert response.status_code == 422


def test_preferences_routes_are_in_openapi() -> None:
    from fastapi import FastAPI

    from fastapi_notification.api.routers.notification import create_router

    app = FastAPI()
    app.include_router(create_router())
    paths = app.openapi()["paths"]
    preference_path = paths["/notifications/preferences/"]
    assert "get" in preference_path
    assert "put" in preference_path
    assert "delete" in preference_path
