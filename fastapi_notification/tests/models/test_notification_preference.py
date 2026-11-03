"""Unit tests for notification preference keys and schema metadata."""

import pytest

from fastapi_notification.api.schemas.notification_preference import (
    NotificationPreferenceUpdate,
)
from fastapi_notification.models.base import Base
from fastapi_notification.models.notification_preference import (
    NotificationPreference,
    normalize_preference_key,
)


def test_preference_table_is_registered_with_unique_scope() -> None:
    table = Base.metadata.tables["notification_preference"]
    assert table is NotificationPreference.__table__
    assert any(
        constraint.name == "notification_preference_unique"
        for constraint in table.constraints
    )


def test_preference_key_is_normalized() -> None:
    assert normalize_preference_key("  Orders.Email ") == "orders.email"
    assert normalize_preference_key("*", allow_wildcard=True) == "*"


@pytest.mark.parametrize("value", ["", "bad channel", "../orders", "_orders", "a" * 65])
def test_invalid_preference_key_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_preference_key(value, allow_wildcard=True)


def test_preference_update_schema_normalizes_keys() -> None:
    payload = NotificationPreferenceUpdate(
        category="Orders", channel="Email", enabled=False
    )
    assert payload.category == "orders"
    assert payload.channel == "email"


def test_preference_update_schema_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        NotificationPreferenceUpdate.model_validate(
            {
                "category": "orders",
                "channel": "email",
                "enabled": False,
                "user_id": "other",
            }
        )
