from datetime import datetime, timedelta, timezone
from typing import Any, Callable, List

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.api.filters.notification_filter import (
    NotificationFilter,
    get_filterset,
)
from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.api, pytest.mark.api_filters]


def make_filter(**parameters: Any) -> NotificationFilter:
    """Build a filter set with the given query parameters.

    Args:
        **parameters (Any): The query parameters to apply.

    Returns:
        NotificationFilter: The filter set.
    """
    defaults = {
        "group__id": None,
        "recipient__id": None,
        "status": None,
        "category": None,
        "priority": None,
        "public": None,
        "timestamp_after": None,
        "timestamp_before": None,
        "search": None,
        "ordering": None,
    }
    defaults.update(parameters)

    return NotificationFilter(**defaults)


async def run(
    dal: NotificationDataAccessLayer, filterset: NotificationFilter
) -> List[Notification]:
    """Run a filter set against every sent notification.

    Args:
        dal (NotificationDataAccessLayer): The data access layer.
        filterset (NotificationFilter): The filter set to apply.

    Returns:
        List[Notification]: The matching notifications.
    """
    statement = filterset.filter_queryset(dal.sent_statement(display_detail=True))

    return await dal._execute(statement, display_detail=True)


async def test_no_parameters_matches_everything(
    dal: NotificationDataAccessLayer, notifications: List[Notification]
) -> None:
    """A filter set with nothing set narrows nothing."""
    assert len(await run(dal, make_filter())) == 3


async def test_filtering_by_recipient(
    dal: NotificationDataAccessLayer,
    user: User,
    other_user: User,
    session: AsyncSession,
) -> None:
    """Notifications can be narrowed to one recipient."""
    await dal.create_notification(
        verb="for ann", actor=user, recipients=user, is_sent=True
    )
    await dal.create_notification(
        verb="for bob", actor=user, recipients=other_user, is_sent=True
    )
    await session.commit()

    rows = await run(dal, make_filter(recipient__id=other_user.id))

    assert [row.verb for row in rows] == ["for bob"]


async def test_filtering_by_group(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    session: AsyncSession,
) -> None:
    """Notifications can be narrowed to one group."""
    await dal.create_notification(
        verb="for the group", actor=user, groups=group, is_sent=True
    )
    await dal.create_notification(
        verb="for ann", actor=user, recipients=user, is_sent=True
    )
    await session.commit()

    rows = await run(dal, make_filter(group__id=group.id))

    assert [row.verb for row in rows] == ["for the group"]


