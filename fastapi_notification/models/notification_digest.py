"""Scheduler-agnostic notification digest schedules and delivery batches."""

from __future__ import annotations

from datetime import datetime, time
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.models.base import Base, UTCDateTime, utcnow
from fastapi_notification.models.column_types import opaque_identifier, precise_time


class NotificationDigestSchedule(Base):
    """A user's recurring daily or weekly digest schedule."""

    __tablename__ = "notification_digest_schedule"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "channel", name="notification_digest_schedule_unique"
        ),
        CheckConstraint(
            "frequency IN ('daily', 'weekly')",
            name="ck_notification_digest_frequency",
        ),
        CheckConstraint(
            "(frequency = 'daily' AND weekday IS NULL) OR "
            "(frequency = 'weekly' AND weekday >= 0 AND weekday <= 6)",
            name="ck_notification_digest_frequency_weekday",
        ),
        Index("ix_notification_digest_due", "enabled", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        opaque_identifier(), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="email")
    frequency: Mapped[str] = mapped_column(String(8), nullable=False, default="daily")
    local_time: Mapped[time] = mapped_column(precise_time(), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    next_run_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, index=True
    )
    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        UTCDateTime(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


class NotificationDigestBatch(Base):
    """An idempotent digest delivery unit for an external worker to process."""

    __tablename__ = "notification_digest_batch"
    __table_args__ = (
        UniqueConstraint(
            "schedule_id", "scheduled_for", name="notification_digest_batch_unique"
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'failed')",
            name="ck_notification_digest_batch_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_notification_digest_batch_attempts"),
        CheckConstraint(
            "period_start <= period_end", name="ck_notification_digest_batch_period"
        ),
        Index(
            "ix_notification_digest_batch_status_available",
            "status",
            "available_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("notification_digest_schedule.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[str] = mapped_column(
        opaque_identifier(), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    period_start: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    period_end: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    available_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)


__all__ = ["NotificationDigestBatch", "NotificationDigestSchedule"]
