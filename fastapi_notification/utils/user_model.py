from typing import Any, Tuple, Type

from fastapi_notification.models.auth import User

# The user model the package serializes and addresses notifications to, along
# with the fields that identify a user. Mirrors Django's ``get_user_model()``.
UserModel: Type[User] = User
USERNAME_FIELD: str = User.USERNAME_FIELD
REQUIRED_FIELDS: Tuple[str, ...] = User.REQUIRED_FIELDS


def get_username(user: Any) -> str:
    """Return a user's username.

    Args:
        user (Any): The user object.

    Returns:
        str: The username of the user, or ``"Unknown"`` if the field is not
        available.

    """
    return getattr(user, USERNAME_FIELD, "Unknown")
