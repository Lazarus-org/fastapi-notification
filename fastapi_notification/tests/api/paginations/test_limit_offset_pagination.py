from typing import Any

import pytest
from fastapi import Request

from fastapi_notification.api.paginations.limit_offset_pagination import (
    DefaultLimitOffSetPagination,
)

pytestmark = [pytest.mark.api, pytest.mark.api_paginations]


def make_request(query: str = "") -> Request:
    """Build a request carrying the given query string.

    Args:
        query (str): The raw query string.

    Returns:
        Request: The request.
    """
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/notifications/",
            "raw_path": b"/notifications/",
            "query_string": query.encode(),
            "headers": [(b"host", b"testserver")],
            "scheme": "http",
            "server": ("testserver", 80),
            "root_path": "",
        }
    )


@pytest.fixture
def paginator() -> DefaultLimitOffSetPagination:
    """Provide a paginator.

    Returns:
        DefaultLimitOffSetPagination: The paginator.
    """
    return DefaultLimitOffSetPagination()


def test_no_limit_uses_the_default(paginator: Any) -> None:
    """Asking for no page size gets the default one."""
    assert paginator.get_limit(make_request()) == 10


def test_a_valid_limit_is_honoured(paginator: Any) -> None:
    """A sensible page size is used as given."""
    assert paginator.get_limit(make_request("limit=25")) == 25


def test_a_limit_below_the_minimum_falls_back(paginator: Any) -> None:
    """A page size below the minimum falls back to the default."""
    assert paginator.get_limit(make_request("limit=0")) == 10


def test_a_limit_above_the_maximum_is_capped(paginator: Any) -> None:
    """A page size above the maximum is capped rather than rejected."""
    assert paginator.get_limit(make_request("limit=5000")) == 100


def test_a_non_numeric_limit_falls_back(paginator: Any) -> None:
    """A page size that is not a number falls back to the default."""
    assert paginator.get_limit(make_request("limit=lots")) == 10


def test_no_offset_starts_at_the_beginning(paginator: Any) -> None:
    """With no offset, the first page is served."""
    assert paginator.get_offset(make_request()) == 0


def test_a_valid_offset_is_honoured(paginator: Any) -> None:
    """A sensible offset is used as given."""
    assert paginator.get_offset(make_request("offset=20")) == 20


def test_a_negative_offset_is_clamped(paginator: Any) -> None:
    """A negative offset is treated as the beginning."""
    assert paginator.get_offset(make_request("offset=-5")) == 0


def test_a_non_numeric_offset_falls_back(paginator: Any) -> None:
    """An offset that is not a number is treated as the beginning."""
    assert paginator.get_offset(make_request("offset=lots")) == 0


def test_the_next_link_is_absent_on_the_last_page(paginator: Any) -> None:
    """There is no next page once every item has been served."""
    assert paginator.get_next_link(make_request(), offset=0, limit=10, count=5) is None


def test_the_next_link_points_at_the_following_page(paginator: Any) -> None:
    """The next link advances the offset by one page."""
    link = paginator.get_next_link(make_request("limit=10"), 0, 10, 30)

    assert "offset=10" in link
    assert "limit=10" in link


def test_the_previous_link_is_absent_on_the_first_page(paginator: Any) -> None:
    """There is no previous page at the beginning."""
    assert paginator.get_previous_link(make_request(), offset=0, limit=10) is None


def test_the_previous_link_points_at_the_preceding_page(paginator: Any) -> None:
    """The previous link rewinds the offset by one page."""
    link = paginator.get_previous_link(make_request("limit=10"), 20, 10)

    assert "offset=10" in link


def test_the_previous_link_does_not_go_below_zero(paginator: Any) -> None:
    """Rewinding past the beginning stops at the beginning."""
    link = paginator.get_previous_link(make_request("limit=10"), 5, 10)

    assert "offset=0" in link


def test_links_preserve_the_other_query_parameters(paginator: Any) -> None:
    """Filtering and ordering survive a move between pages."""
    link = paginator.get_next_link(make_request("limit=10&status=INFO"), 0, 10, 30)

    assert "status=INFO" in link


def test_the_response_wraps_the_page(paginator: Any) -> None:
    """The envelope reports the total alongside the page and its links."""
    response = paginator.get_paginated_response(
        make_request("limit=2&offset=2"), results=[{"id": 3}, {"id": 4}], count=10
    )

    assert response["count"] == 10
    assert response["results"] == [{"id": 3}, {"id": 4}]
    assert "offset=4" in response["next"]
    assert "offset=0" in response["previous"]
