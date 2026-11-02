"""Response schemas for notification summaries and previews."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationCountBreakdown(BaseModel):
    """Total/read/unread counts for one category or priority value."""

    total: int = Field(ge=0)
    unread: int = Field(ge=0)
    read: int = Field(ge=0)


class NotificationSummaryResponse(BaseModel):
    """Aggregate counts, broken down by category and priority."""

    total: int = Field(ge=0, description="All visible sent notifications.")
    unread: int = Field(ge=0, description="Visible notifications not yet seen.")
    read: int = Field(ge=0, description="Visible notifications already seen.")
    by_category: Dict[str, NotificationCountBreakdown] = Field(
        default_factory=dict,
        description="Total, unread and read counts grouped by category key.",
    )
    by_priority: Dict[str, NotificationCountBreakdown] = Field(
        default_factory=dict,
        description="Total, unread and read counts grouped by priority.",
    )


class NotificationPreviewItem(BaseModel):
    """Compact representation of a recent notification and its read state."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    status: str
    category: str
    priority: str
    link: Optional[str] = None
    timestamp: datetime
    expires_at: Optional[datetime]
    is_seen: bool


class NotificationPreviewResponse(BaseModel):
    """Bounded list of the most recent visible notifications."""

    results: List[NotificationPreviewItem]
