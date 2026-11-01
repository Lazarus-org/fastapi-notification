import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Tuple

# How many seconds each recognised time unit spans.
DURATIONS: Dict[str, int] = {
    "s": 1,
    "sec": 1,
    "second": 1,
    "m": 60,
    "min": 60,
    "minute": 60,
    "h": 3600,
    "hour": 3600,
    "d": 86400,
    "day": 86400,
}


class ThrottleHistory:
    """In-memory record of when each identity last made a request.

    Keeps a sliding window per identity, which is enough for a single process.
    Deployments running several workers should point the throttle at a shared
    store by subclassing :class:`RoleBasedUserRateThrottle` and overriding
    :meth:`RoleBasedUserRateThrottle.get_history`.

    """

    def __init__(self) -> None:
        self._entries: Dict[str, Deque[float]] = defaultdict(deque)

    def get(self, key: str) -> Deque[float]:
        """Return the recorded request times for an identity.

        Args:
            key (str): The identity to look up.

        Returns:
            Deque[float]: The timestamps of that identity's recent requests.

        """
        return self._entries[key]

    def clear(self) -> None:
        """Forget every recorded request."""
        self._entries.clear()


#: The process wide history the default throttle records against.
history = ThrottleHistory()


class RoleBasedUserRateThrottle:
    """Rate limit requests according to the user's role.

    Regular authenticated users are limited to the rate in
    ``AUTHENTICATED_USER_THROTTLE_RATE`` (30 a minute by default), while staff
    users get the higher ``STAFF_USER_THROTTLE_RATE`` (100 a minute). Both come
    from settings, so the limits can be tuned without touching code.

    """

    scope: str = "user"

    def get_rate(self, user: Any) -> str:
        """Return the configured throttle rate for a user.

        Args:
            user (Any): The user making the request.

        Returns:
            str: The rate, as ``"number/time_unit"``.

        """
        from fastapi_notification.settings.conf import config

        self.base_rate: str = config.authenticated_user_throttle_rate
        self.staff_rate: str = config.staff_user_throttle_rate

        from fastapi_notification.identity import is_staff_identity

        if is_staff_identity(user):
            return self.staff_rate

        return self.base_rate

    def parse_rate(self, rate: str) -> Tuple[int, int]:
        """Split a rate string into a request count and a window in seconds.

        Args:
            rate (str): The rate, as ``"number/time_unit"``.

        Returns:
            Tuple[int, int]: The number of requests allowed and the window
            length in seconds.

        Raises:
            ValueError: If the rate is not in the expected format.

        """
        try:
            number, _, unit = rate.partition("/")
            num_requests = int(number)
            duration = DURATIONS[unit.lower()]
        except (KeyError, ValueError) as error:
            raise ValueError(
                f"'{rate}' is not a valid throttle rate; expected 'number/time_unit'"
                " (e.g. '10/minute')."
            ) from error

        return num_requests, duration

    def get_cache_key(self, user: Any) -> str:
        """Return the key a user's request history is recorded under.

        Args:
            user (Any): The user making the request.

        Returns:
            str: The history key.

        """
        from fastapi_notification.identity import get_identity_adapter

        adapter = get_identity_adapter()
        try:
            identity = adapter.get_user_id(user)
        except ValueError:
            if user is not None and hasattr(user, adapter.user_id_attribute):
                raise
            identity = "anonymous"

        return f"throttle_{self.scope}_{identity}"

    def get_history(self) -> ThrottleHistory:
        """Return the store request times are recorded in.

        Override this to record against a shared store, such as Redis, when
        running more than one worker process.

        Returns:
            ThrottleHistory: The history store.

        """
        return history

    def allow_request(self, user: Any) -> bool:
        """Decide whether a user's request is within their rate limit.

        Requests outside the current window are discarded before the check, so
        the limit slides rather than resetting on fixed boundaries.

        Args:
            user (Any): The user making the request.

        Returns:
            bool: True if the request is allowed, False if it is throttled.

        """
        num_requests, duration = self.parse_rate(self.get_rate(user))

        now = time.monotonic()
        timestamps = self.get_history().get(self.get_cache_key(user))

        while timestamps and timestamps[0] <= now - duration:
            timestamps.popleft()

        if len(timestamps) >= num_requests:
            return False

        timestamps.append(now)
        return True

    def wait(self, user: Any) -> float:
        """Return how long until the user may make another request.

        Args:
            user (Any): The throttled user.

        Returns:
            float: The number of seconds to wait; zero when not throttled.

        """
        _, duration = self.parse_rate(self.get_rate(user))
        timestamps = self.get_history().get(self.get_cache_key(user))

        if not timestamps:
            return 0.0

        return max(duration - (time.monotonic() - timestamps[0]), 0.0)
