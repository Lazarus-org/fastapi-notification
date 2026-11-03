from typing import Type

from fastapi_notification.api.schemas.base import BaseSerializer
from fastapi_notification.api.schemas.group import GroupSerializer
from fastapi_notification.api.schemas.user import UserSerializer
from fastapi_notification.settings.conf import config


def group_serializer_class() -> Type[BaseSerializer]:
    """Return the serializer used for the group field.

    Returns:
        Type[BaseSerializer]: The configured class, or the default.
    """
    return config.group_serializer_class or GroupSerializer


def user_serializer_class() -> Type[BaseSerializer]:
    """Return the serializer used for the recipient and seen_by fields.

    Returns:
        Type[BaseSerializer]: The configured class, or the default.
    """
    return config.user_serializer_class or UserSerializer
