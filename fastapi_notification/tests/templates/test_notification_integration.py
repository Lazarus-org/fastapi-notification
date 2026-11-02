"""Tests that the notification DAL consumes rendered template snapshots."""

from unittest.mock import AsyncMock, patch

import pytest

from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.repository.manager.templates import (
    RenderedNotificationTemplate,
)


@pytest.mark.asyncio
async def test_create_notification_uses_rendered_template_and_provenance():
    session = AsyncMock()
    notification = object()
    rendered = RenderedNotificationTemplate(
        verb="payment received",
        description="Order A-42 has been paid.",
        category="orders",
        key="orders.payment_received",
        locale="en",
    )

    with patch(
        "fastapi_notification.repository.manager.templates."
        "NotificationTemplateDataAccessLayer.render",
        new=AsyncMock(return_value=rendered),
    ), patch(
        "fastapi_notification.repository.manager.notification.queryset."
        "create_notification",
        new=AsyncMock(return_value=notification),
    ) as create:
        result = await NotificationDataAccessLayer(session).create_notification(
            actor=object(),
            template_key="orders.payment_received",
            template_context={"order_number": "A-42"},
        )

    assert result is notification
    kwargs = create.await_args.kwargs
    assert kwargs["verb"] == "payment received"
    assert kwargs["description"] == "Order A-42 has been paid."
    assert kwargs["category"] == "orders"
    assert kwargs["template_key"] == "orders.payment_received"
    assert kwargs["locale"] == "en"


@pytest.mark.asyncio
async def test_manual_notification_still_requires_verb():
    with pytest.raises(ValueError, match="verb is required"):
        await NotificationDataAccessLayer(AsyncMock()).create_notification(
            actor=object()
        )


@pytest.mark.asyncio
async def test_notification_requires_actor_even_when_template_is_used():
    with pytest.raises(ValueError, match="actor is required"):
        await NotificationDataAccessLayer(AsyncMock()).create_notification(
            template_key="orders.payment_received"
        )
