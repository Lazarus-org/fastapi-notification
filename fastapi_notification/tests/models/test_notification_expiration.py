"""Unit tests for timezone-aware notification expiration semantics."""

from datetime import datetime, timedelta, timezone

import pytest

from fastapi_notification.models.notification import Notification

pytestmark = [pytest.mark.models, pytest.mark.models_notification]


def build_notification(expires_at=None) -> Notification:
    """Build an unpersisted notification for expiration unit tests."""
    return Notification(
        verb="test",
        actor_content_type_id=1,
        actor_object_id="1",
        expires_at=expires_at,
    )


def test_expiration_is_optional_by_default() -> None:
    """Notifications without an expiration never expire automatically."""
    notification = build_notification()

    assert notification.expires_at is None
    assert notification.is_expired() is False


def test_expiration_is_normalized_to_utc() -> None:
    """An aware timestamp with another offset is stored as UTC."""
    offset = timezone(timedelta(hours=3, minutes=30))
    expires_at = datetime(2026, 11, 2, 12, 0, tzinfo=offset)

    notification = build_notification(expires_at)

    assert notification.expires_at == datetime(2026, 11, 2, 8, 30, tzinfo=timezone.utc)
    assert notification.expires_at.utcoffset() == timedelta(0)


def test_naive_expiration_is_rejected() -> None:
    """Callers must make the timezone of an expiration instant explicit."""
    with pytest.raises(ValueError, match="timezone-aware"):
        build_notification(datetime(2026, 11, 2, 12, 0))


def test_non_datetime_expiration_is_rejected() -> None:
    """Invalid expiration values fail before database persistence."""
    with pytest.raises(TypeError, match="datetime"):
        build_notification("2026-11-02T12:00:00Z")


def test_expiration_boundary_is_inclusive() -> None:
    """A notification is expired at, not after, its expiry instant."""
    instant = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    notification = build_notification(instant)

    assert notification.is_expired(instant - timedelta(microseconds=1)) is False
    assert notification.is_expired(instant) is True
    assert notification.is_expired(instant + timedelta(microseconds=1)) is True


def test_naive_comparison_instant_is_rejected() -> None:
    """Expiration checks never guess the timezone of a caller-supplied instant."""
    notification = build_notification(
        datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        notification.is_expired(datetime(2026, 11, 2, 12, 0))


def test_naive_sqlite_loaded_expiration_is_interpreted_as_utc() -> None:
    """SQLite's timezone-stripped loaded values are treated as stored UTC."""
    notification = build_notification()
    notification.__dict__["expires_at"] = datetime(2026, 11, 2, 12, 0)

    assert notification.is_expired(
        datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    ) is True
