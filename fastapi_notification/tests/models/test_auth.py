import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, Permission, User

pytestmark = [pytest.mark.models]


async def test_user_str_is_the_username(user: User) -> None:
    """A user renders as its username."""
    assert str(user) == "ann"


async def test_group_str_is_the_name(group: Group) -> None:
    """A group renders as its name."""
    assert str(group) == "admins"


async def test_permission_str_is_the_name(session: AsyncSession) -> None:
    """A permission renders as its name."""
    permission = Permission(name="Can view notifications", codename="view_notification")
    session.add(permission)
    await session.commit()

    assert str(permission) == "Can view notifications"


async def test_group_membership_is_visible_from_both_sides(
    session: AsyncSession, group: Group, group_user: User
) -> None:
    """Joining a group is reflected on the group and on the user."""
    await session.refresh(group)

    assert [member.id for member in group.users] == [group_user.id]
    assert [joined.id for joined in group_user.groups] == [group.id]


async def test_group_permissions_are_loaded(session: AsyncSession) -> None:
    """A group exposes the permissions granted to it."""
    permission = Permission(name="Can clear", codename="clear_notification")
    session.add(permission)
    await session.flush()

    group = Group(name="clearers", permissions=[permission])
    session.add(group)
    await session.commit()
    await session.refresh(group)

    assert [granted.codename for granted in group.permissions] == ["clear_notification"]
