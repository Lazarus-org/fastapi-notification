"""Data access layer for per-user notification preferences."""

from typing import Any, List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.models.notification_preference import (
    NotificationPreference,
    normalize_preference_key,
)
from fastapi_notification.models.state import insert_if_absent


class NotificationPreferenceDataAccessLayer:
    """Read and update delivery preferences for one authenticated identity.

    Preferences are policy data for delivery adapters. They do not remove, hide, or
    mutate notifications already persisted in a user's inbox.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(self, user: Any) -> List[NotificationPreference]:
        """Return all preference rules belonging to ``user``."""
        user_id = get_identity_adapter().get_user_id(user)
        result = await self.session.execute(
            select(NotificationPreference)
            .where(NotificationPreference.user_id == user_id)
            .order_by(
                NotificationPreference.category,
                NotificationPreference.channel,
            )
        )
        return list(result.scalars().all())

    async def set_preference(
        self,
        user: Any,
        *,
        category: str = "*",
        channel: str = "*",
        enabled: bool,
    ) -> NotificationPreference:
        """Create or update one preference rule atomically."""
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean.")
        category = normalize_preference_key(category, allow_wildcard=True)
        channel = normalize_preference_key(channel, allow_wildcard=True)
        user_id = get_identity_adapter().get_user_id(user)
        instance, _ = await insert_if_absent(
            self.session,
            NotificationPreference,
            {
                "user_id": user_id,
                "category": category,
                "channel": channel,
                "enabled": enabled,
            },
            ("user_id", "category", "channel"),
        )
        # A conflicting concurrent insert is returned by insert_if_absent;
        # assigning after the atomic claim makes this call an upsert.
        instance.enabled = enabled
        await self.session.flush()
        return instance

    async def reset_preference(
        self,
        user: Any,
        *,
        category: str = "*",
        channel: str = "*",
    ) -> bool:
        """Remove a preference override, restoring inherited/default behavior."""
        category = normalize_preference_key(category, allow_wildcard=True)
        channel = normalize_preference_key(channel, allow_wildcard=True)
        result = await self.session.execute(
            delete(NotificationPreference).where(
                NotificationPreference.user_id
                == get_identity_adapter().get_user_id(user),
                NotificationPreference.category == category,
                NotificationPreference.channel == channel,
            )
        )
        return bool(result.rowcount)

    async def is_enabled(
        self,
        user: Any,
        *,
        category: str,
        channel: str,
        default: bool = True,
    ) -> bool:
        """Resolve whether a channel is enabled using specificity precedence.

        Precedence: exact category+channel, exact category+wildcard channel,
        wildcard category+exact channel, then global wildcard. With no rule,
        ``default`` is returned (enabled by default).
        """
        category = normalize_preference_key(category)
        channel = normalize_preference_key(channel)
        user_id = get_identity_adapter().get_user_id(user)
        result = await self.session.execute(
            select(
                NotificationPreference.category,
                NotificationPreference.channel,
                NotificationPreference.enabled,
            ).where(
                NotificationPreference.user_id == user_id,
                NotificationPreference.category.in_([category, "*"]),
                NotificationPreference.channel.in_([channel, "*"]),
            )
        )
        rules = {(row.category, row.channel): bool(row.enabled) for row in result.all()}
        for key in (
            (category, channel),
            (category, "*"),
            ("*", channel),
            ("*", "*"),
        ):
            if key in rules:
                return rules[key]
        return default


__all__ = ["NotificationPreferenceDataAccessLayer"]
