from typing import Any

# The attribute a user model exposes to name its identifying field, mirroring
# Django's ``USERNAME_FIELD``.
USERNAME_FIELD_ATTRIBUTE = "USERNAME_FIELD"

# Used when a user model does not declare an identifying field of its own.
DEFAULT_USERNAME_FIELD = "username"


def get_username_field(user: Any) -> str:
    """Return the name of the field that identifies a user.

    Args:
        user (Any): The user object, or its class.

    Returns:
        str: The declared username field, or ``"username"`` when the model does
        not declare one.
    """
    owner = user if isinstance(user, type) else type(user)
    return getattr(owner, USERNAME_FIELD_ATTRIBUTE, DEFAULT_USERNAME_FIELD)


def get_username(user: Any) -> str:
    """Return a user's username.

    Kept free of model imports so the models themselves can depend on it.

    Args:
        user (Any): The user object.

    Returns:
        str: The username of the user, or ``"Unknown"`` if the field is not
        available.
    """
    return getattr(user, get_username_field(user), "Unknown")
