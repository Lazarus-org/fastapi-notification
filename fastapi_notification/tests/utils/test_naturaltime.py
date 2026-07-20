from datetime import datetime, timedelta, timezone

import pytest

from fastapi_notification.utils.naturaltime import naturaltime

pytestmark = [pytest.mark.utils, pytest.mark.utils_naturaltime]

NOW = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_none_renders_as_empty() -> None:
    """A missing timestamp renders as nothing at all."""
    assert naturaltime(None) == ""


def test_sub_second_deltas_render_as_now() -> None:
    """Anything within the last second reads as the present."""
    assert naturaltime(NOW, now=NOW) == "now"


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=1), "1 second ago"),
        (timedelta(seconds=30), "30 seconds ago"),
        (timedelta(minutes=1), "1 minute ago"),
        (timedelta(minutes=45), "45 minutes ago"),
        (timedelta(hours=1), "1 hour ago"),
        (timedelta(hours=5), "5 hours ago"),
        (timedelta(days=1), "1 day ago"),
        (timedelta(days=3), "3 days ago"),
        (timedelta(days=7), "1 week ago"),
        (timedelta(days=21), "3 weeks ago"),
        (timedelta(days=30), "1 month ago"),
        (timedelta(days=120), "4 months ago"),
        (timedelta(days=365), "1 year ago"),
        (timedelta(days=800), "2 years ago"),
    ],
)
def test_past_deltas_read_naturally(delta: timedelta, expected: str) -> None:
    """Past timestamps are described in the largest fitting unit."""
    assert naturaltime(NOW - delta, now=NOW) == expected


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=5), "5 seconds from now"),
        (timedelta(hours=2), "2 hours from now"),
        (timedelta(days=400), "1 year from now"),
    ],
)
def test_future_deltas_read_naturally(delta: timedelta, expected: str) -> None:
    """Future timestamps are described as being ahead."""
    assert naturaltime(NOW + delta, now=NOW) == expected


def test_naive_timestamps_are_treated_as_utc() -> None:
    """A timestamp with no timezone is assumed to be UTC."""
    naive = datetime(2026, 7, 20, 11, 0, 0)

    assert naturaltime(naive, now=NOW) == "1 hour ago"


def test_naive_reference_is_treated_as_utc() -> None:
    """A naive reference point is also assumed to be UTC."""
    naive_now = datetime(2026, 7, 20, 12, 0, 0)

    assert naturaltime(NOW - timedelta(hours=3), now=naive_now) == "3 hours ago"


def test_defaults_to_the_current_time() -> None:
    """With no reference point, the present is used."""
    assert naturaltime(datetime.now(timezone.utc) - timedelta(minutes=2)) == (
        "2 minutes ago"
    )
