from typing import Tuple, Type

from fastapi_notification.models.auth import User
from fastapi_notification.utils.username import get_username, get_username_field

# The user model the package serializes and addresses notifications to, along
# with the fields that identify a user. Mirrors Django's ``get_user_model()``.
UserModel: Type[User] = User
USERNAME_FIELD: str = User.USERNAME_FIELD
REQUIRED_FIELDS: Tuple[str, ...] = User.REQUIRED_FIELDS

__all__ = [
    "REQUIRED_FIELDS",
    "USERNAME_FIELD",
    "UserModel",
    "get_username",
    "get_username_field",
]
