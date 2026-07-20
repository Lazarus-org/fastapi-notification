import pytest

from fastapi_notification.models.helper.enums.status_choices import NotificationStatus

pytestmark = [pytest.mark.models]


def test_members_are_plain_strings() -> None:
    """Statuses persist and serialize as their bare string value."""
    assert NotificationStatus.INFO == "INFO"
    assert NotificationStatus.INFO.value == "INFO"


def test_label_describes_the_status() -> None:
    """Every status carries a human readable description."""
    assert NotificationStatus.ERROR.label.startswith("Error -")
    assert NotificationStatus.INFRASTRUCTURE.label.startswith("Infrastructure -")


def test_choices_pairs_values_with_labels() -> None:
    """The choices list mirrors a Django TextChoices enumeration."""
    choices = NotificationStatus.choices()

    assert ("INFO", NotificationStatus.INFO.label) in choices
    assert len(choices) == len(NotificationStatus)


def test_values_lists_every_status() -> None:
    """Every status value is reported."""
    assert set(NotificationStatus.values()) == {
        "ERROR",
        "SUCCESS",
        "WARNING",
        "INFO",
        "CRITICAL",
        "SENSITIVE",
        "INFRASTRUCTURE",
    }
