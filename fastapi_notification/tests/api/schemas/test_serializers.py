from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.api.schemas.dynamic_notification import (
    NotificationDynamicSerializer,
)
from fastapi_notification.api.schemas.group import GroupSerializer, PermissionSerializer
from fastapi_notification.api.schemas.helper.get_serializer_cls import (
    group_serializer_class,
    user_serializer_class,
)
from fastapi_notification.api.schemas.notification import NotificationSerializer
from fastapi_notification.api.schemas.user import UserSerializer, build_user_serializer
from fastapi_notification.models.auth import Group, Permission, User
from fastapi_notification.models.notification import Notification
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.api, pytest.mark.api_schemas]


async def test_user_serializer_uses_the_configured_fields(user: User) -> None:
    """A user is rendered with exactly the configured fields."""
    assert UserSerializer.to_representation(user) == {"id": user.id}


async def test_user_serializer_honours_a_narrowed_field_list(user: User) -> None:
    """Narrowing the field list narrows the response."""
    configure(USER_SERIALIZER_FIELDS=["username"])

    assert build_user_serializer().to_representation(user) == {"username": "ann"}


async def test_group_serializer_includes_its_permissions(
    session: AsyncSession,
) -> None:
    """A group is rendered together with the permissions it grants."""
    permission = Permission(name="Can clear", codename="clear_notification")
    session.add(permission)
    await session.flush()

    group = Group(name="clearers", permissions=[permission])
    session.add(group)
    await session.commit()
    await session.refresh(group)

    data = GroupSerializer.to_representation(group)

    assert data["name"] == "clearers"
    assert data["permissions"][0]["codename"] == "clear_notification"


async def test_group_serializer_handles_a_group_without_permissions(
    group: Group,
) -> None:
    """A group granting nothing renders with an empty permission list."""
    assert GroupSerializer.to_representation(group)["permissions"] == []


def test_permission_serializer_renders_a_permission() -> None:
    """A permission renders its identifying fields."""
    permission = Permission(id=1, name="Can clear", codename="clear_notification")

    assert PermissionSerializer.to_representation(permission) == {
        "id": 1,
        "name": "Can clear",
        "codename": "clear_notification",
    }


async def test_notification_serializer_expands_related_objects(
    notification: Notification, session: AsyncSession
) -> None:
    """A notification is rendered with its recipients and content types."""
    await session.refresh(notification)

    data = NotificationSerializer.to_representation(notification)

    assert data["id"] == notification.id
    assert data["verb"] == "liked your post"
    assert data["category"] == "general"
    assert data["priority"] == "normal"
    assert data["recipient"] == [{"id": user.id}]
    assert data["actor_content_type"] == "auth.user"
    assert data["target_content_type"] is None
    assert data["title"].startswith("ann liked your post")


async def test_notification_serializer_can_drop_empty_fields(
    notification: Notification, session: AsyncSession
) -> None:
    """Null fields can be stripped from the response."""
    configure(SERIALIZER_EXCLUDE_NULL_FIELDS=True)
    await session.refresh(notification)

    data = NotificationSerializer.to_representation(notification)

    assert "target_content_type" not in data
    assert "link" not in data
    assert data["verb"] == "liked your post"


def test_dynamic_serializer_defaults_to_a_title_and_summary() -> None:
    """With nothing configured, a summary row plus a title is returned."""
    timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
    row = {
        "id": 1,
        "description": "ann waved",
        "status": "INFO",
        "category": "orders",
        "priority": "urgent",
        "link": None,
        "timestamp": timestamp,
    }

    data = NotificationDynamicSerializer.to_representation(row)

    assert data["title"] == "ann waved 1 hour ago"
    assert data["id"] == 1
    assert data["status"] == "INFO"
    assert data["category"] == "orders"
    assert data["priority"] == "urgent"


def test_dynamic_serializer_honours_a_configured_field_list() -> None:
    """A configured field list is served exactly."""
    configure(SERIALIZER_FIELDS=["id", "verb"])

    data = NotificationDynamicSerializer.to_representation(
        {"id": 1, "verb": "waved", "status": "INFO"}
    )

    assert data == {"id": 1, "verb": "waved"}


def test_dynamic_serializer_titles_a_configured_row_by_its_string_form() -> None:
    """When fields are configured, the title is the row's own rendering."""
    configure(SERIALIZER_FIELDS=["title", "id"])

    data = NotificationDynamicSerializer.to_representation({"id": 1})

    assert data["id"] == 1
    assert data["title"] == "{'id': 1}"


async def test_dynamic_serializer_reads_model_instances(
    notification: Notification, session: AsyncSession
) -> None:
    """Whole notifications are rendered as readily as summary rows."""
    await session.refresh(notification)

    data = NotificationDynamicSerializer.to_representation(notification)

    assert data["id"] == notification.id
    assert data["title"].startswith("ann liked your post")


def test_dynamic_serializer_can_drop_empty_fields() -> None:
    """Null fields can be stripped from the response."""
    configure(SERIALIZER_EXCLUDE_NULL_FIELDS=True)

    data = NotificationDynamicSerializer.to_representation(
        {"id": 1, "description": "ann waved", "status": "INFO", "link": None}
    )

    assert "link" not in data


def test_dynamic_serializer_renders_many_rows() -> None:
    """A page of rows is rendered in one call."""
    rows = [{"id": index, "description": "waved"} for index in range(3)]

    assert len(NotificationDynamicSerializer.to_representation_many(rows)) == 3


def test_dynamic_serializer_reports_missing_fields_as_none() -> None:
    """A configured field absent from the row renders as null."""
    configure(SERIALIZER_FIELDS=["id", "link"])

    assert NotificationDynamicSerializer.to_representation({"id": 1}) == {
        "id": 1,
        "link": None,
    }


def test_the_default_helper_classes_are_used() -> None:
    """With nothing configured, the packaged serializers are used."""
    assert user_serializer_class() is UserSerializer
    assert group_serializer_class() is GroupSerializer


def test_configured_helper_classes_are_used() -> None:
    """Configured serializers replace the packaged ones."""
    configure(
        USER_SERIALIZER_CLASS=(
            "fastapi_notification.api.schemas.group.PermissionSerializer"
        ),
        GROUP_SERIALIZER_CLASS=(
            "fastapi_notification.api.schemas.user.UserSerializer"
        ),
    )

    assert user_serializer_class() is PermissionSerializer
    assert group_serializer_class() is UserSerializer
