from functools import wraps
from typing import Any, Callable


def conditional_route(condition: bool) -> Callable:
    """Mark a route handler as registrable only when a condition holds.

    Replaces the original package's ``conditional_action`` decorator. Rather
    than registering a route that would reject every request, the router simply
    leaves it out, so a disabled endpoint is absent from the application and
    from its OpenAPI schema.

    Args:
        condition (bool): Whether the route should be registered.

    Returns:
        Callable: A decorator that tags the handler with the condition.

    Raises:
        TypeError: If ``condition`` is not a boolean.

    """
    if not isinstance(condition, bool):
        raise TypeError("The 'condition' argument must be of type bool.")

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapped_func(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        wrapped_func.route_enabled = condition  # type: ignore[attr-defined]
        return wrapped_func

    return decorator


def is_route_enabled(func: Callable) -> bool:
    """Report whether a handler is enabled.

    Handlers that were never decorated are treated as enabled.

    Args:
        func (Callable): The handler to inspect.

    Returns:
        bool: Whether the route should be registered.

    """
    return bool(getattr(func, "route_enabled", True))
