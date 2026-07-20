from typing import Any, Dict, List, Optional

from fastapi_notification.api.schemas.base import BaseSerializer


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
        data = super().to_representation(instance)

        permissions = getattr(instance, "permissions", None)
        if permissions is not None:
            data["permissions"] = PermissionSerializer.to_representation_many(
                permissions
            )

        return data