async def test_filtering_by_status(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Notifications can be narrowed by status."""
    await dal.create_notification(
        verb="urgent", actor=user, recipients=user, status="CRITICAL", is_sent=True
    )
    await dal.create_notification(
        verb="routine", actor=user, recipients=user, is_sent=True
    )
    await session.commit()

    rows = await run(dal, make_filter(status="CRITICAL"))

    assert [row.verb for row in rows] == ["urgent"]


async def test_filtering_by_builtin_and_custom_category(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Category filters accept built-in and namespaced application keys."""
    await dal.create_notification(
        verb="order", actor=user, recipients=user, category="orders", is_sent=True
    )
    await dal.create_notification(
        verb="billing",
        actor=user,
        recipients=user,
        category="Com.Example.Billing",
        is_sent=True,
    )
    await session.commit()

    assert [row.verb for row in await run(dal, make_filter(category="ORDERS"))] == [
        "order"
    ]
    assert [
        row.verb for row in await run(dal, make_filter(category="com.example.billing"))
    ] == ["billing"]


async def test_filtering_by_priority(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Priority filters match the normalized priority key."""
    await dal.create_notification(
        verb="urgent", actor=user, recipients=user, priority="urgent", is_sent=True
    )
    await dal.create_notification(
        verb="routine", actor=user, recipients=user, priority="normal", is_sent=True
    )
    await session.commit()

    rows = await run(dal, make_filter(priority="urgent"))
    assert [row.verb for row in rows] == ["urgent"]


async def test_priority_ordering_uses_urgency_rank(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Descending priority puts urgent first and uses timestamp as a tie-breaker."""
    for priority in ("low", "urgent", "normal", "high"):
        await dal.create_notification(
            verb=priority,
            actor=user,
            recipients=user,
            priority=priority,
            is_sent=True,
        )
    await session.commit()

    rows = await run(dal, make_filter(ordering="-priority"))
    assert [row.priority for row in rows] == ["urgent", "high", "normal", "low"]

    ascending = await run(dal, make_filter(ordering="priority"))
    assert [row.priority for row in ascending] == ["low", "normal", "high", "urgent"]


def test_filter_rejects_invalid_category_or_priority() -> None:
    """Invalid taxonomy filters are rejected before SQL is constructed."""
    import pytest

    with pytest.raises(ValueError, match="category"):
        make_filter(category="bad category")
    with pytest.raises(ValueError, match="priority"):
        make_filter(priority="immediate")


async def test_filtering_by_visibility(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Notifications can be narrowed by public visibility."""
    await dal.create_notification(
        verb="private", actor=user, recipients=user, public=False, is_sent=True
    )
    await dal.create_notification(
        verb="public", actor=user, recipients=user, is_sent=True
    )
    await session.commit()

    assert [row.verb for row in await run(dal, make_filter(public=False))] == [
        "private"
    ]
    assert [row.verb for row in await run(dal, make_filter(public=True))] == ["public"]


async def test_filtering_by_a_timestamp_range(
    dal: NotificationDataAccessLayer,
    notifications: List[Notification],
) -> None:
    """Notifications can be narrowed to a window in time."""
    now = datetime.now(timezone.utc)

    within = await run(
        dal,
        make_filter(
            timestamp_after=now - timedelta(hours=1),
            timestamp_before=now + timedelta(hours=1),
        ),
    )
    outside = await run(dal, make_filter(timestamp_after=now + timedelta(hours=1)))

    assert len(within) == 3
    assert len(outside) == 0


async def test_searching_matches_the_configured_fields(
    dal: NotificationDataAccessLayer, notifications: List[Notification]
) -> None:
    """A search term is matched across the configured search fields."""
    assert len(await run(dal, make_filter(search="thing 1"))) == 1
    assert len(await run(dal, make_filter(search="THING"))) == 3
    assert len(await run(dal, make_filter(search="nothing here"))) == 0


async def test_searching_with_no_usable_fields_matches_everything(
    dal: NotificationDataAccessLayer, notifications: List[Notification]
) -> None:
    """When no configured search field exists, the term is ignored."""
    configure(API_SEARCH_FIELDS=["not_a_column"])

    assert len(await run(dal, make_filter(search="thing"))) == 3


async def test_ordering_by_an_allowed_field(
    dal: NotificationDataAccessLayer, notifications: List[Notification]
) -> None:
    """Ordering by a permitted field is honoured, in both directions."""
    ascending = await run(dal, make_filter(ordering="id"))
    descending = await run(dal, make_filter(ordering="-id"))

    assert [row.id for row in ascending] == sorted(row.id for row in ascending)
    assert [row.id for row in descending] == sorted(
        (row.id for row in descending), reverse=True
    )


async def test_ordering_by_an_unpermitted_field_is_ignored(
    dal: NotificationDataAccessLayer, notifications: List[Notification]
) -> None:
    """A field outside the allowed list cannot be ordered by."""
    rows = await run(dal, make_filter(ordering="verb"))

    assert [row.id for row in rows] == sorted((row.id for row in rows), reverse=True)


async def test_ordering_by_a_permitted_but_absent_column_is_ignored(
    dal: NotificationDataAccessLayer, notifications: List[Notification]
) -> None:
    """A permitted name that is not a column is ignored rather than failing."""
    configure(API_ORDERING_FIELDS=["id", "not_a_column"])

    rows = await run(dal, make_filter(ordering="not_a_column"))

    assert len(rows) == 3


def test_the_default_filterset_is_reported() -> None:
    """With nothing configured, the packaged filter set is used."""
    assert get_filterset(None) is NotificationFilter


def test_a_configured_filterset_is_reported() -> None:
    """A configured filter set replaces the packaged one."""
    configure(
        API_FILTERSET_CLASS=(
            "fastapi_notification.api.filters.notification_filter.NotificationFilter"
        )
    )

    assert get_filterset(None) is NotificationFilter


def test_direct_construction_has_plain_defaults() -> None:
    """Dependency metadata must not become filter values in direct DAL use."""
    from sqlalchemy import select

    filterset = NotificationFilter()
    statement = select(Notification)
    assert filterset.filter_conditions() == []
    assert filterset.search_condition() is None
    assert filterset.apply_ordering(statement) is statement
    assert str(filterset.filter_queryset(statement)) == str(statement)


def test_partial_direct_construction_only_applies_explicit_filters() -> None:
    filterset = NotificationFilter(category="security", priority="urgent")
    assert len(filterset.filter_conditions()) == 2
    assert filterset.search is None
    assert filterset.ordering is None
