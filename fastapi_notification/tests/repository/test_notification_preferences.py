"""Tests for per-user notification delivery preferences."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import User
from fastapi_notification.models.notification_preference import NotificationPreference
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.repository.manager.preferences import (
    NotificationPreferenceDataAccessLayer,
)


async def test_preferences_default_to_enabled(
    session: AsyncSession, user: User
) -> None:
    dal = NotificationPreferenceDataAccessLayer(session)
    assert await dal.is_enabled(user, category="orders", channel="email") is True


async def test_preference_rules_follow_specificity_precedence(
    session: AsyncSession, user: User
) -> None:
    dal = NotificationPreferenceDataAccessLayer(session)
    await dal.set_preference(user, category="*", channel="*", enabled=False)
    await dal.set_preference(user, category="orders", channel="*", enabled=True)
    await dal.set_preference(user, category="orders", channel="email", enabled=False)

    assert await dal.is_enabled(user, category="orders", channel="email") is False
    assert await dal.is_enabled(user, category="orders", channel="push") is True
    assert await dal.is_enabled(user, category="social", channel="email") is False


async def test_exact_channel_rule_overrides_category_wildcard(
    session: AsyncSession, user: User
) -> None:
    dal = NotificationPreferenceDataAccessLayer(session)
    await dal.set_preference(user, category="orders", channel="*", enabled=False)
    await dal.set_preference(user, category="orders", channel="push", enabled=True)

    assert await dal.is_enabled(user, category="orders", channel="push") is True
    assert await dal.is_enabled(user, category="orders", channel="email") is False


async def test_preference_updates_existing_rule(
    session: AsyncSession, user: User
) -> None:
    dal = NotificationPreferenceDataAccessLayer(session)
    first = await dal.set_preference(
        user, category="security", channel="email", enabled=False
    )
    second = await dal.set_preference(
        user, category="security", channel="email", enabled=True
    )

    assert first.id == second.id
    assert second.enabled is True
    assert len(await dal.list_for_user(user)) == 1


async def test_preferences_are_isolated_by_user(
    session: AsyncSession, user: User, other_user: User
) -> None:
    dal = NotificationPreferenceDataAccessLayer(session)
    await dal.set_preference(user, category="*", channel="email", enabled=False)

    assert await dal.is_enabled(user, category="orders", channel="email") is False
    assert await dal.is_enabled(other_user, category="orders", channel="email") is True
    assert len(await dal.list_for_user(other_user)) == 0


async def test_reset_restores_inherited_default(
    session: AsyncSession, user: User
) -> None:
    dal = NotificationPreferenceDataAccessLayer(session)
    await dal.set_preference(user, category="orders", channel="email", enabled=False)

    assert await dal.reset_preference(user, category="orders", channel="email") is True
    assert await dal.reset_preference(user, category="orders", channel="email") is False
    assert await dal.is_enabled(user, category="orders", channel="email") is True


async def test_invalid_preference_keys_are_rejected(
    session: AsyncSession, user: User
) -> None:
    dal = NotificationPreferenceDataAccessLayer(session)
    with pytest.raises(ValueError):
        await dal.set_preference(
            user, category="../orders", channel="email", enabled=False
        )
    with pytest.raises(ValueError):
        await dal.set_preference(
            user, category="orders", channel="bad channel", enabled=False
        )


async def test_preferences_do_not_change_existing_inbox_notifications(
    session: AsyncSession, user: User, dal: NotificationDataAccessLayer
) -> None:
    notification = await dal.create_notification(
        verb="order placed",
        actor=user,
        recipients=user,
        category="orders",
        is_sent=True,
    )
    preferences = NotificationPreferenceDataAccessLayer(session)
    await preferences.set_preference(
        user, category="orders", channel="in_app", enabled=False
    )

    visible = await dal.sent(recipients=user)
    assert [item["id"] for item in visible] == [notification.id]


async def test_preference_model_is_registered() -> None:
    assert NotificationPreference.__tablename__ == "notification_preference"
