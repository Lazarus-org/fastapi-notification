"""API schemas for quiet hours and digest schedules."""

from datetime import datetime, time
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fastapi_notification.models.notification_preference import normalize_preference_key
from fastapi_notification.models.notification_quiet_hours import validate_timezone


class QuietHoursUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str = "*"
    start_time: time
    end_time: time
    timezone: str = "UTC"
    enabled: bool = True
    allow_urgent: bool = True

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        return normalize_preference_key(value, allow_wildcard=True)

    @field_validator("timezone")
    @classmethod
    def validate_timezone_name(cls, value: str) -> str:
        return validate_timezone(value)

    @model_validator(mode="after")
    def validate_window(self):
        if self.start_time.tzinfo is not None or self.end_time.tzinfo is not None:
            raise ValueError(
                "quiet-hour times must be timezone-naive wall-clock times."
            )
        if self.start_time == self.end_time:
            raise ValueError("start_time and end_time must be different.")
        return self


class QuietHoursItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    channel: str
    start_time: time
    end_time: time
    timezone: str
    enabled: bool
    allow_urgent: bool
    updated_at: datetime


class QuietHoursList(BaseModel):
    results: List[QuietHoursItem]


class DigestScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str = "email"
    frequency: str = "daily"
    local_time: time
    timezone: str = "UTC"
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    enabled: bool = True

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        return normalize_preference_key(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone_name(cls, value: str) -> str:
        return validate_timezone(value)

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value: str) -> str:
        if value not in {"daily", "weekly"}:
            raise ValueError("frequency must be 'daily' or 'weekly'.")
        return value

    @model_validator(mode="after")
    def validate_weekday(self):
        if self.local_time.tzinfo is not None:
            raise ValueError("local_time must be a timezone-naive wall-clock time.")
        if self.frequency == "weekly" and self.weekday is None:
            raise ValueError("weekly schedules require weekday.")
        if self.frequency == "daily" and self.weekday is not None:
            raise ValueError("weekday is only valid for weekly schedules.")
        return self


class DigestScheduleItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    channel: str
    frequency: str
    local_time: time
    timezone: str
    weekday: Optional[int]
    enabled: bool
    next_run_at: datetime
    last_run_at: Optional[datetime]


class DigestScheduleList(BaseModel):
    results: List[DigestScheduleItem]
