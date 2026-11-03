"""Database-backed tests for quiet-hour and digest scheduling DAL."""

from datetime import datetime, time, timedelta, timezone
from typing import Any

import pytest

from fastapi_notification.models.notification_digest import (
    NotificationDigestBatch,
    NotificationDigestSchedule,
)
from fastapi_notification.models.notification_quiet_hours import NotificationQuietHours
from fastapi_notification.repository.manager.scheduling import (
    NotificationSchedulingDataAccessLayer,
)


async def test_quiet_hours_support_overnight_windows(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    await dal.set_quiet_hours(
        user,
        channel="email",
        start_time=time(22),
        end_time=time(7),
        timezone_name="UTC",
        allow_urgent=True,
    )
    assert (
        await dal.is_quiet(
            user, channel="email", at=datetime(2026, 11, 2, 23, tzinfo=timezone.utc)
        )
        is True
    )
    assert (
        await dal.is_quiet(
            user, channel="email", at=datetime(2026, 11, 2, 6, tzinfo=timezone.utc)
        )
        is True
    )
    assert (
        await dal.is_quiet(
            user, channel="email", at=datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        )
        is False
    )
    assert (
        await dal.is_quiet(
            user,
            channel="email",
            at=datetime(2026, 11, 2, 23, tzinfo=timezone.utc),
            priority="urgent",
        )
        is False
    )


async def test_quiet_hours_return_next_allowed_instant(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    await dal.set_quiet_hours(
        user, channel="*", start_time=time(22), end_time=time(7), timezone_name="UTC"
    )
    result = await dal.next_allowed_at(
        user, channel="email", at=datetime(2026, 11, 2, 23, tzinfo=timezone.utc)
    )
    assert result == datetime(2026, 11, 3, 7, tzinfo=timezone.utc)


async def test_quiet_hours_are_user_scoped(session, user, other_user):
    dal = NotificationSchedulingDataAccessLayer(session)
    await dal.set_quiet_hours(
        user, start_time=time(22), end_time=time(7), timezone_name="UTC"
    )
    assert len(await dal.list_quiet_hours(user)) == 1
    assert await dal.list_quiet_hours(other_user) == []


async def test_digest_schedule_creates_due_idempotent_batch(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    now = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    schedule = await dal.set_digest_schedule(
        user, frequency="daily", local_time=time(9), timezone_name="UTC", now=now
    )
    due = schedule.next_run_at
    batches = await dal.create_due_batches(now=due)
    assert len(batches) == 1
    assert batches[0].status == "pending"
    assert batches[0].period_end == due
    assert schedule.next_run_at > due
    assert await dal.create_due_batches(now=due) == []


async def test_digest_batch_claim_and_complete_are_state_guarded(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    now = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    schedule = await dal.set_digest_schedule(
        user, local_time=time(9), timezone_name="UTC", now=now
    )
    batch = (await dal.create_due_batches(now=schedule.next_run_at))[0]
    claimed = await dal.claim_batch(batch.id, now=schedule.next_run_at)
    assert claimed is not None and claimed.attempts == 1
    assert await dal.claim_batch(batch.id, now=schedule.next_run_at) is None
    assert await dal.mark_batch_sent(batch.id) is True
    assert await dal.mark_batch_sent(batch.id) is False


async def test_failed_digest_batch_can_be_retried(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    now = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    schedule = await dal.set_digest_schedule(
        user, local_time=time(9), timezone_name="UTC", now=now
    )
    batch = (await dal.create_due_batches(now=schedule.next_run_at))[0]
    assert await dal.claim_batch(batch.id, now=schedule.next_run_at)
    assert await dal.mark_batch_failed(batch.id, "provider unavailable")
    retry = await dal.claim_batch(
        batch.id, now=schedule.next_run_at + timedelta(minutes=1)
    )
    assert retry is not None and retry.attempts == 2


def test_scheduling_models_are_registered():
    assert NotificationQuietHours.__tablename__ == "notification_quiet_hours"
    assert NotificationDigestSchedule.__tablename__ == "notification_digest_schedule"
    assert NotificationDigestBatch.__tablename__ == "notification_digest_batch"


async def test_disabled_exact_quiet_rule_overrides_enabled_wildcard(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    await dal.set_quiet_hours(
        user,
        channel="*",
        start_time=time(22),
        end_time=time(7),
        timezone_name="UTC",
        enabled=True,
    )
    await dal.set_quiet_hours(
        user,
        channel="email",
        start_time=time(22),
        end_time=time(7),
        timezone_name="UTC",
        enabled=False,
    )
    assert (
        await dal.is_quiet(
            user, channel="email", at=datetime(2026, 11, 2, 23, tzinfo=timezone.utc)
        )
        is False
    )


async def test_schedule_removal_preserves_created_digest_batch(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    now = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    schedule = await dal.set_digest_schedule(
        user, local_time=time(9), timezone_name="UTC", now=now
    )
    batch = (await dal.create_due_batches(now=schedule.next_run_at))[0]
    await dal.reset_digest_schedule(user, channel="email")
    await session.flush()
    persisted = await session.get(NotificationDigestBatch, batch.id)
    assert persisted is not None
    assert persisted.schedule_id is None


async def test_deferred_batch_is_not_claimable_until_available(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    now = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    schedule = await dal.set_digest_schedule(
        user, local_time=time(9), timezone_name="UTC", now=now
    )
    batch = (await dal.create_due_batches(now=schedule.next_run_at))[0]
    assert await dal.claim_batch(batch.id, now=schedule.next_run_at)
    release_at = schedule.next_run_at + timedelta(hours=2)
    assert await dal.defer_batch(batch.id, until=release_at)
    assert (
        await dal.claim_batch(batch.id, now=schedule.next_run_at + timedelta(hours=1))
        is None
    )
    assert await dal.claim_batch(batch.id, now=release_at) is not None


async def test_abandoned_processing_batch_can_be_reclaimed(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    now = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    schedule = await dal.set_digest_schedule(
        user, local_time=time(9), timezone_name="UTC", now=now
    )
    batch = (await dal.create_due_batches(now=schedule.next_run_at))[0]
    assert await dal.claim_batch(batch.id, now=schedule.next_run_at)
    reclaimed = await dal.claim_batch(
        batch.id, now=schedule.next_run_at + timedelta(minutes=16)
    )
    assert reclaimed is not None
    assert reclaimed.attempts == 2


async def test_quiet_hours_reset_is_idempotent(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    await dal.set_quiet_hours(
        user, channel="push", start_time=time(22), end_time=time(7), timezone_name="UTC"
    )
    assert await dal.reset_quiet_hours(user, channel="push") is True
    assert await dal.reset_quiet_hours(user, channel="push") is False


async def test_digest_schedule_reset_preserves_batches(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    now = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    schedule = await dal.set_digest_schedule(
        user, local_time=time(9), timezone_name="UTC", now=now
    )
    batch = (await dal.create_due_batches(now=schedule.next_run_at))[0]
    assert await dal.reset_digest_schedule(user, channel="email") is True
    assert await session.get(NotificationDigestBatch, batch.id) is not None
    assert await session.get(NotificationDigestSchedule, schedule.id) is None


async def test_due_batch_creation_catches_up_missed_daily_periods(session, user):
    dal = NotificationSchedulingDataAccessLayer(session)
    start = datetime(2026, 11, 2, 8, tzinfo=timezone.utc)
    schedule = await dal.set_digest_schedule(
        user, local_time=time(9), timezone_name="UTC", now=start
    )
    batches = await dal.create_due_batches(
        now=datetime(2026, 11, 4, 10, tzinfo=timezone.utc), limit=10
    )
    assert len(batches) == 3
    assert [batch.scheduled_for.day for batch in batches] == [2, 3, 4]
    assert schedule.next_run_at == datetime(2026, 11, 5, 9, tzinfo=timezone.utc)


async def test_quiet_end_in_second_dst_fold_is_in_the_future(
    session: Any, user: Any
) -> None:
    dal = NotificationSchedulingDataAccessLayer(session)
    await dal.set_quiet_hours(
        user,
        start_time=time(0),
        end_time=time(1, 30),
        timezone_name="America/New_York",
    )
    at = datetime(2026, 11, 1, 6, 15, tzinfo=timezone.utc)
    assert await dal.is_quiet(user, channel="email", at=at)
    assert await dal.next_allowed_at(user, channel="email", at=at) == datetime(
        2026, 11, 1, 6, 30, tzinfo=timezone.utc
    )
