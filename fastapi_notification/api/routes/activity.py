from typing import Any, Callable, Dict, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.api.dependencies.auth import (
    get_current_user,
    make_admin_dependency,
    make_authenticated_dependency,
)
from fastapi_notification.api.dependencies.db import get_session
from fastapi_notification.api.filters.notification_filter import NotificationFilter
from fastapi_notification.api.routes.base import BaseNotificationRoutes
from fastapi_notification.api.schemas.notification import NotificationSerializer
from fastapi_notification.settings.conf import config


class ActivityRoutes(BaseNotificationRoutes):
    """Routes for viewing, clearing and deleting seen notifications.

    Features:
    - List Activities: Lists all seen notifications for the user. The
      availability of this route is controlled by settings.
    - Retrieve Activity: Retrieve detailed information about a specific
      notification by its ID. The availability of this route is controlled by
      settings.
    - Clear Activities: Soft-delete one or all notifications. Controlled by
      settings.
    - Delete Activities: Permanently delete one or all notifications. Restricted
      to admin users and controlled by settings.

    Permissions:
    - Regular Users: Can list, retrieve and clear their own notifications.
    - Admin Users: Can additionally hard delete notifications, when enabled.

    """

    async def get_statement(
        self,
        session: AsyncSession,
        user: Any,
        display_detail: bool = False,
    ) -> Select:
        """Build the statement returning the user's seen notifications.

        Every user sees only activities for notifications addressed to them
        directly or to a group they belong to. Staff and superuser status does
        not widen the personal activity view.

        Args:
            session (AsyncSession): The session used to read.
            user (Any): The current user.
            display_detail (bool): Whether whole notifications are selected.

        Returns:
            Select: The statement.

        """
        dal = self.get_dal(session)
        groups = await self.get_user_groups(session, user)

        return dal.seen_statement(
            seen_by=user,
            recipients=user,
            groups=groups,
            display_detail=self.wants_detail(display_detail),
        )


# pylint: disable=too-many-arguments,too-many-statements,too-many-locals
def create_activity_router(
    session_dependency: Optional[Callable[..., Any]] = None,
    current_user_dependency: Optional[Callable[..., Any]] = None,
    prefix: str = "/activities",
    tags: Optional[Sequence[str]] = None,
) -> APIRouter:
    """Build the activities router.

    The soft delete routes are registered only when
    ``API_INCLUDE_SOFT_DELETE`` is on, and the hard delete routes only when
    ``API_INCLUDE_HARD_DELETE`` is on, so a disabled capability leaves no trace
    in the application or its OpenAPI schema.

    Args:
        session_dependency (Optional[Callable[..., Any]]): Dependency yielding
            the database session.
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
    routes = ActivityRoutes(user_dependency=user_dep)
    admin_dep = make_admin_dependency(user_dep)

    router = APIRouter(
        prefix=prefix,
        tags=list(tags) if tags else ["activities"],
        dependencies=routes.dependencies,
    )

    if routes.is_method_enabled("LIST"):

        @router.get("/", summary="List seen notifications")
        async def list_activities(  # type: ignore[misc]
            request: Request,
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(user_dep),
            filterset: NotificationFilter = Depends(routes.get_filter_dependency()),
        ) -> Any:
            """List the notifications the current user has already seen.

            Args:
                request (Request): The current request.
                session (AsyncSession): The database session.
                user (Any): The authenticated user.
                filterset (NotificationFilter): The filtering parameters.

            Returns:
                Dict[str, Any]: The paginated activities.

            """
            return await routes.list_notifications(request, session, user, filterset)

    if config.include_soft_delete:

        @router.get(
            "/clear_activities/",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Soft delete all activities",
        )
        async def clear_activities(  # type: ignore[misc]
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(user_dep),
        ) -> Response:
            """Soft delete every notification the current user has seen.

            Args:
                session (AsyncSession): The database session.
                user (Any): The authenticated user.

            Returns:
                Response: An empty 204 response.

            """
            await routes.get_dal(session).clear_all(user)
            await session.commit()

            return Response(status_code=status.HTTP_204_NO_CONTENT)

    if config.include_hard_delete:

        @router.get(
            "/delete_activities/",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Permanently delete sent notifications (administrative)",
        )
        async def delete_activities(  # type: ignore[misc]
            request: Request,
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(admin_dep),
            filterset: NotificationFilter = Depends(routes.get_filter_dependency()),
        ) -> Response:
            """Permanently delete sent notifications as an administrative action.

            This operation is deliberately global rather than scoped to the
            administrator's personal inbox. The route is registered only when
            hard deletion is enabled and requires the explicit staff guard.

            Args:
                request (Request): The current request.
                session (AsyncSession): The database session.
                user (Any): The authenticated admin user.
                filterset (NotificationFilter): The filtering parameters.

            Returns:
                Response: An empty 204 response.

            """
            # This is an explicit, staff-only administrative operation. It is
            # intentionally not derived from the admin's personal activity view.
            statement = routes.get_dal(session).sent_statement(display_detail=True)
            statement = filterset.filter_queryset(statement)

            await routes.get_dal(session).delete_many(statement)
            await session.commit()

            return Response(status_code=status.HTTP_204_NO_CONTENT)

    if routes.is_method_enabled("RETRIEVE"):

        @router.get("/{notification_id:int}/", summary="Retrieve a seen notification")
        async def retrieve_activity(  # type: ignore[misc]
            notification_id: int,
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(user_dep),
            filterset: NotificationFilter = Depends(routes.get_filter_dependency()),
        ) -> Dict[str, Any]:
            """Retrieve a single notification the current user has seen.

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

            return NotificationSerializer.to_representation(notification)

    if config.include_soft_delete:

        @router.get(
            "/{notification_id:int}/clear_notification/",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Soft delete a notification",
        )
        async def clear_notification(  # type: ignore[misc]
            notification_id: int,
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(user_dep),
        ) -> Response:
            """Soft delete a specific notification for the current user.

            Args:
                notification_id (int): The ID of the notification.
                session (AsyncSession): The database session.
                user (Any): The authenticated user.

            Returns:
                Response: An empty 204 response.

            Raises:
                HTTPException: With status 404 when the notification does not
                    exist or is not visible to the user.

            """
            try:
                await routes.get_dal(session).delete_notification(
                    notification_id=notification_id, recipient=user, soft_delete=True
                )
            except LookupError as error:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Not found."
                ) from error

            await session.commit()

            return Response(status_code=status.HTTP_204_NO_CONTENT)

    if config.include_hard_delete:

        @router.get(
            "/{notification_id:int}/delete_notification/",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Permanently delete a notification",
        )
        async def delete_notification(  # type: ignore[misc]
            notification_id: int,
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(admin_dep),
        ) -> Response:
            """Permanently delete a specific notification.

            Args:
                notification_id (int): The ID of the notification.
                session (AsyncSession): The database session.
                user (Any): The authenticated admin user.

            Returns:
                Response: An empty 204 response.

            Raises:
                HTTPException: With status 404 when the notification does not
                    exist.

            """
            try:
                await routes.get_dal(session).delete_notification(
                    notification_id=notification_id, soft_delete=False
                )
            except LookupError as error:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Not found."
                ) from error

            await session.commit()

            return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
