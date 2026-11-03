import pytest

from fastapi_notification.api.paginations.limit_offset_pagination import (
    DefaultLimitOffSetPagination,
)
from fastapi_notification.api.throttlings.role_base_throttle import (
    RoleBasedUserRateThrottle,
)
from fastapi_notification.identity import IdentityAdapter
from fastapi_notification.settings.conf import (
    NotificationConfig,
    config,
    configure,
    reset_config,
)

pytestmark = [pytest.mark.settings, pytest.mark.settings_conf]


def test_defaults_are_applied() -> None:
    """With nothing configured, the packaged defaults are in force."""
    assert config.include_soft_delete is True
    assert config.include_hard_delete is False
    assert config.api_allow_list is True
    assert config.api_allow_retrieve is True
    assert config.api_ordering_fields == [
        "id",
        "timestamp",
        "public",
        "category",
        "priority",
    ]
    assert config.api_search_fields == ["verb", "description"]
    assert config.user_serializer_fields == ["id"]


def test_default_classes_are_imported() -> None:
    """Class settings resolve to the classes they name."""
    assert config.api_throttle_class is RoleBasedUserRateThrottle
    assert config.api_pagination_class is DefaultLimitOffSetPagination
    assert config.notification_serializer_class is None
    assert config.identity_adapter is IdentityAdapter


def test_configure_overrides_a_setting() -> None:
    """A value registered through configure takes effect immediately."""
    configure(API_INCLUDE_HARD_DELETE=True)

    assert config.include_hard_delete is True


def test_configure_accepts_a_prefixed_name() -> None:
    """Setting names may be given with or without the package prefix."""
    configure(FASTAPI_NOTIFICATION_API_ALLOW_LIST=False)

    assert config.api_allow_list is False


def test_reset_config_restores_the_defaults() -> None:
    """Resetting discards every override."""
    configure(API_INCLUDE_HARD_DELETE=True)
    reset_config()

    assert config.include_hard_delete is False


def test_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings absent from the overrides fall through to the environment."""
    monkeypatch.setenv("FASTAPI_NOTIFICATION_API_INCLUDE_HARD_DELETE", "true")

    assert NotificationConfig().include_hard_delete is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", True), ("yes", True), ("on", True), ("0", False), ("no", False)],
)
def test_boolean_environment_values_are_parsed(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    """Common spellings of true and false are understood."""
    monkeypatch.setenv("FASTAPI_NOTIFICATION_API_ALLOW_LIST", raw)

    assert NotificationConfig().api_allow_list is expected


def test_unparseable_boolean_is_left_as_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A value that is not a boolean is passed through for validation to catch."""
    monkeypatch.setenv("FASTAPI_NOTIFICATION_API_ALLOW_LIST", "perhaps")

    assert NotificationConfig().api_allow_list == "perhaps"


def test_list_environment_values_are_parsed_as_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """List settings are read as JSON."""
    monkeypatch.setenv(
        "FASTAPI_NOTIFICATION_API_ORDERING_FIELDS", '["id", "timestamp"]'
    )

    assert NotificationConfig().api_ordering_fields == ["id", "timestamp"]


def test_unparseable_list_is_left_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed list is passed through for validation to catch."""
    monkeypatch.setenv("FASTAPI_NOTIFICATION_API_ORDERING_FIELDS", "id,timestamp")

    assert NotificationConfig().api_ordering_fields == "id,timestamp"


def test_string_settings_are_read_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    """String settings need no coercion."""
    monkeypatch.setenv("FASTAPI_NOTIFICATION_STAFF_USER_THROTTLE_RATE", "5/second")

    assert NotificationConfig().staff_user_throttle_rate == "5/second"


def test_a_class_may_be_supplied_directly() -> None:
    """Class settings accept a class as readily as an import path."""
    configure(API_PAGINATION_CLASS=DefaultLimitOffSetPagination)

    assert config.api_pagination_class is DefaultLimitOffSetPagination


def test_an_unimportable_class_resolves_to_none() -> None:
    """A path that cannot be imported leaves the setting unset."""
    configure(API_THROTTLE_CLASS="nowhere.Nothing")

    assert config.api_throttle_class is None


def test_a_class_setting_may_be_switched_off() -> None:
    """Setting a class to None disables the feature it drives."""
    configure(API_THROTTLE_CLASS=None, API_PAGINATION_CLASS=None)

    assert config.api_throttle_class is None
    assert config.api_pagination_class is None


def test_a_list_of_class_paths_is_imported() -> None:
    """A setting may name several classes at once."""
    configure(
        API_PARSER_CLASSES=[
            "fastapi_notification.api.schemas.notification.NotificationSerializer"
        ]
    )
    resolved = config.get_optional_classes(
        "FASTAPI_NOTIFICATION_API_PARSER_CLASSES", None
    )

    assert isinstance(resolved, list)
    assert len(resolved) == 1


def test_an_unimportable_class_in_a_list_yields_nothing() -> None:
    """One bad path in a list invalidates the whole setting."""
    resolved = config.get_optional_classes("MISSING", ["nowhere.Nothing"])

    assert resolved == []
