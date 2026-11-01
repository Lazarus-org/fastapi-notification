from typing import Any, Iterator, List

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.queryset.notification import (
    _as_sequence,
    _ids,
    add_groups,
)

pytestmark = [pytest.mark.managers]


def test_nothing_normalizes_to_an_empty_sequence() -> None:
    """An absent audience is simply nobody."""
    assert _as_sequence(None) == []


def test_a_single_instance_is_wrapped(user: User) -> None:
    """One user is treated as a sequence of one."""
    assert _as_sequence(user) == [user]


def test_a_single_group_is_wrapped(group: Group) -> None:
    """One group is treated as a sequence of one."""
    assert _as_sequence(group) == [group]


@pytest.mark.parametrize("wrapper", [list, tuple, set])
def test_collections_are_normalized(user: User, wrapper: Any) -> None:
    """Any ordinary collection is accepted as an audience."""
    assert _as_sequence(wrapper([user])) == [user]


def test_any_iterable_is_normalized(user: User, other_user: User) -> None:
    """An arbitrary iterable, such as a generator, is accepted too."""

    def people() -> Iterator[User]:
        yield user
        yield other_user

    assert _as_sequence(people()) == [user, other_user]


def test_ids_reads_primary_keys(user: User, other_user: User) -> None:
    """Instances are reduced to their primary keys."""
    assert _ids([user, other_user]) == [str(user.id), str(other_user.id)]


def test_ids_passes_raw_integers_through() -> None:
    """Primary keys may be given directly."""
    assert _ids([1, 2]) == ["1", "2"]


async def test_adding_no_groups_is_a_no_op(
    notification: Notification, session: AsyncSession
) -> None:
    """Addressing a notification to no groups changes nothing."""
    await add_groups(session, notification, [])
    await session.commit()
    await session.refresh(notification)

    assert notification.group == []
