import pytest

from fastapi_notification.models.notification import Notification
from fastapi_notification.utils.get_model_fields import get_serializable_model_fields

pytestmark = [pytest.mark.utils]


def test_reports_the_mapped_columns() -> None:
    """Every mapped column is serializable."""
    fields = get_serializable_model_fields(Notification)

    assert "id" in fields
    assert "verb" in fields
    assert "timestamp" in fields


def test_reports_the_relationships() -> None:
    """Relationships can be named in the serializer field settings too."""
    fields = get_serializable_model_fields(Notification)

    assert "recipient" in fields
    assert "group" in fields
    assert "seen_by" in fields


def test_excludes_unmapped_attributes() -> None:
    """Transient attributes are not serializable."""
    fields = get_serializable_model_fields(Notification)

    assert "actor" not in fields
    assert "title_generator" not in fields
