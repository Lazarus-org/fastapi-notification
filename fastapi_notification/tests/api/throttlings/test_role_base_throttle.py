import time
from typing import Any

import pytest

from fastapi_notification.api.throttlings.role_base_throttle import (
    RoleBasedUserRateThrottle,
    ThrottleHistory,
    history,
)
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.api, pytest.mark.api_throttlings]


class Viewer:
    """A stand-in user, so throttling can be tested without the database."""

    def __init__(self, identifier: int, is_staff: bool = False) -> None:
        self.id = identifier
        self.is_staff = is_staff


@pytest.fixture
def throttle() -> RoleBasedUserRateThrottle:
    """Provide a throttle.

    Returns:
        RoleBasedUserRateThrottle: The throttle.
    """
    return RoleBasedUserRateThrottle()


def test_regular_users_get_the_authenticated_rate(throttle: Any) -> None:
    """A regular user is held to the authenticated rate."""
    assert throttle.get_rate(Viewer(1)) == "30/minute"


def test_staff_users_get_the_staff_rate(throttle: Any) -> None:
    """A staff user is held to the higher staff rate."""
    assert throttle.get_rate(Viewer(2, is_staff=True)) == "100/minute"


def test_configured_rates_are_honoured(throttle: Any) -> None:
    """The rates come from settings, not from the code."""
    configure(AUTHENTICATED_USER_THROTTLE_RATE="5/second")

    assert throttle.get_rate(Viewer(1)) == "5/second"


@pytest.mark.parametrize(
    ("rate", "expected"),
    [
        ("10/second", (10, 1)),
        ("10/minute", (10, 60)),
        ("10/hour", (10, 3600)),
        ("10/day", (10, 86400)),
        ("10/m", (10, 60)),
    ],
)
def test_rates_are_parsed(throttle: Any, rate: str, expected: tuple) -> None:
    """Every recognised time unit is understood."""
    assert throttle.parse_rate(rate) == expected


@pytest.mark.parametrize("rate", ["10/fortnight", "lots/minute", "nonsense"])
def test_malformed_rates_are_rejected(throttle: Any, rate: str) -> None:
    """A rate that cannot be parsed is reported clearly."""
    with pytest.raises(ValueError, match="not a valid throttle rate"):
        throttle.parse_rate(rate)


def test_requests_within_the_limit_are_allowed(throttle: Any) -> None:
    """Staying under the limit never blocks."""
    configure(AUTHENTICATED_USER_THROTTLE_RATE="3/minute")
    user = Viewer(1)

    assert [throttle.allow_request(user) for _ in range(3)] == [True, True, True]


def test_requests_beyond_the_limit_are_blocked(throttle: Any) -> None:
    """The request after the limit is refused."""
    configure(AUTHENTICATED_USER_THROTTLE_RATE="2/minute")
    user = Viewer(1)

    throttle.allow_request(user)
    throttle.allow_request(user)

    assert throttle.allow_request(user) is False


def test_limits_are_tracked_per_user(throttle: Any) -> None:
    """One user exhausting their limit does not affect another."""
    configure(AUTHENTICATED_USER_THROTTLE_RATE="1/minute")

    assert throttle.allow_request(Viewer(1)) is True
    assert throttle.allow_request(Viewer(1)) is False
    assert throttle.allow_request(Viewer(2)) is True


def test_staff_get_more_headroom(throttle: Any) -> None:
    """A staff user is allowed past the regular limit."""
    configure(
        AUTHENTICATED_USER_THROTTLE_RATE="1/minute",
        STAFF_USER_THROTTLE_RATE="5/minute",
    )
    staff = Viewer(3, is_staff=True)

    assert all(throttle.allow_request(staff) for _ in range(5))


def test_the_window_slides(throttle: Any) -> None:
    """Requests older than the window stop counting against the limit."""
    configure(AUTHENTICATED_USER_THROTTLE_RATE="1/second")
    user = Viewer(1)

    assert throttle.allow_request(user) is True
    assert throttle.allow_request(user) is False

    time.sleep(1.05)

    assert throttle.allow_request(user) is True


def test_wait_is_zero_before_any_request(throttle: Any) -> None:
    """A user who has not been seen has nothing to wait for."""
    assert throttle.wait(Viewer(99)) == 0.0


def test_wait_reports_the_remaining_window(throttle: Any) -> None:
    """A throttled user is told roughly how long to wait."""
    configure(AUTHENTICATED_USER_THROTTLE_RATE="1/minute")
    user = Viewer(1)
    throttle.allow_request(user)

    assert 0 < throttle.wait(user) <= 60


def test_the_cache_key_is_per_user_and_scope(throttle: Any) -> None:
    """Each user's history is recorded under its own key."""
    assert throttle.get_cache_key(Viewer(7)) == "throttle_user_7"


def test_the_cache_key_falls_back_for_anonymous_callers(throttle: Any) -> None:
    """A caller with no identifier still gets a key."""

    class Anonymous:
        pass

    assert throttle.get_cache_key(Anonymous()) == "throttle_user_anonymous"


def test_the_default_history_is_shared(throttle: Any) -> None:
    """The throttle records against the process wide history by default."""
    assert throttle.get_history() is history


def test_history_can_be_cleared() -> None:
    """Clearing the history forgets every recorded request."""
    store = ThrottleHistory()
    store.get("key").append(1.0)
    store.clear()

    assert len(store.get("key")) == 0
