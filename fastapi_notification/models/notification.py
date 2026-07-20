from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.base import Base, utcnow
from fastapi_notification.models.content_type import ContentType, register_content_model
from fastapi_notification.models.helper.enums.status_choices import NotificationStatus
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.models.permissions.notification_permission import (
    NotificationPermission,
)
from fastapi_notification.utils.loading import ensure_loaded
from fastapi_notification.utils.naturaltime import naturaltime

notification_group = Table(
    "notification_group",
    Base.metadata,
    Column(
        "notification_id",
        ForeignKey("notification.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("group_id", ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)


@register_content_model
class Notification(Base):
    """A notification sent to users and groups.

    Any object can be associated with a notification through the generic
    ``actor``, ``target`` and ``action_object`` relations, each stored as a
    content type and object id pair.

    Attributes:
        recipient (List[User]): Users receiving the notification.
        group (List[Group]): Groups receiving the notification.
        verb (str): The action verb associated with the notification.
        description (Optional[str]): A description of the notification.
        status (str): The current status of the notification.
        actor_content_type_id (int): Content type of the actor initiating the action.
        actor_object_id (int): ID of the actor object.
        target_content_type_id (Optional[int]): Content type of the target object.
        target_object_id (Optional[int]): ID of the target object.
        action_object_content_type_id (Optional[int]): Content type of the action object.
        action_object_object_id (Optional[int]): ID of the action object.
        link (Optional[str]): URL associated with the action.
        is_sent (bool): Indicates if the notification has been sent.
        seen_by (List[User]): Users who have seen the notification.
        public (bool): Indicates if the notification is public.
        data (Optional[dict]): Additional metadata associated with the notification.
        timestamp (datetime): Time when the notification was created.

    """

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    verb: Mapped[str] = mapped_column(
        String(127),
        nullable=False,
        comment=(
            "A short description of the action that triggered the notification"
            " (e.g., 'liked', 'commented')."
        ),
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "A textual description providing more detail about the notification."
        ),
    )
    status: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        default=NotificationStatus.INFO.value,
        comment=(
            "Indicates the notification's current status, such as 'info', 'error',"
            " or 'warning'."
        ),
    )
    actor_content_type_id: Mapped[int] = mapped_column(
        ForeignKey("content_type.id", ondelete="CASCADE"),
        nullable=False,
        comment=(
            "The content type of the object representing the actor (i.e., the"
            " initiator of the notification)."
        ),
    )
    actor_object_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="The unique ID of the actor object associated with the notification.",
    )
    target_content_type_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("content_type.id", ondelete="CASCADE"),
        nullable=True,
        comment=(
            "The content type of the target object of the notification, if applicable."
        ),
    )
    target_object_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "The unique ID of the target object associated with the notification,"
            " if applicable."
        ),
    )
    action_object_content_type_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("content_type.id", ondelete="CASCADE"),
        nullable=True,
        comment=(
            "The content type of the action object that triggered the notification,"
            " if applicable."
        ),
    )
    action_object_object_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "The unique ID of the action object associated with the notification,"
            " if applicable."
        ),
    )
    link: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        comment=(
            "A URL related to the notification or action, for further details or"
            " follow-up."
        ),
    )
    is_sent: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment=(
            "A boolean flag indicating whether this notification has already been"
            " sent to its recipients."
        ),
    )
    public: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="A boolean flag indicating if this notification is public or private.",
    )
    data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "Stores arbitrary JSON data related to the notification, such as custom"
            " attributes or metadata."
        ),
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
        comment="The date and time when this notification was created.",
    )

    recipient: Mapped[List[User]] = relationship(
        secondary="notification_recipient",
        primaryjoin="Notification.id == NotificationRecipient.notification_id",
        secondaryjoin="NotificationRecipient.recipient_id == User.id",
        viewonly=True,
        lazy="selectin",
    )
    group: Mapped[List[Group]] = relationship(
        secondary=notification_group, lazy="selectin"
    )
    seen_by: Mapped[List[User]] = relationship(
        secondary="notification_seen",
        primaryjoin="Notification.id == NotificationSeen.notification_id",
        secondaryjoin="NotificationSeen.user_id == User.id",
        viewonly=True,
        lazy="selectin",
    )

    actor_content_type: Mapped[Optional[ContentType]] = relationship(
        foreign_keys=[actor_content_type_id], lazy="selectin"
    )
    target_content_type: Mapped[Optional[ContentType]] = relationship(
        foreign_keys=[target_content_type_id], lazy="selectin"
    )
    action_object_content_type: Mapped[Optional[ContentType]] = relationship(
        foreign_keys=[action_object_content_type_id], lazy="selectin"
    )

    #: Resolved generic relation objects. These are populated when the
    #: notification is created, and by :meth:`resolve_generic_relations` when it
    #: is loaded back from the database.
    actor: ClassVar[Any] = None
    target: ClassVar[Any] = None
    action_object: ClassVar[Any] = None

    def __str__(self) -> str:
        """Return the description alongside the age of the notification.

        Returns:
            str: The string representation of the notification.

        """
        return f"{self.description} {naturaltime(self.timestamp)}"

    def title_generator(self) -> str:
        """Build the title of the notification from its generic relations.

        Returns:
            str: The generated title for the notification.

        """
        if self.target:
            if self.action_object:
                return (
                    f"{self.actor} {self.verb} {self.action_object} on {self.target}"
                )
            return f"{self.actor} {self.verb} {self.target}"
        if self.action_object:
            return f"{self.actor} {self.verb} {self.action_object}"
        return f"{self.actor} {self.verb}"

    async def resolve_generic_relations(self, session: AsyncSession) -> "Notification":
        """Load the ``actor``, ``target`` and ``action_object`` instances.

        Generic relations cannot be loaded eagerly by the ORM, so they are
        resolved on demand through the content types recorded on the row.

        Args:
            session (AsyncSession): The session used to read.

        Returns:
            Notification: This notification, with its generic relations
            populated.

        """
        pairs = (
            ("actor", self.actor_content_type, self.actor_object_id),
            ("target", self.target_content_type, self.target_object_id),
            (
                "action_object",
                self.action_object_content_type,
                self.action_object_object_id,
            ),
        )

        for attribute, content_type, object_id in pairs:
            if content_type is None or object_id is None:
                continue
            resolved = await content_type.get_object_for_this_type(session, object_id)
            setattr(self, attribute, resolved)

        return self

    async def mark_as_seen(self, session: AsyncSession, user: Any) -> None:
        """Mark the notification as seen by a specific user.

        Marking a notification as seen more than once is a no-op rather than an
        error, so repeatedly retrieving a notification stays safe.

        Args:
            session (AsyncSession): The session used to write.
            user (Any): The user who has seen the notification.

        Raises:
            PermissionError: If the user does not have permission to mark the
                notification as seen.

        """
        await ensure_loaded(session, user, "groups")
        NotificationPermission(self).validate_permission(user, "mark as seen")

        if any(seen_user.id == user.id for seen_user in self.seen_by):
            return

        session.add(NotificationSeen(notification_id=self.id, user_id=user.id))
        await session.flush()
