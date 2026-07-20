from typing import Any, Dict, List, Optional

from fastapi_notification.api.schemas.base import BaseSerializer
from fastapi_notification.utils.loading import loaded_collection


class PermissionSerializer(BaseSerializer):
    """Serializer for the permission model.

    Attributes:
        id (Optional[int]): The primary key of the permission.
        name (Optional[str]): The human readable name.
        codename (Optional[str]): The machine readable identifier.

    """

    id: Optional[int] = None
    name: Optional[str] = None
    codename: Optional[str] = None


class GroupSerializer(BaseSerializer):
    """Serializer for the group model, including its permissions.

    Attributes:
        id (Optional[int]): The primary key of the group.
        name (Optional[str]): The name of the group.
        permissions (List[Dict[str, Any]]): The permissions granted by the group.

    """

    id: Optional[int] = None
    name: Optional[str] = None
    permissions: List[Dict[str, Any]] = []

    @classmethod
    def to_representation(cls, instance: Any) -> Dict[str, Any]:
        """Serialize a group along with its permissions.

        Args:
            instance (Any): The group instance to serialize.

        Returns:
            Dict[str, Any]: The serialized group.

        """
        payload = {
            "id": getattr(instance, "id", None),
            "name": getattr(instance, "name", None),
            "permissions": PermissionSerializer.to_representation_many(
                loaded_collection(instance, "permissions")
            ),
        }

        return super().to_representation(payload)
