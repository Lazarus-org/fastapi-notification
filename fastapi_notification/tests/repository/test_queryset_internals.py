from types import SimpleNamespace
from typing import Any, Iterator, List

import pytest
from sqlalchemy.dialects import sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.queryset import notification as queryset_module
from fastapi_notification.repository.queryset.notification import (
    NotificationQuerySet,
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


@pytest.mark.parametrize("operation", ["mark_all_as_seen", "clear_all"])
async def test_bulk_user_operations_include_identity_adapter_groups(
    monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """Bulk state changes pass host group memberships into their queries."""
    captured = {}

    class FakeAdapter:
        async def get_user_group_ids(self, session: Any, user: Any) -> List[str]:
            return ["group-17"]

    class FakeQuerySet:
        def unseen(self, **kwargs: Any) -> object:
            captured.update(kwargs)
            return object()

        def seen(self, **kwargs: Any) -> object:
            captured.update(kwargs)
            return object()

    class FakeSession:
        def add_all(self, instances: List[Any]) -> None:
            assert instances == []

        async def flush(self) -> None:
            return None

    async def fake_fetch(
        session: Any, statement: Any, display_detail: bool = False
    ) -> List[Any]:
        assert display_detail is True
        return []

    monkeypatch.setattr(
        queryset_module, "get_identity_adapter", lambda: FakeAdapter()
    )
    monkeypatch.setattr(queryset_module, "NotificationQuerySet", FakeQuerySet)
    monkeypatch.setattr(queryset_module, "fetch", fake_fetch)

    session = FakeSession()
    user = SimpleNamespace(id="user-12")
    if operation == "mark_all_as_seen":
        assert await queryset_module.mark_all_as_seen(session, user) == 0
        assert captured["unseen_by"] is user
    else:
        await queryset_module.clear_all(session, user)
        assert captured["seen_by"] is user

    assert captured["groups"] == ["group-17"]
    assert captured["display_detail"] is True


async def test_adding_no_groups_is_a_no_op(
    notification: Notification, session: AsyncSession
) -> None:
    """Addressing a notification to no groups changes nothing."""
    await add_groups(session, notification, [])
    await session.commit()
    await session.refresh(notification)

    assert notification.group == []


@pytest.mark.parametrize(
    ("identifier", "is_staff", "is_superuser"),
    [("staff-17", True, False), ("root-23", False, True)],
)
def test_elevated_roles_are_still_recipient_scoped(
    identifier: str, is_staff: bool, is_superuser: bool
) -> None:
    """Staff and superuser flags do not remove the recipient SQL predicate."""
    viewer = SimpleNamespace(
        id=identifier, is_staff=is_staff, is_superuser=is_superuser
    )
    statement = NotificationQuerySet().unseen(
        unseen_by=viewer, display_detail=True
    )
    sql = str(
        statement.compile(
            dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
        )
    )

    assert f"notification_recipient.recipient_id IN ('{identifier}')" in sql
