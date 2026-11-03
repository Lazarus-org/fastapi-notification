"""Scheduler-agnostic quiet-hours and digest scheduling data access."""

import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, List, Optional
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.models.helper.enums import normalize_priority
from fastapi_notification.models.notification_digest import (
    NotificationDigestBatch,
    NotificationDigestSchedule,
)
from fastapi_notification.models.notification_preference import normalize_preference_key
from fastapi_notification.models.notification_quiet_hours import (
    NotificationQuietHours,
    validate_timezone,
)
from fastapi_notification.models.state import insert_if_absent
from fastapi_notification.utils.sqlalchemy import execute_dml

_ERROR_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")


def _validate_claim_token(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("claim_token must be a UUID string.")
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError("claim_token must be a valid UUID string.") from exc


def _validate_error_code(value: object) -> str:
    if not isinstance(value, str) or not _ERROR_CODE_PATTERN.fullmatch(value):
        raise ValueError(
            "error_code must be a lowercase identifier containing 1 to 64 "
            "letters, digits, dots, underscores or hyphens, and start with a letter."
        )
    return value


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _next_run(
    *,
    after: datetime,
    frequency: str,
    local_time: time,
    timezone_name: str,
    weekday: Optional[int],
) -> datetime:
    """Calculate the next wall-clock schedule instant after an aware instant."""
    after = _require_aware(after)
    zone = ZoneInfo(validate_timezone(timezone_name))
    local_after = after.astimezone(zone)
    candidate_date = local_after.date()
    if frequency == "weekly":
        if weekday is None or not 0 <= weekday <= 6:
            raise ValueError("weekly schedules require weekday between 0 and 6.")
        days = (weekday - candidate_date.weekday()) % 7
        candidate_date += timedelta(days=days)
    elif frequency != "daily":
        raise ValueError("frequency must be 'daily' or 'weekly'.")

    candidate = datetime.combine(candidate_date, local_time).replace(tzinfo=zone)
    if candidate.astimezone(timezone.utc) <= after:
        candidate_date += timedelta(days=7 if frequency == "weekly" else 1)
        candidate = datetime.combine(candidate_date, local_time).replace(tzinfo=zone)
    return candidate.astimezone(timezone.utc)


class NotificationSchedulingDataAccessLayer:
    """Manage quiet windows, digest schedules and idempotent digest batches.

    This class does not run a worker, send messages, or commit transactions.
    Applications can call ``create_due_batches`` from cron, Celery, APScheduler, or
    their own worker and then process claimed batches using their preferred delivery
    provider.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _user_id(self, user: Any) -> str:
        return str(get_identity_adapter().get_user_id(user))

    async def list_quiet_hours(self, user: Any) -> List[NotificationQuietHours]:
        result = await self.session.execute(
            select(NotificationQuietHours)
            .where(NotificationQuietHours.user_id == self._user_id(user))
            .order_by(NotificationQuietHours.channel)
        )
        return list(result.scalars().all())

    # Keep explicit existing public options; see STATIC_ANALYSIS.md.
    async def set_quiet_hours(  # pylint: disable=too-many-arguments
        self,
        user: Any,
        *,
        start_time: time,
        end_time: time,
        timezone_name: str = "UTC",
        channel: str = "*",
        enabled: bool = True,
        allow_urgent: bool = True,
    ) -> NotificationQuietHours:
        if not isinstance(start_time, time) or not isinstance(end_time, time):
            raise TypeError("start_time and end_time must be datetime.time values.")
        if start_time.tzinfo is not None or end_time.tzinfo is not None:
            raise ValueError("Quiet-hour wall-clock times must not contain tzinfo.")
        if start_time == end_time:
            raise ValueError("start_time and end_time must be different.")
        if not isinstance(enabled, bool) or not isinstance(allow_urgent, bool):
            raise TypeError("enabled and allow_urgent must be booleans.")
        channel = normalize_preference_key(channel, allow_wildcard=True)
        timezone_name = validate_timezone(timezone_name)
        values = {
            "user_id": self._user_id(user),
            "channel": channel,
            "start_time": start_time,
            "end_time": end_time,
            "timezone": timezone_name,
            "enabled": enabled,
            "allow_urgent": allow_urgent,
        }
        row, _ = await insert_if_absent(
            self.session,
            NotificationQuietHours,
            values,
            ("user_id", "channel"),
        )
        for key, value in values.items():
            if key not in {"user_id", "channel"}:
                setattr(row, key, value)
        await self.session.flush()
        return row

    async def reset_quiet_hours(self, user: Any, *, channel: str = "*") -> bool:
        channel = normalize_preference_key(channel, allow_wildcard=True)
        result = await execute_dml(
            self.session,
            delete(NotificationQuietHours).where(
                NotificationQuietHours.user_id == self._user_id(user),
                NotificationQuietHours.channel == channel,
            ),
        )
        return bool(result.rowcount)

    async def is_quiet(
        self,
        user: Any,
        *,
        channel: str,
        at: Optional[datetime] = None,
        priority: str = "normal",
    ) -> bool:
        """Return whether delivery is currently inside a matching quiet window."""
        at = _require_aware(at or datetime.now(timezone.utc))
        channel = normalize_preference_key(channel)
        priority = normalize_priority(priority)
        result = await self.session.execute(
            select(NotificationQuietHours).where(
                NotificationQuietHours.user_id == self._user_id(user),
                NotificationQuietHours.channel.in_([channel, "*"]),
            )
        )
        rules = {row.channel: row for row in result.scalars().all()}
        rule = rules.get(channel) or rules.get("*")
        if (
            rule is None
            or not rule.enabled
            or (priority == "urgent" and rule.allow_urgent)
        ):
            return False
        local = at.astimezone(ZoneInfo(rule.timezone))
        current = local.timetz().replace(tzinfo=None)
        start, end = rule.start_time, rule.end_time
        if start < end:
            return start <= current < end
        return current >= start or current < end

    async def next_allowed_at(
        self,
        user: Any,
        *,
        channel: str,
        at: Optional[datetime] = None,
        priority: str = "normal",
    ) -> Optional[datetime]:
        """Return the UTC instant when the active quiet window ends, if any."""
        at = _require_aware(at or datetime.now(timezone.utc))
        channel = normalize_preference_key(channel)
        priority = normalize_priority(priority)
        result = await self.session.execute(
            select(NotificationQuietHours).where(
                NotificationQuietHours.user_id == self._user_id(user),
                NotificationQuietHours.channel.in_([channel, "*"]),
            )
        )
        rules = {row.channel: row for row in result.scalars().all()}
        rule = rules.get(channel) or rules.get("*")
        if (
            rule is None
            or not rule.enabled
            or (priority == "urgent" and rule.allow_urgent)
        ):
            return None
        zone = ZoneInfo(rule.timezone)
        local = at.astimezone(zone)
        current = local.timetz().replace(tzinfo=None)
        start, end = rule.start_time, rule.end_time
        quiet = (
            start <= current < end
            if start < end
            else (current >= start or current < end)
        )
        if not quiet:
            return None
        end_date = local.date()
        if end < start <= current:
            end_date += timedelta(days=1)
        return (
            datetime.combine(end_date, end, tzinfo=zone)
            .replace(fold=local.fold)
            .astimezone(timezone.utc)
        )

    async def list_digest_schedules(
        self, user: Any
    ) -> List[NotificationDigestSchedule]:
        result = await self.session.execute(
            select(NotificationDigestSchedule)
            .where(NotificationDigestSchedule.user_id == self._user_id(user))
            .order_by(NotificationDigestSchedule.channel)
        )
        return list(result.scalars().all())

    # Keep explicit existing public options; see STATIC_ANALYSIS.md.
    async def set_digest_schedule(  # pylint: disable=too-many-arguments
        self,
        user: Any,
        *,
        channel: str = "email",
        frequency: str = "daily",
        local_time: time,
        timezone_name: str = "UTC",
        weekday: Optional[int] = None,
        enabled: bool = True,
        now: Optional[datetime] = None,
    ) -> NotificationDigestSchedule:
        channel = normalize_preference_key(channel)
        timezone_name = validate_timezone(timezone_name)
        if frequency not in {"daily", "weekly"}:
            raise ValueError("frequency must be 'daily' or 'weekly'.")
        if not isinstance(local_time, time) or local_time.tzinfo is not None:
            raise ValueError("local_time must be a timezone-naive datetime.time.")
        if frequency == "weekly" and (
            weekday is None or isinstance(weekday, bool) or not 0 <= weekday <= 6
        ):
            raise ValueError("weekly schedules require weekday between 0 and 6.")
        if frequency == "daily" and weekday is not None:
            raise ValueError("weekday is only valid for weekly schedules.")
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a boolean.")
        now = _require_aware(now or datetime.now(timezone.utc))
        next_run = _next_run(
            after=now,
            frequency=frequency,
            local_time=local_time,
            timezone_name=timezone_name,
            weekday=weekday,
        )
        values = {
            "user_id": self._user_id(user),
            "channel": channel,
            "frequency": frequency,
            "local_time": local_time,
            "timezone": timezone_name,
            "weekday": weekday,
            "enabled": enabled,
            "next_run_at": next_run,
        }
        row, inserted = await insert_if_absent(
            self.session,
            NotificationDigestSchedule,
            values,
            ("user_id", "channel"),
        )
        for key, value in values.items():
            if key not in {"user_id", "channel"}:
                setattr(row, key, value)
        if not inserted:
            # A changed schedule starts a fresh digest window; do not aggregate
            # the entire interval since the old schedule's previous execution.
            row.last_run_at = None
        await self.session.flush()
        return row

    async def reset_digest_schedule(self, user: Any, *, channel: str = "email") -> bool:
        channel = normalize_preference_key(channel)
        # ON DELETE SET NULL on digest batches preserves already-created work
        # and its audit trail after a user removes the recurring schedule.
        user_id = self._user_id(user)
        schedule_ids = select(NotificationDigestSchedule.id).where(
            NotificationDigestSchedule.user_id == user_id,
            NotificationDigestSchedule.channel == channel,
        )
        # Explicitly detach batches before deleting the schedule. This preserves
        # already-created work even on SQLite connections without FK enforcement.
        await self.session.execute(
            update(NotificationDigestBatch)
            .where(NotificationDigestBatch.schedule_id.in_(schedule_ids))
            .values(schedule_id=None)
        )
        result = await execute_dml(
            self.session,
            delete(NotificationDigestSchedule).where(
                NotificationDigestSchedule.user_id == user_id,
                NotificationDigestSchedule.channel == channel,
            ),
        )
        return bool(result.rowcount)

    async def create_due_batches(
        self,
        *,
        now: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[NotificationDigestBatch]:
        """Create idempotent batches for due schedules; does not send them.

        One batch per schedule is created per round. If a scheduler was offline for
        several periods, repeated rounds catch up missed periods fairly across schedules
        without allowing one old schedule to starve others.
        """
        now = _require_aware(now or datetime.now(timezone.utc))
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 1000
        ):
            raise ValueError("limit must be an integer between 1 and 1000.")
        result = await self.session.execute(
            select(NotificationDigestSchedule)
            .where(
                NotificationDigestSchedule.enabled.is_(True),
                NotificationDigestSchedule.next_run_at <= now,
            )
            .order_by(NotificationDigestSchedule.next_run_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        schedules = list(result.scalars().all())
        batches: List[NotificationDigestBatch] = []
        while len(batches) < limit:
            progressed = False
            for schedule in schedules:
                if schedule.next_run_at > now or len(batches) >= limit:
                    continue
                progressed = True
                scheduled_for = schedule.next_run_at
                if schedule.last_run_at is not None:
                    period_start = schedule.last_run_at
                else:
                    local_scheduled = scheduled_for.astimezone(
                        ZoneInfo(schedule.timezone)
                    )
                    previous_date = local_scheduled.date() - timedelta(
                        days=7 if schedule.frequency == "weekly" else 1
                    )
                    period_start = datetime.combine(
                        previous_date,
                        schedule.local_time,
                        tzinfo=ZoneInfo(schedule.timezone),
                    ).astimezone(timezone.utc)
                batch, _ = await insert_if_absent(
                    self.session,
                    NotificationDigestBatch,
                    {
                        "schedule_id": schedule.id,
                        "user_id": schedule.user_id,
                        "channel": schedule.channel,
                        "scheduled_for": scheduled_for,
                        "period_start": period_start,
                        "period_end": scheduled_for,
                        "status": "pending",
                        "attempts": 0,
                        "available_at": scheduled_for,
                    },
                    ("schedule_id", "scheduled_for"),
                )
                batches.append(batch)
                schedule.last_run_at = scheduled_for
                schedule.next_run_at = _next_run(
                    after=scheduled_for,
                    frequency=schedule.frequency,
                    local_time=schedule.local_time,
                    timezone_name=schedule.timezone,
                    weekday=schedule.weekday,
                )
            if not progressed:
                break
        await self.session.flush()
        return batches

    async def claim_batch(
        self,
        batch_id: int,
        *,
        now: Optional[datetime] = None,
        stale_after: timedelta = timedelta(minutes=15),
    ) -> Optional[NotificationDigestBatch]:
        """Atomically claim a batch, reclaiming abandoned processing leases.

        Delivery is at-least-once: workers should pass the batch ID to their
        provider as its idempotency key because a process may crash after a
        provider accepts a message but before ``mark_batch_sent`` commits.
        """
        now = _require_aware(now or datetime.now(timezone.utc))
        if not isinstance(stale_after, timedelta) or stale_after.total_seconds() <= 0:
            raise ValueError("stale_after must be a positive timedelta.")
        stale_before = now - stale_after
        claim_token = str(uuid4())
        result = await execute_dml(
            self.session,
            update(NotificationDigestBatch)
            .where(
                NotificationDigestBatch.id == batch_id,
                (
                    (NotificationDigestBatch.status.in_(["pending", "failed"]))
                    & (NotificationDigestBatch.available_at <= now)
                )
                | (
                    (NotificationDigestBatch.status == "processing")
                    & (NotificationDigestBatch.claimed_at <= stale_before)
                ),
            )
            .values(
                status="processing",
                attempts=NotificationDigestBatch.attempts + 1,
                claimed_at=now,
                claim_token=claim_token,
                last_error_code=None,
            ),
        )
        if not result.rowcount:
            return None
        await self.session.flush()
        batch = await self.session.get(NotificationDigestBatch, batch_id)
        if batch is not None:
            await self.session.refresh(batch)
        return batch

    async def mark_batch_sent(self, batch_id: int, *, claim_token: str) -> bool:
        claim_token = _validate_claim_token(claim_token)
        result = await execute_dml(
            self.session,
            update(NotificationDigestBatch)
            .where(
                NotificationDigestBatch.id == batch_id,
                NotificationDigestBatch.status == "processing",
                NotificationDigestBatch.claim_token == claim_token,
            )
            .values(
                status="sent",
                sent_at=datetime.now(timezone.utc),
                claimed_at=None,
                claim_token=None,
                last_error_code=None,
            ),
        )
        return bool(result.rowcount)

    async def mark_batch_failed(
        self, batch_id: int, error_code: str, *, claim_token: str
    ) -> bool:
        error_code = _validate_error_code(error_code)
        claim_token = _validate_claim_token(claim_token)
        result = await execute_dml(
            self.session,
            update(NotificationDigestBatch)
            .where(
                NotificationDigestBatch.id == batch_id,
                NotificationDigestBatch.status == "processing",
                NotificationDigestBatch.claim_token == claim_token,
            )
            .values(
                status="failed",
                claimed_at=None,
                claim_token=None,
                last_error_code=error_code,
            ),
        )
        return bool(result.rowcount)

    async def defer_batch(
        self,
        batch_id: int,
        *,
        until: datetime,
        claim_token: str,
    ) -> bool:
        """Return an owned batch to pending until a quiet window ends."""
        until = _require_aware(until)
        claim_token = _validate_claim_token(claim_token)
        result = await execute_dml(
            self.session,
            update(NotificationDigestBatch)
            .where(
                NotificationDigestBatch.id == batch_id,
                NotificationDigestBatch.status == "processing",
                NotificationDigestBatch.claim_token == claim_token,
            )
            .values(
                status="pending",
                available_at=until,
                claimed_at=None,
                claim_token=None,
            ),
        )
        return bool(result.rowcount)

    async def list_pending_batches(
        self,
        *,
        limit: int = 100,
        now: Optional[datetime] = None,
    ) -> List[NotificationDigestBatch]:
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 1000
        ):
            raise ValueError("limit must be an integer between 1 and 1000.")
        now = _require_aware(now or datetime.now(timezone.utc))
        result = await self.session.execute(
            select(NotificationDigestBatch)
            .where(
                NotificationDigestBatch.status.in_(["pending", "failed"]),
                NotificationDigestBatch.available_at <= now,
            )
            .order_by(
                NotificationDigestBatch.available_at,
                NotificationDigestBatch.created_at,
            )
            .limit(limit)
        )
        return list(result.scalars().all())


__all__ = ["NotificationSchedulingDataAccessLayer"]
