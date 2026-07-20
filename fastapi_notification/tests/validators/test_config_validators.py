import pytest

from fastapi_notification.validators.config_validators import (
    Error,
    validate_boolean_setting,
    validate_list_fields,
    validate_optional_class_setting,
    validate_optional_classes_setting,
    validate_throttle_rate,
)

pytestmark = [pytest.mark.validators, pytest.mark.config_validators]

CLASS_PATH = "fastapi_notification.api.schemas.notification.NotificationSerializer"


def test_error_renders_with_its_hint() -> None:
    """An error reads as an identifier, a message and a hint."""
    error = Error(msg="something is wrong", id="E001", hint="try this")

    assert str(error) == "(E001) something is wrong HINT: try this"


def test_error_renders_without_a_hint() -> None:
    """An error with no hint omits it."""
    assert str(Error(msg="wrong", id="E001")) == "(E001) wrong"


def test_boolean_accepts_a_boolean() -> None:
    """A boolean setting holding a boolean is valid."""
    assert validate_boolean_setting(True, "SETTING") == []


def test_boolean_rejects_anything_else() -> None:
    """A boolean setting holding anything else is reported."""
    errors = validate_boolean_setting("yes", "SETTING")

    assert len(errors) == 1
    assert "not a boolean" in errors[0].msg


def test_list_accepts_a_populated_list() -> None:
    """A list setting holding field names is valid."""
    assert validate_list_fields(["id"], "SETTING") == []


def test_list_allows_none_when_permitted() -> None:
    """An optional list setting may be unset."""
    assert validate_list_fields(None, "SETTING", allow_none=True) == []


def test_list_rejects_none_when_not_permitted() -> None:
    """A required list setting may not be unset."""
    errors = validate_list_fields(None, "SETTING")

    assert "not a list" in errors[0].msg


def test_list_rejects_a_non_list() -> None:
    """A list setting holding something else is reported."""
    errors = validate_list_fields("id", "SETTING")

    assert "not a list" in errors[0].msg


def test_list_rejects_an_empty_list() -> None:
    """A list setting must name at least one field."""
    errors = validate_list_fields([], "SETTING")

    assert "empty list" in errors[0].msg


def test_list_rejects_non_string_entries() -> None:
    """Every entry in a list setting must be a name."""
    errors = validate_list_fields([1], "SETTING")

    assert "is not a string" in errors[0].msg


def test_list_rejects_unknown_fields() -> None:
    """Entries are checked against the fields that actually exist."""
    errors = validate_list_fields(["bogus"], "SETTING", available_fields=["id"])

    assert "is invalid" in errors[0].msg
    assert "Valid fields" in errors[0].hint


def test_throttle_rate_accepts_a_well_formed_rate() -> None:
    """A rate of requests over a time unit is valid."""
    assert validate_throttle_rate("10/minute", "SETTING") == []


def test_throttle_rate_rejects_a_non_string() -> None:
    """A rate must be a string."""
    errors = validate_throttle_rate(10, "SETTING")

    assert errors[0].id == "fastapi_notification.E005"


def test_throttle_rate_rejects_a_missing_separator() -> None:
    """A rate must name a time unit."""
    errors = validate_throttle_rate("10", "SETTING")

    assert errors[0].id == "fastapi_notification.E005"


def test_throttle_rate_rejects_too_many_parts() -> None:
    """A rate must have exactly one separator."""
    errors = validate_throttle_rate("10/minute/hour", "SETTING")

    assert errors[0].id == "fastapi_notification.E006"


def test_throttle_rate_rejects_a_non_numeric_count() -> None:
    """The request count must be a number."""
    errors = validate_throttle_rate("many/minute", "SETTING")

    assert errors[0].id == "fastapi_notification.E007"


def test_throttle_rate_rejects_an_unknown_time_unit() -> None:
    """The time unit must be one the throttle understands."""
    errors = validate_throttle_rate("10/fortnight", "SETTING")

    assert errors[0].id == "fastapi_notification.E008"
    assert "Valid time units" in errors[0].hint


def test_optional_class_allows_none() -> None:
    """An optional class setting may be unset."""
    assert validate_optional_class_setting(None, "SETTING") == []


def test_optional_class_accepts_a_class() -> None:
    """A class may be supplied directly rather than as a path."""
    assert validate_optional_class_setting(Error, "SETTING") == []


def test_optional_class_accepts_an_importable_path() -> None:
    """A path that imports cleanly is valid."""
    assert validate_optional_class_setting(CLASS_PATH, "SETTING") == []


def test_optional_class_rejects_a_non_string() -> None:
    """A class setting must be a path or a class."""
    errors = validate_optional_class_setting(42, "SETTING")

    assert "must be a valid string" in errors[0].msg


def test_optional_class_rejects_an_unimportable_path() -> None:
    """A path that cannot be imported is reported."""
    errors = validate_optional_class_setting("nowhere.Nothing", "SETTING")

    assert "Cannot import" in errors[0].msg


def test_optional_classes_allows_none() -> None:
    """An optional list-of-classes setting may be unset."""
    assert validate_optional_classes_setting(None, "SETTING") == []


def test_optional_classes_accepts_importable_paths() -> None:
    """A list of paths that import cleanly is valid."""
    assert validate_optional_classes_setting([CLASS_PATH], "SETTING") == []


def test_optional_classes_rejects_a_non_list() -> None:
    """The setting must be a list."""
    errors = validate_optional_classes_setting(CLASS_PATH, "SETTING")

    assert "Invalid type for setting" in errors[0].msg


def test_optional_classes_rejects_non_string_entries() -> None:
    """Every entry must be a path."""
    errors = validate_optional_classes_setting([42], "SETTING")

    assert "Invalid type for class path" in errors[0].msg


def test_optional_classes_rejects_an_unimportable_entry() -> None:
    """An entry that cannot be imported is reported."""
    errors = validate_optional_classes_setting(["nowhere.Nothing"], "SETTING")

    assert "Cannot import" in errors[0].msg
