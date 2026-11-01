from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from fastapi_notification.identity import (
    get_identity_adapter,
    hydrate_notification_identities,
)
from fastapi_notification.models.associations import notification_group
from fastapi_notification.models.base import Base, utcnow
from fastapi_notification.models.content_type import (
    ContentType,
    normalize_object_id,
    register_content_model,
)
from fastapi_notification.models.helper.enums.status_choices import NotificationStatus
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.models.permissions.notification_permission import (
    NotificationPermission,
)
from fastapi_notification.utils.loading import ensure_loaded
from fastapi_notification.utils.naturaltime import naturaltime


@register_content_model
class Notification(Base):
    """A notification sent to users and groups.

    Any object can be associated with a notification through the generic
    ``actor``, ``target`` and ``action_object`` relations, each stored as a
    content type and object id pair.

    Attributes:
        recipient (List[Any]): Resolved host identities receiving the notification.
        group (List[Any]): Resolved host groups receiving the notification.
        verb (str): The action verb associated with the notification.
        description (Optional[str]): A description of the notification.
        status (str): The current status of the notification.
        actor_content_type_id (int): Content type of the actor initiating the action.
        actor_object_id (str): Text-normalized ID of the actor object.
        target_content_type_id (Optional[int]): Content type of the target object.
        target_object_id (Optional[str]): Text-normalized ID of the target object.
        action_object_content_type_id (Optional[int]): Content type of the\n            action object.
        action_object_object_id (Optional[str]): Text-normalized ID of the\n            action object.
        link (Optional[str]): URL associated with the action.
        is_sent (bool): Indicates if the notification has been sent.
        seen_by (List[Any]): Resolved host identities who have seen the notification.
        public (bool): Indicates if the notification is public.
        data (Optional[dict]): Additional metadata associated with the notification.
        timestamp (datetime): Time when the notification was created.

    """

    __tablename__ = "notification"
    __serializable_identity_fields__: ClassVar[tuple[str, ...]] = (
        "recipient",
        "group",
        "seen_by",
    )

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
    actor_object_id: Mapped[str] = mapped_column(
        Text,
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
    target_object_id: Mapped[Optional[str]] = mapped_column(
        Text,
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
    action_object_object_id: Mapped[Optional[str]] = mapped_column(
        Text,
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

    # These collections are transient identity projections populated by the
    # configured adapter. They deliberately are not ORM relationships: the
    # notification schema must not require host user or group tables.
    @property
    def recipient(self) -> List[Any]:
        """Return resolved recipient identities for this notification."""
        return self.__dict__.get("_recipient_identities", [])

    @recipient.setter
    def recipient(self, value: List[Any]) -> None:
        self.__dict__["_recipient_identities"] = value

    @property
    def group(self) -> List[Any]:
        """Return resolved group identities for this notification."""
        return self.__dict__.get("_group_identities", [])

    @group.setter
    def group(self, value: List[Any]) -> None:
        self.__dict__["_group_identities"] = value

    @property
    def seen_by(self) -> List[Any]:
        """Return resolved identities that have seen this notification."""
        return self.__dict__.get("_seen_by_identities", [])

    @seen_by.setter
    def seen_by(self, value: List[Any]) -> None:
        self.__dict__["_seen_by_identities"] = value

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

    @validates(
        "actor_object_id", "target_object_id", "action_object_object_id"
    )
    def _normalize_generic_relation_identifier(
        self, key: str, value: Any
    ) -> Optional[str]:
        """Normalize generic relation identifiers assigned through the ORM."""
        if value is None:
            if key == "actor_object_id":
                raise TypeError("The actor generic relation requires an object ID.")
            return None
        return normalize_object_id(value)

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
        await ensure_loaded(
            session,
            self,
            "actor_content_type",
            "target_content_type",
            "action_object_content_type",
        )

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

    async def load_identities(self, session: AsyncSession) -> "Notification":
        """Resolve recipient, group, and seen-by identities for this instance.

        ORM relationships to host authentication models are intentionally not
        declared. Use this method after loading a notification directly through
        SQLAlchemy; the data access layer and HTTP routes call it automatically.

        Args:
            session (AsyncSession): The session used to resolve host identities.

        Returns:
            Notification: This notification with its identity projections loaded.
        """
        await hydrate_notification_identities(session, [self])
        return self

    async def mark_as_seen(self, session: AsyncSession, user: Any) -> None:
        """Mark the notification as seen by a specific user.

        Marking a notification as seen more than once is a no-op rather than an
        error, so repeating the explicit mark-as-seen action stays safe.

        Args:
            session (AsyncSession): The session used to write.
            user (Any): The user who has seen the notification.

        Raises:
            PermissionError: If the user does not have permission to mark the
                notification as seen.

        """
        await NotificationPermission(self).validate_permission_async(
            session, user, "mark as seen"
        )

        user_id = get_identity_adapter().get_user_id(user)
        existing = await session.execute(
            select(NotificationSeen.id).where(
                NotificationSeen.notification_id == self.id,
                NotificationSeen.user_id == user_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return

        session.add(NotificationSeen(notification_id=self.id, user_id=user_id))
        await session.flush()
        current_seen = list(self.seen_by)
        current_seen.append(user)
        self.seen_by = current_seen
