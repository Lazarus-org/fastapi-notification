"""Tests for notification category and priority semantics."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models import (
    NotificationCategory,
    NotificationPriority,
    NotificationStatus,
)
from fastapi_notification.models.auth import User
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)

pytestmark = [pytest.mark.models, pytest.mark.models_notification]


async def test_create_notification_uses_taxonomy_defaults(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Existing callers receive stable general/normal defaults."""
    notification = await dal.create_notification(verb="created", actor=user)
    await session.flush()

    assert notification.category == "general"
    assert notification.priority == "normal"
    assert notification.status == NotificationStatus.INFO.value


async def test_create_notification_accepts_builtin_category_and_priority_enums(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """String enums can be passed directly to the DAL."""
    notification = await dal.create_notification(
        verb="security event",
        actor=user,
        category=NotificationCategory.SECURITY,
        priority=NotificationPriority.URGENT,
    )
    await session.flush()

    assert notification.category == "security"
    assert notification.priority == "urgent"


async def test_create_notification_normalizes_custom_category(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Custom category keys are trimmed and normalized to lowercase."""
    notification = await dal.create_notification(
        verb="invoice created",
        actor=user,
        category="  Com.Example.Billing  ",
    )
    await session.flush()

    assert notification.category == "com.example.billing"


@pytest.mark.parametrize("category", ["", "bad category", "_leading", "x" * 65])
async def test_create_notification_rejects_invalid_category(
    dal: NotificationDataAccessLayer, user: User, category: str
) -> None:
    """Category keys must follow the documented safe key format."""
    with pytest.raises(ValueError, match="category"):
        await dal.create_notification(
            verb="invalid category", actor=user, category=category
        )


async def test_create_notification_rejects_non_string_category(
    dal: NotificationDataAccessLayer, user: User
) -> None:
    """Category keys cannot be arbitrary objects."""
    with pytest.raises(TypeError, match="category"):
        await dal.create_notification(  # type: ignore[arg-type]
            verb="invalid category", actor=user, category=123
        )


@pytest.mark.parametrize("priority", ["", "immediate", "critical", "5"])
async def test_create_notification_rejects_unknown_priority(
    dal: NotificationDataAccessLayer, user: User, priority: str
) -> None:
    """Only the four documented urgency levels are accepted."""
    with pytest.raises(ValueError, match="priority"):
        await dal.create_notification(
            verb="invalid priority", actor=user, priority=priority
        )


async def test_update_notification_changes_category_and_priority(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Taxonomy fields can be updated independently from status."""
    notification = await dal.create_notification(
        verb="invoice created", actor=user, status="SUCCESS"
    )
    updated = await dal.update_notification(
        notification.id,
        category="financial",
        priority="high",
    )
    await session.flush()

    assert updated.category == "financial"
    assert updated.priority == "high"
    assert updated.status == "SUCCESS"


async def test_update_notification_rejects_invalid_taxonomy(
    dal: NotificationDataAccessLayer, user: User
) -> None:
    """Invalid values cannot be introduced by an update."""
    notification = await dal.create_notification(verb="invoice", actor=user)

    with pytest.raises(ValueError, match="priority"):
        await dal.update_notification(notification.id, priority="immediate")


async def test_model_validators_normalize_direct_assignments() -> None:
    """Direct ORM assignments receive the same validation as DAL writes."""
    notification = Notification(
        verb="event",
        category="  Orders ",
        priority=" HIGH ",
    )

    assert notification.category == "orders"
    assert notification.priority == "high"


def test_direct_model_assignment_rejects_invalid_taxonomy() -> None:
    """ORM construction cannot bypass category or priority validation."""
    with pytest.raises(ValueError, match="category"):
        Notification(verb="event", category="invalid category")

    with pytest.raises(ValueError, match="priority"):
        Notification(verb="event", priority="immediate")
