"""Pure tests for timezone-aware recurring schedule calculations."""

from datetime import datetime, time, timezone
from typing import Any

import pytest

from fastapi_notification.models.notification_quiet_hours import validate_timezone
from fastapi_notification.repository.manager.scheduling import _next_run


def test_daily_schedule_uses_local_wall_clock() -> None:
    now = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)
    result = _next_run(
        after=now,
        frequency="daily",
        local_time=time(9),
        timezone_name="America/New_York",
        weekday=None,
    )
    assert result == datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)


def test_daily_schedule_moves_to_tomorrow_when_time_has_passed() -> None:
    now = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)
    result = _next_run(
        after=now,
        frequency="daily",
        local_time=time(9),
        timezone_name="America/New_York",
        weekday=None,
    )
    assert result == datetime(2026, 11, 3, 14, 0, tzinfo=timezone.utc)


def test_weekly_schedule_uses_monday_zero_based_weekday() -> None:
    now = datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc)  # Monday
    result = _next_run(
        after=now,
        frequency="weekly",
        local_time=time(9),
        timezone_name="America/New_York",
        weekday=2,
    )
    assert result == datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)


def test_weekly_schedule_requires_valid_weekday() -> None:
    with pytest.raises(ValueError):
        _next_run(
            after=datetime.now(timezone.utc),
            frequency="weekly",
            local_time=time(9),
            timezone_name="UTC",
            weekday=None,
        )


def test_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError):
        _next_run(
            after=datetime(2026, 11, 2),
            frequency="daily",
            local_time=time(9),
            timezone_name="UTC",
            weekday=None,
        )


def test_invalid_timezone_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_timezone("Mars/Olympus_Mons")


def test_daily_schedule_keeps_wall_clock_after_dst_transition() -> None:
    # New York moves from UTC-5 to UTC-4 on 2026-03-08. The local 09:00
    # schedule should remain 09:00, with its UTC instant moving by one hour.
    before = _next_run(
        after=datetime(2026, 3, 7, 14, 30, tzinfo=timezone.utc),
        frequency="daily",
        local_time=time(9),
        timezone_name="America/New_York",
        weekday=None,
    )
    after = _next_run(
        after=datetime(2026, 3, 8, 13, 30, tzinfo=timezone.utc),
        frequency="daily",
        local_time=time(9),
        timezone_name="America/New_York",
        weekday=None,
    )
    assert before == datetime(2026, 3, 8, 13, 0, tzinfo=timezone.utc)
    assert after == datetime(2026, 3, 9, 13, 0, tzinfo=timezone.utc)


def test_weekly_schedule_rejects_invalid_weekday() -> None:
    with pytest.raises(ValueError):
        _next_run(
            after=datetime.now(timezone.utc),
            frequency="weekly",
            local_time=time(9),
            timezone_name="UTC",
            weekday=7,
        )


def test_quiet_hours_and_digest_schemas_validate_timezone_and_frequency() -> None:
    from fastapi_notification.api.schemas.notification_scheduling import (
        DigestScheduleUpdate,
        QuietHoursUpdate,
    )

    quiet = QuietHoursUpdate(
        channel="EMAIL",
        start_time=time(22),
        end_time=time(7),
        timezone="America/Los_Angeles",
        allow_urgent=False,
    )
    assert quiet.channel == "email"
    digest = DigestScheduleUpdate(
        channel="email",
        frequency="weekly",
        local_time=time(8),
        timezone="UTC",
        weekday=0,
    )
    assert digest.weekday == 0
    with pytest.raises(ValueError):
        DigestScheduleUpdate(
            channel="email",
            frequency="weekly",
            local_time=time(8),
            timezone="UTC",
        )
    with pytest.raises(ValueError):
        QuietHoursUpdate(
            channel="email",
            start_time=time(8),
            end_time=time(8),
            timezone="UTC",
        )


def test_schedule_schema_rejects_unknown_timezone() -> None:
    from fastapi_notification.api.schemas.notification_scheduling import (
        DigestScheduleUpdate,
    )

    with pytest.raises(ValueError):
        DigestScheduleUpdate(
            channel="email",
            frequency="daily",
            local_time=time(8),
            timezone="Mars/Olympus_Mons",
        )


@pytest.mark.parametrize(
    "zone,day,hour,minute,expected",
    [
        ("UTC", (2026, 3, 8), 9, 0, (9, 0)),
        ("Asia/Tehran", (2026, 3, 8), 9, 0, (5, 30)),
        ("America/New_York", (2026, 3, 8), 2, 30, (7, 30)),
        ("America/New_York", (2026, 11, 1), 1, 30, (5, 30)),
        ("Europe/Berlin", (2026, 3, 29), 2, 30, (1, 30)),
        ("Europe/Berlin", (2026, 10, 25), 2, 30, (0, 30)),
    ],
)
def test_transition_policy_runs_once_per_local_date(
    zone: str,
    day: tuple[int, int, int],
    hour: int,
    minute: int,
    expected: tuple[int, int],
) -> None:
    result = _next_run(
        after=datetime(*day, tzinfo=timezone.utc),
        frequency="daily",
        local_time=time(hour, minute),
        timezone_name=zone,
        weekday=None,
    )
    assert result == datetime(*day, *expected, tzinfo=timezone.utc)
    following = _next_run(
        after=result,
        frequency="daily",
        local_time=time(hour, minute),
        timezone_name=zone,
        weekday=None,
    )
    from zoneinfo import ZoneInfo

    assert (
        following.astimezone(ZoneInfo(zone)).date()
        > result.astimezone(ZoneInfo(zone)).date()
    )
