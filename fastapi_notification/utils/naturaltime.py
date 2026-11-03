from datetime import datetime, timezone
from typing import Optional

# Thresholds, in seconds, paired with the unit label used to describe them.
_UNITS = (
    (60 * 60 * 24 * 365, "year"),
    (60 * 60 * 24 * 30, "month"),
    (60 * 60 * 24 * 7, "week"),
    (60 * 60 * 24, "day"),
    (60 * 60, "hour"),
    (60, "minute"),
)


def _as_aware(value: datetime) -> datetime:
    """Return the datetime as timezone aware, assuming UTC when naive.

    Args:
        value (datetime): The datetime to normalize.

    Returns:
        datetime: An equivalent timezone aware datetime.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def naturaltime(value: Optional[datetime], now: Optional[datetime] = None) -> str:
    """Describe a datetime relative to the present in plain English.

    This is the package's replacement for Django's ``humanize.naturaltime``
    template filter, producing strings such as ``"3 hours ago"`` or
    ``"2 days from now"``.

    Args:
        value (Optional[datetime]): The datetime to describe.
        now (Optional[datetime]): The reference point. Defaults to the current
            time in UTC.

    Returns:
        str: A human readable description, or an empty string when ``value`` is
        ``None``.
    """
    if value is None:
        return ""

    value = _as_aware(value)
    now = _as_aware(now) if now else datetime.now(timezone.utc)

    delta = (now - value).total_seconds()
    future = delta < 0
    delta = abs(delta)
    suffix = "from now" if future else "ago"

    if delta < 1:
        return "now"

    if delta < 60:
        count = int(delta)
        unit = "second" if count == 1 else "seconds"
        return f"{count} {unit} {suffix}"

    for seconds, name in _UNITS:
        if delta >= seconds:
            count = int(delta // seconds)
            unit = name if count == 1 else f"{name}s"
            return f"{count} {unit} {suffix}"

    # Unreachable: any delta of 60 seconds or more matches a unit above.
    return "now"  # pragma: no cover
