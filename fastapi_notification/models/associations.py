"""Association tables used by notification persistence."""

from sqlalchemy import Column, ForeignKey, String, Table

from fastapi_notification.models.base import Base
from fastapi_notification.models.column_types import opaque_identifier

notification_group = Table(
    "notification_group",
    Base.metadata,
    Column(
        "notification_id",
        ForeignKey("notification.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("group_id", opaque_identifier(), primary_key=True),
)

__all__ = ["notification_group"]
