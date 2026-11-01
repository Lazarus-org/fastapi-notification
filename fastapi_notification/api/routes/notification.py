from typing import Any, Callable, Dict, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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
from fastapi_notification.api.schemas.notification_summary import (
    NotificationPreviewItem,
    NotificationPreviewResponse,
    NotificationSummaryResponse,
)
from fastapi_notification.utils.serialization import generate_title


class NotificationRoutes(BaseNotificationRoutes):
    """Routes for viewing and interacting with unseen notifications.

    Features:
    - List Notifications: Retrieves a list of unseen notifications. The
      availability of this route is controlled by settings.
    - Retrieve Notification: Fetch detailed information about a specific
      unseen notification. Retrieval is read-only.
    - Mark Notification as Seen: Explicitly mark one notification as seen using
      POST.
    - Mark All as Seen: Marks all unseen notifications for the user as seen
      using POST.
    - Summary: Returns aggregate total, unread and read counts.
    - Preview: Returns a bounded set of recent notifications with read state.

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
    - Every user, including staff and superusers, sees only notifications
      addressed to them directly or through a group they belong to.

    """

    async def get_statement(
        self,
        session: AsyncSession,
        user: Any,
        display_detail: bool = False,
    ) -> Select:
        """Build the statement returning the user's unseen notifications.

        Every user sees only unseen notifications addressed to them directly
        or to a group they belong to. Staff and superuser status does not widen
        the notification audience.

        Args:
            session (AsyncSession): The session used to read.
            user (Any): The current user.
            display_detail (bool): Whether whole notifications are selected.

        Returns:
            Select: The statement.

        """
        dal = self.get_dal(session)
        groups = await self.get_user_groups(session, user)

        return dal.unseen_statement(
            unseen_by=user,
            recipients=user,
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

        @router.get(
            "/summary/",
            response_model=NotificationSummaryResponse,
            summary="Get notification counts",
        )
        async def notification_summary(  # type: ignore[misc]
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(user_dep),
            filterset: NotificationFilter = Depends(routes.get_filter_dependency()),
        ) -> Dict[str, int]:
            """Return total, unread and read counts for the current user.

            Counts include sent notifications addressed directly to the user or
            to one of their groups, exclude notifications cleared by that user,
            and honour the same filters as the notification listing.

            """
            dal = routes.get_dal(session)
            groups = await routes.get_user_groups(session, user)
            statement = dal.sent_statement(
                recipients=user,
                exclude_deleted_by=user,
                groups=groups,
                display_detail=True,
            )
            statement = filterset.filter_queryset(statement)
            return await dal.summary(statement, user)

        @router.get(
            "/preview/",
            response_model=NotificationPreviewResponse,
            summary="Preview recent notifications",
        )
        async def notification_preview(  # type: ignore[misc]
            limit: int = Query(5, ge=1, le=20, description="Maximum preview items."),
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(user_dep),
            filterset: NotificationFilter = Depends(routes.get_filter_dependency()),
        ) -> Dict[str, Any]:
            """Return the most recent visible notifications, read or unread.

            The response is bounded to 1–20 items (5 by default). It includes
            direct and group notifications, excludes unsent and user-cleared
            notifications, and reports whether the current user has seen each
            item.

            """
            dal = routes.get_dal(session)
            groups = await routes.get_user_groups(session, user)
            statement = dal.sent_statement(
                recipients=user,
                exclude_deleted_by=user,
                groups=groups,
                display_detail=True,
            )
            statement = filterset.filter_queryset(statement)
            rows = await dal.preview(statement, user, limit)
            results = [
                NotificationPreviewItem(
                    id=row["id"],
                    title=generate_title(
                        {
                            "description": row["description"] or row["verb"],
                            "timestamp": row["timestamp"],
                        }
                    ),
                    description=row["description"],
                    status=row["status"],
                    link=row["link"],
                    timestamp=row["timestamp"],
                    is_seen=bool(row["is_seen"]),
                )
                for row in rows
            ]
            return NotificationPreviewResponse(results=results).model_dump()

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

    @router.post("/mark_all_as_seen/", summary="Mark all notifications as seen")
    async def mark_all_as_seen(  # type: ignore[misc]
        session: AsyncSession = Depends(session_dep),
        user: Any = Depends(user_dep),
    ) -> Dict[str, str]:
        """Mark every unseen notification for the current user as seen.

        This state-changing action is exposed through POST rather than GET.

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
            """Retrieve a single unseen notification without changing its state.

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

        @router.post(
            "/{notification_id:int}/mark_as_seen/",
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Mark a notification as seen",
        )
        async def mark_notification_as_seen(  # type: ignore[misc]
            notification_id: int,
            session: AsyncSession = Depends(session_dep),
            user: Any = Depends(user_dep),
        ) -> Response:
            """Mark one notification as seen by the current user.

            The notification must be sent to the current user or to one of their
            groups, and must not have been soft-deleted by that user. Repeating
            the request is harmless.

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
            dal = routes.get_dal(session)
            groups = await routes.get_user_groups(session, user)
            statement = dal.sent_statement(
                recipients=user,
                exclude_deleted_by=user,
                groups=groups,
                display_detail=True,
            )
            notification = await dal.get(statement, notification_id)

            if notification is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Not found."
                )

            await notification.mark_as_seen(session, user)
            await session.commit()

            return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
