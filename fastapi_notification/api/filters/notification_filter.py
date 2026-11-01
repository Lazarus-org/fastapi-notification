from datetime import datetime
from typing import Any, List, Optional

from fastapi import Query, Request
from sqlalchemy import ColumnElement, Select, or_

from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.models.notification import Notification, notification_group
from fastapi_notification.models.notification_recipient import NotificationRecipient
from fastapi_notification.settings.conf import config


class NotificationFilter:
    """Applies filtering, searching and ordering to a notification statement.

    Replaces the ``django-filter`` filter set, the search backend and the
    ordering backend of the original package with a single dependency driven by
    query parameters.

    """

    def __init__(
        self,
        group__id: Optional[str] = Query(
            None, description="Filter notifications sent to this group."
        ),
        recipient__id: Optional[str] = Query(
            None, description="Filter notifications sent to this recipient."
        ),
        status: Optional[str] = Query(
            None, description="Filter notifications by status."
        ),
        public: Optional[bool] = Query(
            None, description="Filter notifications by public visibility."
        ),
        timestamp_after: Optional[datetime] = Query(
            None, description="Only notifications created at or after this time."
        ),
        timestamp_before: Optional[datetime] = Query(
            None, description="Only notifications created at or before this time."
        ),
        search: Optional[str] = Query(
            None, description="Search across the configured search fields."
        ),
        ordering: Optional[str] = Query(
            None,
            description=(
                "Order by one of the configured fields. Prefix with '-' to sort"
                " descending."
            ),
        ),
    ) -> None:
        self.group__id = group__id
        self.recipient__id = recipient__id
        self.status = status
        self.public = public
        self.timestamp_after = timestamp_after
        self.timestamp_before = timestamp_before
        self.search = search
        self.ordering = ordering

    def filter_conditions(self) -> List[ColumnElement[bool]]:
        """Build the conditions implied by the filtering parameters.

        Returns:
            List[ColumnElement[bool]]: The conditions to apply.

        """
        conditions: List[ColumnElement[bool]] = []

        if self.group__id is not None:
            conditions.append(
                Notification.id.in_(
                    notification_group.select()
                    .with_only_columns(notification_group.c.notification_id)
                    .where(
                        notification_group.c.group_id
                        == get_identity_adapter().get_group_id(self.group__id)
                    )
                )
            )

        if self.recipient__id is not None:
            conditions.append(
                Notification.id.in_(
                    NotificationRecipient.__table__.select()
                    .with_only_columns(NotificationRecipient.notification_id)
                    .where(
                        NotificationRecipient.recipient_id
                        == get_identity_adapter().get_user_id(self.recipient__id)
                    )
                )
            )

        if self.status is not None:
            conditions.append(Notification.status == self.status)

        if self.public is not None:
            conditions.append(Notification.public.is_(self.public))

        if self.timestamp_after is not None:
            conditions.append(Notification.timestamp >= self.timestamp_after)

        if self.timestamp_before is not None:
            conditions.append(Notification.timestamp <= self.timestamp_before)

        return conditions

    def search_condition(self) -> Optional[ColumnElement[bool]]:
        """Build the condition implied by the search term.

        The term is matched case insensitively against every field named in
        ``API_SEARCH_FIELDS``.

        Returns:
            Optional[ColumnElement[bool]]: The condition, or ``None`` when no
            search term was given.

        """
        if not self.search:
            return None

        clauses = [
            getattr(Notification, field).ilike(f"%{self.search}%")
            for field in config.api_search_fields
            if hasattr(Notification, field)
        ]

        if not clauses:
            return None

        return or_(*clauses)

    def apply_ordering(self, statement: Select) -> Select:
        """Apply the requested ordering to a statement.

        Only fields named in ``API_ORDERING_FIELDS`` are honoured, so a client
        cannot order by an arbitrary column.

        Args:
            statement (Select): The statement to order.

        Returns:
            Select: The ordered statement, unchanged when the requested field is
            not allowed.

        """
        if not self.ordering:
            return statement

        descending = self.ordering.startswith("-")
        field = self.ordering[1:] if descending else self.ordering

        if field not in config.api_ordering_fields:
            return statement

        column: Any = getattr(Notification, field, None)
        if column is None:
            return statement

        return statement.order_by(None).order_by(
            column.desc() if descending else column.asc()
        )

    def filter_queryset(self, statement: Select) -> Select:
        """Apply every filter, the search term and the ordering to a statement.

        Args:
            statement (Select): The statement to narrow.

        Returns:
            Select: The narrowed statement.

        """
        for condition in self.filter_conditions():
            statement = statement.where(condition)

        search = self.search_condition()
        if search is not None:
            statement = statement.where(search)

        return self.apply_ordering(statement)


def get_filterset(request: Request) -> Any:
    """Return the filter set class in use, honouring the configured override.

    Args:
        request (Request): The current request; accepted so this can be used as
            a dependency.

    Returns:
        Any: The configured filter set class, or :class:`NotificationFilter`.

    """
    return config.api_filterset_class or NotificationFilter
