from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from fastapi import Request


class DefaultLimitOffSetPagination:
    """Limit/offset pagination that clamps the page size to a sane range.

    A limit below the minimum, or one that is not a number, falls back to the
    default; a limit above the maximum is capped rather than rejected, so a
    client asking for too much still gets a usable response.

    """

    # Minimum limit allowed in query parameters
    min_limit: int = 1

    # Maximum limit allowed in query parameters
    max_limit: int = 100

    # Default limit when no limit is specified
    default_limit: int = 10

    # Query parameter names, matching the original package.
    limit_query_param: str = "limit"
    offset_query_param: str = "offset"

    def get_limit(self, request: Request) -> int:
        """Resolve the page size from the request's query parameters.

        Args:
            request (Request): The request carrying the pagination parameters.

        Returns:
            int: The number of items to return, constrained by the configured
            minimum and maximum, or the default when not usable.

        """
        limit = request.query_params.get(self.limit_query_param)

        if limit:
            try:
                parsed = int(limit)

                if parsed < self.min_limit:
                    return self.default_limit

                if parsed > self.max_limit:
                    return self.max_limit

                return parsed

            except ValueError:
                pass

        return self.default_limit

    def get_offset(self, request: Request) -> int:
        """Resolve the offset from the request's query parameters.

        Args:
            request (Request): The request carrying the pagination parameters.

        Returns:
            int: The number of items to skip; never negative.

        """
        offset = request.query_params.get(self.offset_query_param)

        if offset:
            try:
                return max(int(offset), 0)
            except ValueError:
                pass

        return 0

    def _build_url(self, request: Request, offset: int, limit: int) -> str:
        """Build a page URL preserving the request's other query parameters.

        Args:
            request (Request): The current request.
            offset (int): The offset of the page being linked to.
            limit (int): The page size.

        Returns:
            str: The absolute URL of that page.

        """
        params: Dict[str, Any] = dict(request.query_params)
        params[self.limit_query_param] = limit
        params[self.offset_query_param] = offset

        return f"{request.url.remove_query_params(list(params))}?{urlencode(params)}"

    def get_next_link(
        self, request: Request, offset: int, limit: int, count: int
    ) -> Optional[str]:
        """Return the URL of the next page, if there is one.

        Args:
            request (Request): The current request.
            offset (int): The offset of the current page.
            limit (int): The page size.
            count (int): The total number of items.

        Returns:
            Optional[str]: The next page URL, or ``None`` on the last page.

        """
        if offset + limit >= count:
            return None
        return self._build_url(request, offset + limit, limit)

    def get_previous_link(
        self, request: Request, offset: int, limit: int
    ) -> Optional[str]:
        """Return the URL of the previous page, if there is one.

        Args:
            request (Request): The current request.
            offset (int): The offset of the current page.
            limit (int): The page size.

        Returns:
            Optional[str]: The previous page URL, or ``None`` on the first page.

        """
        if offset <= 0:
            return None
        return self._build_url(request, max(offset - limit, 0), limit)

    def get_paginated_response(
        self, request: Request, results: List[Any], count: int
    ) -> Dict[str, Any]:
        """Wrap a page of results in the paginated response envelope.

        Args:
            request (Request): The current request.
            results (List[Any]): The serialized items on this page.
            count (int): The total number of items across all pages.

        Returns:
            Dict[str, Any]: The response body, with ``count``, ``next``,
            ``previous`` and ``results``.

        """
        limit = self.get_limit(request)
        offset = self.get_offset(request)

        return {
            "count": count,
            "next": self.get_next_link(request, offset, limit, count),
            "previous": self.get_previous_link(request, offset, limit),
            "results": results,
        }
