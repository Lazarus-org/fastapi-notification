from typing import Any, Callable, Dict, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.api.dependencies.auth import (
    get_current_user,
    make_authenticated_dependency,
)
from fastapi_notification.api.dependencies.db import get_session
from fastapi_notification.api.filters.notification_filter import NotificationFilter
from fastapi_notification.api.routes.base import BaseNotificationRoutes
from fastapi_notification.api.schemas.notification import NotificationSerializer


class NotificationRoutes(BaseNotificationRoutes):
    """Routes for viewing and interacting with unseen notifications.

    Features:
    - List Notifications: Retrieves a list of unseen notifications. The
      availability of this route is controlled by settings.
    - Retrieve Notification: Fetch detailed information about a specific
      notification by its ID, marking it as seen. The availability of this route
      is controlled by settings.
    - Mark All as Seen: Marks all unseen notifications for the user as seen.

    Customizations:
    - Dynamic Serializer: Depending on the user's role or configuration
      settings, either NotificationSerializer or NotificationDynamicSerializer
      is used.
    - Filtering and Searching: Supports filtering, searching and ordering
      through the notification filter set.
    - Configuration via Settings: Route availability and the level of detail
      returned are read from the package settings.

    Permissions:
    - Only authenticated users may interact with notifications.
    - Staff users see every sent notification, with full details.

    """

    async def get_statement(
        self,
        session: AsyncSession,
        user: Any,
        display_detail: bool = False,
    ) -> Select:
        """Build the statement returning the user's unseen notifications.

        Staff see every unseen notification with full details; everyone else
        sees the ones addressed to them or to a group they belong to.

        Args:
            session (AsyncSession): The session used to read.
            user (Any): The current user.
            display_detail (bool): Whether whole notifications are selected.

        Returns:
            Select: The statement.

        """
        dal = self.get_dal(session)

        if getattr(user, "is_staff", False):
            return dal.unseen_statement(unseen_by=user, display_detail=True)

        groups = await self.get_user_groups(session, user)

        return dal.unseen_statement(
            unseen_by=user,
            groups=groups,
            display_detail=self.wants_detail(display_detail),
        )


# pylint: disable=too-many-arguments
def create_notification_router(
    session_dependency: Optional[Callable[..., Any]] = None,
    current_user_dependency: Optional[Callable[..., Any]] = None,
    prefix: str = "/notifications",
    tags: Optional[Sequence[str]] = None,
) -> APIRouter:
    """Build the notifications router.

    Routes disabled in settings are never registered, so they are absent from
    the application and from its OpenAPI schema.

    Args:
        session_dependency (Optional[Callable[..., Any]]): Dependency yielding
            the database session. Defaults to the package placeholder, which a
            host may instead override through ``app.dependency_overrides``.
        current_user_dependency (Optional[Callable[..., Any]]): Dependency
            returning the authenticated user.
        prefix (str): The path prefix to mount the routes under.
        tags (Optional[Sequence[str]]): OpenAPI tags for the routes.

    Returns:
        APIRouter: The configured router.

    """
    from fastapi_notification.settings.checks import run_checks

    run_checks()

    session_dep = session_dependency or get_session
    user_dep = make_authenticated_dependency(
        current_user_dependency or get_current_user
    )
    routes = NotificationRoutes(user_dependency=user_dep)

    router = APIRouter(
        prefix=prefix,
        tags=list(tags) if tags else ["notifications"],
        dependencies=routes.dependencies,
    )

    if routes.is_method_enabled("LIST"):

        @router.get("/", summary="List unseen notifications")
        async def list_notifications(  # type: ignore[misc]
            request: Request,
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(user_dep),
            filterset: NotificationFilter = Depends(routes.get_filter_dependency()),
        ) -> Any:
            """List the notifications the current user has not seen yet.

            Args:
                request (Request): The current request.
                session (AsyncSession): The database session.
                user (Any): The authenticated user.
                filterset (NotificationFilter): The filtering parameters.

            Returns:
                Dict[str, Any]: The paginated notifications.

            """
            return await routes.list_notifications(request, session, user, filterset)

    @router.get("/mark_all_as_seen/", summary="Mark all notifications as seen")
    async def mark_all_as_seen(  # type: ignore[misc]
        session: AsyncSession = Depends(session_dep),
        user: Any = Depends(user_dep),
    ) -> Dict[str, str]:
        """Mark every unseen notification for the current user as seen.

        Args:
            session (AsyncSession): The database session.
            user (Any): The authenticated user.

        Returns:
            Dict[str, str]: How many notifications were marked as seen.

        """
        count = await routes.get_dal(session).mark_all_as_seen(user)
        await session.commit()

        return {"detail": f"{count} Notifications marked as seen."}

    if routes.is_method_enabled("RETRIEVE"):

        @router.get("/{notification_id:int}/", summary="Retrieve a notification")
        async def retrieve_notification(  # type: ignore[misc]
            notification_id: int,
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(user_dep),
            filterset: NotificationFilter = Depends(routes.get_filter_dependency()),
        ) -> Dict[str, Any]:
            """Retrieve a single notification and mark it as seen.

            Args:
                notification_id (int): The ID of the notification.
                session (AsyncSession): The database session.
                user (Any): The authenticated user.
                filterset (NotificationFilter): The filtering parameters.

            Returns:
                Dict[str, Any]: The serialized notification.

            Raises:
                HTTPException: With status 404 when the notification does not
                    exist or is not visible to the user.

            """
            statement = await routes.get_statement(session, user, display_detail=True)
            statement = filterset.filter_queryset(statement)

            notification = await routes.get_dal(session).get(
                statement, notification_id
            )

            if notification is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Not found."
                )

            data = NotificationSerializer.to_representation(notification)

            await notification.mark_as_seen(session, user)
            await session.commit()

            return data

    return router
