from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.utils.loading import ensure_loaded, loaded_collection

pytestmark = [pytest.mark.utils]


async def test_none_is_returned_untouched(session: AsyncSession) -> None:
    """Nothing to load means nothing to do."""
    assert await ensure_loaded(session, None, "groups") is None


async def test_transient_instances_are_returned_untouched(
    session: AsyncSession,
) -> None:
    """An instance that was never persisted has nothing to refresh."""
    user = User(username="pending", email="pending@example.com")

    assert await ensure_loaded(session, user, "groups") is user


async def test_unloaded_relationships_are_loaded(
    session: AsyncSession, group: Group
) -> None:
    """A persistent instance has its unloaded relationships filled in."""
    user = User(username="fresh", email="fresh@example.com")
    session.add(user)
    await session.flush()

    await session.execute(
        Group.__table__.metadata.tables["user_group"].insert(),
        [{"user_id": user.id, "group_id": group.id}],
    )
    session.expire(user, ["groups"])

    await ensure_loaded(session, user, "groups")

    assert [joined.id for joined in user.groups] == [group.id]


async def test_already_loaded_relationships_are_left_alone(
    session: AsyncSession, group_user: User
) -> None:
    """Relationships that are already loaded are not reloaded."""
    await session.refresh(group_user)

    result = await ensure_loaded(session, group_user, "groups")

    assert result is group_user
    assert len(group_user.groups) == 1


async def test_detached_instances_are_returned_untouched(
    session: AsyncSession, user: User
) -> None:
    """An instance detached from its session cannot be refreshed."""
    session.expunge(user)

    assert await ensure_loaded(session, user, "groups") is user


def test_a_missing_instance_has_no_collection() -> None:
    """Reading a collection off nothing yields nothing."""
    assert loaded_collection(None, "groups") == []


def test_an_unloaded_collection_reads_as_empty(user: User) -> None:
    """An unloaded relationship must never trigger a lazy load."""
    assert loaded_collection(user, "groups") == []


async def test_a_loaded_collection_is_returned(
    session: AsyncSession, group_user: User, group: Any
) -> None:
    """A loaded relationship is returned as it stands."""
    await session.refresh(group_user)

    assert [joined.id for joined in loaded_collection(group_user, "groups")] == [
        group.id
    ]


def test_a_plain_object_reads_through_getattr() -> None:
    """Objects outside the ORM are read directly."""

    class Plain:
        groups = ["a"]

    assert loaded_collection(Plain(), "groups") == ["a"]
    assert loaded_collection(Plain(), "missing") == []
