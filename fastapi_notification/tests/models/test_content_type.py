import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.content_type import (
    ContentType,
    get_registered_model,
    natural_key_for_model,
    register_content_model,
)

pytestmark = [pytest.mark.models, pytest.mark.models_content_type]


def test_natural_key_uses_the_declared_app_label() -> None:
    """A model declaring an app label uses it in its natural key."""
    assert natural_key_for_model(User) == ("auth", "user")


def test_natural_key_falls_back_to_the_top_level_package() -> None:
    """A model with no declared app label falls back to its package."""

    class Widget:
        pass

    app_label, model = natural_key_for_model(Widget)

    assert model == "widget"
    assert app_label == Widget.__module__.split(".")[0]


def test_register_content_model_returns_the_model() -> None:
    """Registration returns the class, so it can be used as a decorator."""

    class Gadget:
        __app_label__ = "testing"

    assert register_content_model(Gadget) is Gadget
    assert get_registered_model("testing", "gadget") is Gadget


def test_get_registered_model_is_none_when_unknown() -> None:
    """An unregistered natural key resolves to nothing."""
    assert get_registered_model("nowhere", "nothing") is None


async def test_get_for_model_creates_once(session: AsyncSession) -> None:
    """Asking twice for the same model reuses the stored content type."""
    first = await ContentType.get_for_model(session, User)
    second = await ContentType.get_for_model(session, User)

    assert first.id == second.id
    assert str(first) == "auth.user"


async def test_get_object_for_this_type_loads_the_instance(
    session: AsyncSession, user: User
) -> None:
    """A content type can load an instance of the model it describes."""
    content_type = await ContentType.get_for_model(session, User)

    loaded = await content_type.get_object_for_this_type(session, user.id)

    assert loaded is not None
    assert loaded.id == user.id


async def test_get_object_for_this_type_is_none_for_a_missing_row(
    session: AsyncSession, group: Group
) -> None:
    """Asking for an absent primary key yields nothing."""
    content_type = await ContentType.get_for_model(session, Group)

    assert await content_type.get_object_for_this_type(session, 9999) is None


async def test_get_object_for_this_type_is_none_for_an_unregistered_model(
    session: AsyncSession,
) -> None:
    """A content type naming an unknown model cannot resolve an object."""
    content_type = ContentType(app_label="nowhere", model="nothing")

    assert content_type.model_class() is None
    assert await content_type.get_object_for_this_type(session, 1) is None
