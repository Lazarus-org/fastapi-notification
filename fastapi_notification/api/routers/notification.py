from typing import Any, Callable, Optional, Sequence

from fastapi import APIRouter

from fastapi_notification.api.routes.activity import create_activity_router
from fastapi_notification.api.routes.notification import create_notification_router


def create_router(
    session_dependency: Optional[Callable[..., Any]] = None,
    current_user_dependency: Optional[Callable[..., Any]] = None,
    prefix: str = "",
    tags: Optional[Sequence[str]] = None,
) -> APIRouter:
    """Build a single router carrying both the notification and activity routes.

    This is the one call most applications need: include the result in the app
    and both endpoint groups are mounted, configured from the package settings.

    Args:
        session_dependency (Optional[Callable[..., Any]]): Dependency yielding
            the database session.
        current_user_dependency (Optional[Callable[..., Any]]): Dependency
            returning the authenticated user.
        prefix (str): A path prefix applied to both groups.
        tags (Optional[Sequence[str]]): OpenAPI tags applied to both groups.

    Returns:
        APIRouter: The combined router.

    """
    router = APIRouter(prefix=prefix)

    router.include_router(
        create_notification_router(
            session_dependency=session_dependency,
            current_user_dependency=current_user_dependency,
            tags=tags,
        )
    )
    router.include_router(
        create_activity_router(
            session_dependency=session_dependency,
            current_user_dependency=current_user_dependency,
            tags=tags,
        )
    )

    return router
