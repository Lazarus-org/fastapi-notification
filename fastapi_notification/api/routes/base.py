from typing import Any, Callable, Dict, List, Optional, Sequence, Type

from fastapi import Request
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.api.schemas.dynamic_notification import (
    NotificationDynamicSerializer,
)
from fastapi_notification.api.schemas.notification import NotificationSerializer
from fastapi_notification.identity import (
    get_identity_adapter,
    hydrate_notification_identities,
)
from fastapi_notification.mixins import ConfigurableAttrsMixin, DisableMethodsMixin
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.repository.queryset import notification as queryset
from fastapi_notification.settings.conf import config


class BaseNotificationRoutes(ConfigurableAttrsMixin, DisableMethodsMixin):
    """Shared behaviour for the notification and activity routers.

    Holds the parts the two routers have in common: choosing how much detail to
    return based on package settings, picking a serializer to match, and running
    a listing through filtering, counting and pagination. Authorization and
    audience visibility are independent of staff/superuser presentation roles.
    """

    def __init__(self, user_dependency: Optional[Callable[..., Any]] = None) -> None:
        self.configure_attrs(user_dependency)

        if not config.api_allow_list:
            self.disable_methods(["LIST"])

        if not config.api_allow_retrieve:
            self.disable_methods(["RETRIEVE"])

    async def get_user_groups(self, session: AsyncSession, user: Any) -> Sequence[str]:
        """Return the groups the current user belongs to.

        Args:
            session (AsyncSession): The session used to read.
            user (Any): The current user.

        Returns:
            Sequence[str]: The normalized identifiers of the user's groups.
        """
        return list(await get_identity_adapter().get_user_group_ids(session, user))

    def wants_detail(self, display_detail: bool) -> bool:
        """Decide whether whole notifications should be selected.

        Detail is forced whenever the response could not be built from the
        summary columns alone: when full details are switched on, or when a
        custom field list or serializer class is configured.

        Args:
            display_detail (bool): Whether the caller asked for detail.

        Returns:
            bool: Whether whole notifications should be selected.
        """
        return bool(
            display_detail
            or config.include_serializer_full_details
            or config.notification_serializer_fields
            or config.notification_serializer_class
        )

    def get_serializer_class(self, user: Any) -> Type[Any]:
        """Return the serializer selected by package settings.

        Args:
            user (Any): The current user.

        Returns:
            Type[Any]: The serializer class to use.
        """
        # Staff and superuser status must not reveal additional notification
        # fields. The representation is controlled only by explicit settings.
        del user
        if config.include_serializer_full_details:
            return NotificationSerializer

        return config.notification_serializer_class or NotificationDynamicSerializer

    def get_dal(self, session: AsyncSession) -> NotificationDataAccessLayer:
        """Return a data access layer bound to the request's session.

        Args:
            session (AsyncSession): The session used to read and write.

        Returns:
            NotificationDataAccessLayer: The data access layer.
        """
        return NotificationDataAccessLayer(session)

    async def get_statement(
        self,
        session: AsyncSession,
        user: Any,
        display_detail: bool = False,
    ) -> Select:
        """Build the statement backing this router's listing.

        Args:
            session (AsyncSession): The session used to read.
            user (Any): The current user.
            display_detail (bool): Whether the caller asked for detail.

        Returns:
            Select: The statement.

        Raises:
            NotImplementedError: Always; each router supplies its own.
        """
        raise NotImplementedError

    async def list_notifications(
        self,
        request: Request,
        session: AsyncSession,
        user: Any,
        filterset: Any,
    ) -> Dict[str, Any]:
        """Serve a listing: filter, count, page, fetch and serialize.

        Args:
            request (Request): The current request.
            session (AsyncSession): The session used to read.
            user (Any): The current user.
            filterset (Any): The filter set carrying the query parameters.

        Returns:
            Dict[str, Any]: The paginated response body.
        """
        # The query shape is selected by explicit serializer settings, never
        # by a user's staff or superuser flag.
        display_detail = self.wants_detail(False)

        statement = await self.get_statement(
            session, user, display_detail=display_detail
        )
        statement = filterset.filter_queryset(statement)

        dal = self.get_dal(session)
        total = await dal.count(statement)

        paged = self.apply_pagination(statement, request)
        rows = await queryset.fetch(session, paged, display_detail=display_detail)

        serializer = self.get_serializer_class(user)
        if display_detail:
            await hydrate_notification_identities(session, rows)
        results: List[Dict[str, Any]] = serializer.to_representation_many(rows)

        return self.paginate(request, results, total)
