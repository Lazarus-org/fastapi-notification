from typing import Any, Dict, Optional, Tuple, Type

from pydantic import create_model

from fastapi_notification.api.schemas.base import BaseSerializer
from fastapi_notification.settings.conf import config


def build_user_serializer() -> Type[BaseSerializer]:
    """Build the user serializer from the configured field list.

    The fields are read from ``USER_SERIALIZER_FIELDS``, which defaults to the
    user model's username field plus its required fields.

    Returns:
        Type[BaseSerializer]: A serializer exposing the configured fields.
    """
    fields: Dict[str, Tuple[Any, Any]] = {
        name: (Optional[Any], None) for name in config.user_serializer_fields
    }

    return create_model(  # type: ignore[call-overload,no-any-return]
        "UserSerializer",
        __base__=BaseSerializer,
        **fields,
    )


class UserSerializer(BaseSerializer):
    """Serializer for the user model.

    Declared for import stability and OpenAPI discovery; the fields actually
    served are resolved at request time by :func:`build_user_serializer`, since
    they are configurable.
    """

    id: Optional[Any] = None
    username: Optional[str] = None
    email: Optional[str] = None

    @classmethod
    def to_representation(cls, instance: Any) -> Dict[str, Any]:
        """Serialize a user using the configured field list.

        Args:
            instance (Any): The user instance to serialize.

        Returns:
            Dict[str, Any]: The serialized user.
        """
        return build_user_serializer().to_representation(instance)
