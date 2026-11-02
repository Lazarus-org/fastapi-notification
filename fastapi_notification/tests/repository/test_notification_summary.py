"""SQLite execution tests for notification summary and preview queries."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fastapi_notification.identity import IdentityAdapter
from fastapi_notification.models.base import Base
from fastapi_notification.models.content_type import ContentType
from fastapi_notification.models.deleted_notification import DeletedNotification
from fastapi_notification.models.notification import Notification, notification_group
from fastapi_notification.models.notification_recipient import NotificationRecipient
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.settings.conf import configure


class AsyncExecutionAdapter:
    """Expose a synchronous SQLAlchemy session through the DAL execute contract."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, statement: Any) -> Any:
        """Execute the SQL statement using the wrapped SQLite session."""
        return self.session.execute(statement)


@pytest.mark.asyncio
async def test_summary_and_preview_execute_with_sqlite() -> None:
    """Aggregate and preview queries honour audiences, state and limits."""
    configure(IDENTITY_ADAPTER=IdentityAdapter)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    user = SimpleNamespace(id=10)
    other_user = SimpleNamespace(id=1234)

    try:
        with Session(engine) as session:
            content_type = ContentType(app_label="tests", model="actor")
            session.add(content_type)
            session.flush()

            notifications = [
                Notification(
                    verb="read direct",
                    description="read direct",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=True,
                    category="orders",
                    priority="urgent",
                    timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
                ),
                Notification(
                    verb="unread group",
                    description="unread group",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=True,
                    category="social",
                    priority="low",
                    timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
                ),
                Notification(
                    verb="deleted direct",
                    description="deleted direct",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=True,
                ),
                Notification(
                    verb="other direct",
                    description="other direct",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=True,
                ),
                Notification(
                    verb="unsent direct",
                    description="unsent direct",
                    actor_content_type_id=content_type.id,
                    actor_object_id="1",
                    is_sent=False,
                ),
            ]
            session.add_all(notifications)
            session.flush()

            session.add_all(
                [
                    NotificationRecipient(
                        notification_id=notifications[0].id, recipient_id="10"
                    ),
                    NotificationRecipient(
                        notification_id=notifications[2].id, recipient_id="10"
                    ),
                    NotificationRecipient(
                        notification_id=notifications[3].id, recipient_id="99"
                    ),
                    NotificationRecipient(
                        notification_id=notifications[4].id, recipient_id="10"
                    ),
                    NotificationSeen(notification_id=notifications[0].id, user_id="10"),
                    DeletedNotification(
                        notification_id=notifications[2].id, user_id="10"
                    ),
                ]
            )
            session.execute(
                notification_group.insert().values(
                    notification_id=notifications[1].id, group_id="admins"
                )
            )
            session.flush()

            dal = NotificationDataAccessLayer(AsyncExecutionAdapter(session))  # type: ignore[arg-type]
            statement = dal.sent_statement(
                recipients=user,
                exclude_deleted_by=user,
                groups=["admins"],
                display_detail=True,
            )

            summary = await dal.summary(statement, user)
            preview = await dal.preview(statement, user, limit=1)

            assert summary == {
                "total": 2,
                "unread": 1,
                "read": 1,
                "by_category": {
                    "orders": {"total": 1, "unread": 0, "read": 1},
                    "social": {"total": 1, "unread": 1, "read": 0},
                },
                "by_priority": {
                    "urgent": {"total": 1, "unread": 0, "read": 1},
                    "low": {"total": 1, "unread": 1, "read": 0},
                },
            }
            assert len(preview) == 1
            assert preview[0]["id"] == notifications[1].id
            assert preview[0]["is_seen"] is False
            assert preview[0]["category"] == "social"
            assert preview[0]["priority"] == "low"
            assert set(preview[0]) == {
                "id",
                "verb",
                "description",
                "status",
                "category",
                "priority",
                "link",
                "timestamp",
                "expires_at",
                "is_seen",
            }

            empty_statement = dal.sent_statement(
                recipients=other_user,
                exclude_deleted_by=other_user,
                groups=[],
                display_detail=True,
            )
            assert await dal.summary(empty_statement, other_user) == {
                "total": 0,
                "unread": 0,
                "read": 0,
                "by_category": {},
                "by_priority": {},
            }
            assert await dal.preview(empty_statement, other_user, limit=5) == []
    finally:
        engine.dispose()
