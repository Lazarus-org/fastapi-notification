import pytest

from fastapi_notification.decorators.route import conditional_route, is_route_enabled

pytestmark = [pytest.mark.decorators, pytest.mark.decorators_route]


def test_a_non_boolean_condition_is_rejected() -> None:
    """The condition must be an actual boolean, not merely truthy."""
    with pytest.raises(TypeError, match="must be of type bool"):
        conditional_route("yes")  # type: ignore[arg-type]


async def test_an_enabled_route_is_marked_and_still_callable() -> None:
    """A route whose condition holds is registrable and behaves normally."""

    @conditional_route(condition=True)
    async def handler() -> str:
        return "handled"

    assert is_route_enabled(handler) is True
    assert await handler() == "handled"


async def test_a_disabled_route_is_marked_but_still_callable() -> None:
    """A route whose condition fails is not registrable, but stays callable."""

    @conditional_route(condition=False)
    async def handler() -> str:
        return "handled"

    assert is_route_enabled(handler) is False
    assert await handler() == "handled"


def test_the_wrapper_keeps_the_handler_identity() -> None:
    """Decorating preserves the handler's name and docstring."""

    @conditional_route(condition=True)
    async def handler() -> None:
        """Some documentation."""
        return None

    assert handler.__name__ == "handler"
    assert handler.__doc__ == "Some documentation."


def test_an_undecorated_handler_counts_as_enabled() -> None:
    """Handlers that were never decorated are registrable."""

    async def handler() -> None:
        pass

    assert is_route_enabled(handler) is True
