"""Association tables used by notification persistence."""

from sqlalchemy import Column, ForeignKey, String, Table

from fastapi_notification.models.base import Base

notification_group = Table(
    "notification_group",
    Base.metadata,
    Column(
        "notification_id",
        ForeignKey("notification.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("group_id", String(255), primary_key=True),
)

__all__ = ["notification_group"]
