import pytest

from fastapi_notification.models.auth import User
from fastapi_notification.utils.user_model import (
    REQUIRED_FIELDS,
    USERNAME_FIELD,
    UserModel,
    get_username,
)
from fastapi_notification.utils.username import (
    DEFAULT_USERNAME_FIELD,
    get_username_field,
)

pytestmark = [pytest.mark.utils]


def test_exposes_the_user_model_and_its_identifying_fields() -> None:
    """The package caches the user model and how to identify a user."""
    assert UserModel is User
    assert USERNAME_FIELD == "username"
    assert REQUIRED_FIELDS == ("email",)


def test_get_username_reads_the_declared_field(user: User) -> None:
    """A user's username is read from its declared username field."""
    assert get_username(user) == "ann"


def test_get_username_falls_back_when_absent() -> None:
    """An object with no username reports as unknown."""

    class Anonymous:
        pass

    assert get_username(Anonymous()) == "Unknown"


def test_username_field_falls_back_to_the_default() -> None:
    """A model that declares no username field uses the default name."""

    class Custom:
        pass

    assert get_username_field(Custom()) == DEFAULT_USERNAME_FIELD


def test_username_field_accepts_a_class() -> None:
    """The username field can be read from the class as well as an instance."""
    assert get_username_field(User) == "username"


def test_username_field_honours_a_custom_declaration() -> None:
    """A model may name a different field as its identifier."""

    class Custom:
        USERNAME_FIELD = "email"
        email = "someone@example.com"

    assert get_username_field(Custom) == "email"
    assert get_username(Custom()) == "someone@example.com"
