from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, status

from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.settings.conf import config


async def get_current_user() -> Any:
    """Return the user making the current request.

    This is a placeholder: the package has no opinion on how an application
    authenticates, so a host must supply its own. Provide it either by passing
    ``current_user_dependency`` to the router factory, or by overriding this
    function through FastAPI's ``dependency_overrides``.

    Returns:
        Any: The authenticated user.

    Raises:
        NotImplementedError: Always, until the host supplies a dependency.

    """
    raise NotImplementedError(
        "fastapi-notification needs to know who is making the request. Pass"
        " current_user_dependency= to the router factory, or override"
        " fastapi_notification.api.dependencies.auth.get_current_user through"
        " app.dependency_overrides."
    )


async def get_authenticated_user(
    user: Any = Depends(get_current_user),
) -> Any:
    """Return the current user, rejecting unauthenticated requests.

    Args:
        user (Any): The user resolved by the current user dependency.

    Returns:
        Any: The authenticated user.

    Raises:
        HTTPException: With status 401 when there is no authenticated user.

    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
        )

    return user


async def require_admin_user(user: Any = Depends(get_authenticated_user)) -> Any:
    """Return the current user, rejecting anyone who is not staff.

    Args:
        user (Any): The authenticated user.

    Returns:
        Any: The staff user.

    Raises:
        HTTPException: With status 403 when the user is not staff.

    """
    if not get_identity_adapter().is_staff(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )

    return user


def make_authenticated_dependency(
    user_dependency: Callable[..., Any],
) -> Callable[..., Any]:
    """Wrap a user dependency so unauthenticated requests are refused.

    A host is free to supply any dependency it likes for resolving the current
    user; wrapping it here means the package still guarantees that every route
    runs with a real user, whatever that dependency returns.

    Args:
        user_dependency (Callable[..., Any]): The dependency resolving the
            current user.

    Returns:
        Callable[..., Any]: The guarded dependency.

    """

    async def authenticated(user: Any = Depends(user_dependency)) -> Any:
        """Return the current user, refusing the request when there is none.

        Args:
            user (Any): The resolved user.

        Returns:
            Any: The authenticated user.

        Raises:
            HTTPException: With status 401 when there is no authenticated user.

        """
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication credentials were not provided.",
            )

        return user

    return authenticated


async def apply_extra_permission(request: Request, user: Any) -> None:
    """Apply the extra permission class, when one is configured.

    The configured class is instantiated and called with the request and user;
    returning a falsy value rejects the request.

    Args:
        request (Request): The current request.
        user (Any): The authenticated user.

    Raises:
        HTTPException: With status 403 when the extra permission denies access.

    """
    permission_class = config.api_extra_permission_class

    if permission_class is None:
        return

    allowed = permission_class()(request, user)

    if hasattr(allowed, "__await__"):
        allowed = await allowed

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )


def make_extra_permission_dependency(
    user_dependency: Callable[..., Any],
) -> Callable[..., Any]:
    """Build an extra permission dependency bound to a user dependency.

    Args:
        user_dependency (Callable[..., Any]): The dependency resolving the
            current user.

    Returns:
        Callable[..., Any]: The extra permission dependency.

    """

    async def check_extra_permission(
        request: Request, user: Any = Depends(user_dependency)
    ) -> Any:
        """Apply the configured extra permission to the current user.

        Args:
            request (Request): The current request.
            user (Any): The authenticated user.

        Returns:
            Any: The authenticated user.

        """
        await apply_extra_permission(request, user)
        return user

    return check_extra_permission


def make_admin_dependency(
    user_dependency: Callable[..., Any],
) -> Callable[..., Any]:
    """Build an admin-only dependency bound to a user dependency.

    Args:
        user_dependency (Callable[..., Any]): The dependency resolving the
            current user.

    Returns:
        Callable[..., Any]: The admin-only dependency.

    """

    async def require_admin(user: Any = Depends(user_dependency)) -> Any:
        """Reject the request when the current user is not staff.

        Args:
            user (Any): The authenticated user.

        Returns:
            Any: The staff user.

        Raises:
            HTTPException: With status 403 when the user is not staff.

        """
        if not get_identity_adapter().is_staff(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )

        return user

    return require_admin


#: The extra permission dependency bound to the package's default user
#: dependency.
check_extra_permission = make_extra_permission_dependency(get_authenticated_user)
