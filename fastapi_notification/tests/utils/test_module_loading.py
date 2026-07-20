import pytest

from fastapi_notification.models.notification import Notification
from fastapi_notification.utils.module_loading import import_string

pytestmark = [pytest.mark.utils]


def test_imports_the_named_attribute() -> None:
    """A valid dotted path resolves to the attribute it names."""
    imported = import_string("fastapi_notification.models.notification.Notification")

    assert imported is Notification


def test_rejects_a_path_without_a_module() -> None:
    """A path with no module part is rejected."""
    with pytest.raises(ImportError, match="doesn't look like a module path"):
        import_string("Notification")


def test_rejects_a_missing_module() -> None:
    """A path naming an absent module is rejected."""
    with pytest.raises(ImportError):
        import_string("fastapi_notification.nowhere.Nothing")


def test_rejects_a_missing_attribute() -> None:
    """A path naming an absent attribute is rejected."""
    with pytest.raises(ImportError, match="does not define"):
        import_string("fastapi_notification.models.notification.Nothing")
