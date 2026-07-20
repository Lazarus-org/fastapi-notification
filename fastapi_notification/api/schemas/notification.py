from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi_notification.api.schemas.base import BaseSerializer
from fastapi_notification.api.schemas.helper.get_serializer_cls import (
    group_serializer_class,
    user_serializer_class,
)
from fastapi_notification.utils.loading import loaded_collection


class NotificationSerializer(BaseSerializer):
    """Serializer for the notification model, including related group and user
    data.

    Attributes:
        id (Optional[int]): Unique identifier for the notification.
        title (Optional[str]): Computed title of the notification.
        recipient (List[Dict[str, Any]]): Users who are the recipients.
        group (List[Dict[str, Any]]): Groups associated with the notification.
        verb (Optional[str]): Action performed (e.g. "created", "updated").
        status (Optional[str]): Current status of the notification.
        actor_content_type (Optional[str]): Type of actor associated with it.
        target_content_type (Optional[str]): Type of target associated with it.
        action_object_content_type (Optional[str]): Type of action object.
        link (Optional[str]): URL link related to the notification.
        is_sent (Optional[bool]): Whether the notification has been sent.
        seen_by (List[Dict[str, Any]]): Users who have seen the notification.
        public (Optional[bool]): Whether the notification is public.
        data (Optional[Dict[str, Any]]): Additional data.
        timestamp (Optional[datetime]): Time when it was created.

    """

    id: Optional[int] = None
    title: Optional[str] = None
    recipient: List[Dict[str, Any]] = []
    group: List[Dict[str, Any]] = []
    verb: Optional[str] = None
    status: Optional[str] = None
    actor_content_type: Optional[str] = None
    target_content_type: Optional[str] = None
    action_object_content_type: Optional[str] = None
    link: Optional[str] = None
    is_sent: Optional[bool] = None
    seen_by: List[Dict[str, Any]] = []
    public: Optional[bool] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None

    @classmethod
    def to_representation(cls, instance: Any) -> Dict[str, Any]:
        """Serialize a notification, expanding its related objects.

        Args:
            instance (Any): The notification instance to serialize.

        Returns:
            Dict[str, Any]: The serialized notification.

        """
        user_serializer = user_serializer_class()
        group_serializer = group_serializer_class()

        payload = {
            "id": instance.id,
            "title": str(instance),
            "recipient": user_serializer.to_representation_many(
                loaded_collection(instance, "recipient")
            ),
            "group": group_serializer.to_representation_many(
                loaded_collection(instance, "group")
            ),
            "verb": instance.verb,
            "status": instance.status,
            "actor_content_type": _content_type_label(instance.actor_content_type),
            "target_content_type": _content_type_label(instance.target_content_type),
            "action_object_content_type": _content_type_label(
                instance.action_object_content_type
            ),
            "link": instance.link,
            "is_sent": instance.is_sent,
            "seen_by": user_serializer.to_representation_many(
                loaded_collection(instance, "seen_by")
            ),
            "public": instance.public,
            "data": instance.data,
            "timestamp": instance.timestamp,
        }

        return super().to_representation(payload)


def _content_type_label(content_type: Any) -> Optional[str]:
    """Render a content type as its dotted natural key.

    Args:
        content_type (Any): The content type, which may be ``None``.

    Returns:
        Optional[str]: The ``app_label.model`` label, or ``None``.

    """
    return str(content_type) if content_type is not None else None
