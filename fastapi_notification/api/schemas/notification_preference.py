"""Pydantic schemas for notification delivery preferences."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fastapi_notification.models.notification_preference import normalize_preference_key


class NotificationPreferenceUpdate(BaseModel):
    """Create or replace one preference rule for the authenticated user."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(default="*", max_length=64)
    channel: str = Field(default="*", max_length=64)
    enabled: bool

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        return normalize_preference_key(value, allow_wildcard=True)

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, value: str) -> str:
        return normalize_preference_key(value, allow_wildcard=True)


class NotificationPreferenceItem(BaseModel):
    """One stored user preference rule."""

    model_config = ConfigDict(from_attributes=True)

    category: str
    channel: str
    enabled: bool
    updated_at: datetime


class NotificationPreferenceList(BaseModel):
    """Collection of preference rules for the authenticated user."""

    results: List[NotificationPreferenceItem]
