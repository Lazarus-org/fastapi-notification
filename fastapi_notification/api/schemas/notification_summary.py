"""Response schemas for notification summaries and previews."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationSummaryResponse(BaseModel):
    """Aggregate counts for the authenticated user's visible notifications."""

    total: int = Field(ge=0, description="All visible sent notifications.")
    unread: int = Field(ge=0, description="Visible notifications not yet seen.")
    read: int = Field(ge=0, description="Visible notifications already seen.")


class NotificationPreviewItem(BaseModel):
    """Compact representation of a recent notification and its read state."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    status: str
    link: Optional[str] = None
    timestamp: datetime
    is_seen: bool


class NotificationPreviewResponse(BaseModel):
    """Bounded list of the most recent visible notifications."""

    results: List[NotificationPreviewItem]
