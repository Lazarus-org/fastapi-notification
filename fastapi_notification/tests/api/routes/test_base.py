import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.api.routes.base import BaseNotificationRoutes
from fastapi_notification.api.schemas.dynamic_notification import (
    NotificationDynamicSerializer,
)
from fastapi_notification.api.schemas.notification import NotificationSerializer
from fastapi_notification.models.auth import User
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.api, pytest.mark.api_routes]


class Viewer:
    """A stand-in user, so the shared logic can be tested in isolation."""

    def __init__(self, is_staff: bool = False) -> None:
        self.id = 1
        self.is_staff = is_staff


async def test_the_base_router_supplies_no_statement(
    session: AsyncSession, user: User
) -> None:
    """The shared base leaves the statement to each concrete router."""
    routes = BaseNotificationRoutes()

    with pytest.raises(NotImplementedError):
        await routes.get_statement(session, user)


def test_regular_users_get_the_dynamic_serializer() -> None:
    """A regular user gets the compact serializer."""
    routes = BaseNotificationRoutes()

    assert routes.get_serializer_class(Viewer()) is NotificationDynamicSerializer


def test_staff_get_the_same_default_serializer_as_regular_users() -> None:
    """Staff status does not reveal additional notification fields."""
    routes = BaseNotificationRoutes()

    assert (
        routes.get_serializer_class(Viewer(is_staff=True))
        is NotificationDynamicSerializer
    )


def test_full_details_can_be_forced_for_everyone() -> None:
    """Turning on full details gives everyone the detailed serializer."""
    configure(SERIALIZER_INCLUDE_FULL_DETAILS=True)
    routes = BaseNotificationRoutes()

    assert routes.get_serializer_class(Viewer()) is NotificationSerializer


def test_a_configured_serializer_replaces_the_default() -> None:
    """A configured serializer is used for regular users."""
    configure(
        SERIALIZER_CLASS=(
            "fastapi_notification.api.schemas.notification.NotificationSerializer"
        )
    )
    routes = BaseNotificationRoutes()

    assert routes.get_serializer_class(Viewer()) is NotificationSerializer


def test_detail_is_not_forced_by_default() -> None:
    """With nothing configured, summary rows are enough."""
    assert BaseNotificationRoutes().wants_detail(False) is False


def test_detail_is_forced_by_a_configured_field_list() -> None:
    """A configured field list may name fields absent from the summary."""
    configure(SERIALIZER_FIELDS=["id", "verb"])

    assert BaseNotificationRoutes().wants_detail(False) is True


def test_detail_is_forced_when_asked_for() -> None:
    """Asking for detail is always honoured."""
    assert BaseNotificationRoutes().wants_detail(True) is True
