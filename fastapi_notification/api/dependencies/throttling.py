from typing import Any, Callable

from fastapi import Depends, HTTPException, status

from fastapi_notification.api.dependencies.auth import get_authenticated_user
from fastapi_notification.settings.conf import config


def check_throttle(user: Any) -> None:
    """Reject the request when the user is over their rate limit.

    The throttle class comes from ``API_THROTTLE_CLASS``; setting it to ``None``
    turns rate limiting off entirely.

    Args:
        user (Any): The authenticated user making the request.

    Raises:
        HTTPException: With status 429 when the user is over their limit, and a
            ``Retry-After`` header saying how long to wait.

    """
    throttle_class = config.api_throttle_class

    if throttle_class is None:
        return

    throttle = throttle_class()

    if not throttle.allow_request(user):
        wait = int(throttle.wait(user)) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Request was throttled. Expected available in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )


def make_throttle_dependency(
    user_dependency: Callable[..., Any],
) -> Callable[..., Any]:
    """Build a throttling dependency bound to a user dependency.

    The user is resolved through whichever dependency the host supplied, so
    throttling applies to the application's own notion of the current user.

    Args:
        user_dependency (Callable[..., Any]): The dependency resolving the
            current user.

    Returns:
        Callable[..., Any]: The throttling dependency.

    """

    async def enforce_throttle(user: Any = Depends(user_dependency)) -> Any:
        """Apply the configured rate limit to the current user.

        Args:
            user (Any): The authenticated user.

        Returns:
            Any: The authenticated user.

        """
        check_throttle(user)
        return user

    return enforce_throttle


#: The throttling dependency bound to the package's default user dependency.
enforce_throttle = make_throttle_dependency(get_authenticated_user)
