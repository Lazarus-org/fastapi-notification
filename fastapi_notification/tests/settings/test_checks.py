import pytest

from fastapi_notification.settings.checks import (
    ImproperlyConfigured,
    check_notification_settings,
    run_checks,
)
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.settings, pytest.mark.settings_checks]


def test_default_settings_are_valid() -> None:
    """Out of the box, nothing is misconfigured."""
    assert check_notification_settings() == []


def test_run_checks_is_silent_when_valid() -> None:
    """Validating a good configuration raises nothing."""
    assert run_checks() is None


def test_a_non_boolean_flag_is_reported() -> None:
    """A flag holding something other than a boolean is caught."""
    configure(API_INCLUDE_SOFT_DELETE="yes")

    errors = check_notification_settings()

    assert any("API_INCLUDE_SOFT_DELETE" in error.msg for error in errors)


def test_an_unknown_serializer_field_is_reported() -> None:
    """Serializer fields are checked against the notification model."""
    configure(SERIALIZER_FIELDS=["id", "bogus"])

    errors = check_notification_settings()

    assert any("bogus" in error.msg for error in errors)


def test_a_known_serializer_field_is_accepted() -> None:
    """Real model fields, and the computed title, are accepted."""
    configure(SERIALIZER_FIELDS=["title", "id", "verb"])

    assert check_notification_settings() == []


def test_a_malformed_throttle_rate_is_reported() -> None:
    """Throttle rates are checked for shape."""
    configure(STAFF_USER_THROTTLE_RATE="lots/fortnight")

    errors = check_notification_settings()

    assert any(error.id.startswith("fastapi_notification.E00") for error in errors)


def test_an_unimportable_class_is_reported() -> None:
    """A class setting naming a path that cannot be imported is caught."""
    configure(API_PAGINATION_CLASS="nowhere.Nothing")

    errors = check_notification_settings()

    assert any("Cannot import" in error.msg for error in errors)


def test_an_empty_field_list_is_reported() -> None:
    """A list setting must name at least one field."""
    configure(API_ORDERING_FIELDS=[])

    errors = check_notification_settings()

    assert any("empty list" in error.msg for error in errors)


def test_run_checks_raises_and_lists_every_problem() -> None:
    """Everything wrong is reported at once, not one at a time."""
    configure(API_ALLOW_LIST="maybe", API_ALLOW_RETRIEVE="perhaps")

    with pytest.raises(ImproperlyConfigured) as raised:
        run_checks()

    assert len(raised.value.errors) == 2
    assert "API_ALLOW_LIST" in str(raised.value)
    assert "API_ALLOW_RETRIEVE" in str(raised.value)


def test_a_missing_identity_adapter_is_reported() -> None:
    """The identity adapter is required and cannot be disabled."""
    configure(IDENTITY_ADAPTER=None)

    errors = check_notification_settings()

    assert any("identity adapter is not configured" in error.msg for error in errors)


def test_an_incomplete_identity_adapter_is_reported() -> None:
    """A class without the adapter contract is rejected at startup."""
    configure(IDENTITY_ADAPTER=object)

    errors = check_notification_settings()

    assert any("identity adapter is invalid" in error.msg for error in errors)
