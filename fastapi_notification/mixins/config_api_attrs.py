from typing import Any, Callable, List, Optional, Type

from fastapi import Depends

from fastapi_notification.api.dependencies.auth import (
    get_authenticated_user,
    make_extra_permission_dependency,
)
from fastapi_notification.api.dependencies.throttling import make_throttle_dependency
from fastapi_notification.settings.conf import config


class ConfigurableAttrsMixin:
    """Resolves a router's behaviour from the package settings.

    Gathers the ordering and search fields, the pagination class and the
    dependency chain (authentication, the optional extra permission, and
    throttling) that every route in the router shares.

    Attributes:
        ordering_fields (Optional[List[str]]): Fields the API can be ordered by.
        search_fields (Optional[List[str]]): Fields the API can be searched on.
        pagination_class (Optional[Type[Any]]): The class used for pagination.
        dependencies (List[Any]): The shared dependency chain.
    """

    def configure_attrs(
        self, user_dependency: Optional[Callable[..., Any]] = None
    ) -> None:
        """Read every configurable attribute from the settings.

        Args:
            user_dependency (Optional[Callable[..., Any]]): The dependency
                resolving the current user. The shared dependency chain is bound
                to it, so throttling and the extra permission see the same user
                the routes do.
        """
        user_dep = user_dependency or get_authenticated_user

        self.ordering_fields: Optional[List[str]] = config.api_ordering_fields
        self.search_fields: Optional[List[str]] = config.api_search_fields
        self.filterset_class: Optional[Type[Any]] = config.api_filterset_class

        pagination_class = config.api_pagination_class
        self.pagination_class: Optional[Type[Any]] = pagination_class
        self.paginator: Optional[Any] = pagination_class() if pagination_class else None

        self.dependencies: List[Any] = [Depends(user_dep)]

        if config.api_extra_permission_class:
            self.dependencies.append(
                Depends(make_extra_permission_dependency(user_dep))
            )

        if config.api_throttle_class:
            self.dependencies.append(Depends(make_throttle_dependency(user_dep)))

    def paginate(self, request: Any, results: List[Any], count: int) -> Any:
        """Wrap a page of results using the configured paginator.

        Args:
            request (Any): The current request.
            results (List[Any]): The serialized items on this page.
            count (int): The total number of items.

        Returns:
            Any: The paginated envelope, or the bare results when pagination is
            switched off.
        """
        if self.paginator is None:
            return results

        return self.paginator.get_paginated_response(request, results, count)

    def apply_pagination(self, statement: Any, request: Any) -> Any:
        """Apply the configured limit and offset to a statement.

        Args:
            statement (Any): The statement to page.
            request (Any): The current request.

        Returns:
            Any: The paged statement, unchanged when pagination is switched off.
        """
        if self.paginator is None:
            return statement

        return statement.limit(self.paginator.get_limit(request)).offset(
            self.paginator.get_offset(request)
        )

    def get_filter_dependency(self) -> Callable[..., Any]:
        """Return the filter set class used to narrow queries.

        Returns:
            Callable[..., Any]: The configured filter set, or the default.
        """
        from fastapi_notification.api.filters.notification_filter import (
            NotificationFilter,
        )

        return self.filterset_class or NotificationFilter
