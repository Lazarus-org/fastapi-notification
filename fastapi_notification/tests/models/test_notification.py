import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.notification import Notification
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)

pytestmark = [pytest.mark.models, pytest.mark.models_notification]


async def test_str_includes_description_and_age(notification: Notification) -> None:
    """The string form pairs the description with how long ago it happened."""
    assert str(notification).startswith("ann liked your post")
    assert str(notification).endswith("now")


async def test_description_is_generated_from_actor_and_verb(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """A notification with no description describes itself."""
    created = await dal.create_notification(verb="waved", actor=user)
    await session.commit()

    assert created.description == "ann waved"


async def test_description_is_kept_when_supplied(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """An explicit description is never overwritten."""
    created = await dal.create_notification(
        verb="waved", actor=user, description="something specific"
    )
    await session.commit()

    assert created.description == "something specific"


async def test_title_generator_with_target(
    dal: NotificationDataAccessLayer, user: User, group: Group, session: AsyncSession
) -> None:
    """A target is woven into the generated title."""
    created = await dal.create_notification(verb="joined", actor=user, target=group)
    await session.commit()

    assert created.title_generator() == "ann joined admins"


async def test_title_generator_with_target_and_action_object(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    other_user: User,
    session: AsyncSession,
) -> None:
    """Both a target and an action object are woven into the title."""
    created = await dal.create_notification(
        verb="added", actor=user, action_object=other_user, target=group
    )
    await session.commit()

    assert created.title_generator() == "ann added bob on admins"


async def test_title_generator_with_action_object_only(
    dal: NotificationDataAccessLayer,
    user: User,
    other_user: User,
    session: AsyncSession,
) -> None:
    """An action object alone still produces a title."""
    created = await dal.create_notification(
        verb="mentioned", actor=user, action_object=other_user
    )
    await session.commit()

    assert created.title_generator() == "ann mentioned bob"


async def test_resolve_generic_relations_loads_every_reference(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    other_user: User,
    session: AsyncSession,
) -> None:
    """Reloading a notification can restore its generic references."""
    created = await dal.create_notification(
        verb="added", actor=user, action_object=other_user, target=group
    )
    await session.commit()

    reloaded = await session.get(Notification, created.id)
    assert reloaded is not None
    await reloaded.resolve_generic_relations(session)

    assert reloaded.actor is not None
    assert user is not None
    assert reloaded.actor.id == user.id
    assert group is not None
    assert reloaded.target is not None
    assert reloaded.target.id == group.id
    assert other_user is not None
    assert reloaded.action_object is not None
    assert reloaded.action_object.id == other_user.id


async def test_resolve_generic_relations_skips_absent_references(
    notification: Notification, session: AsyncSession
) -> None:
    """References that were never set stay unset."""
    reloaded = await session.get(Notification, notification.id)
    assert reloaded is not None
    await reloaded.resolve_generic_relations(session)

    assert reloaded.actor is not None
    assert reloaded.target is None
    assert reloaded.action_object is None


async def test_mark_as_seen_records_the_viewer(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """Marking a notification as seen records who saw it."""
    await notification.mark_as_seen(session, user)
    await session.commit()
    await session.refresh(notification)

    assert [seen.id for seen in notification.seen_by] == [user.id]


async def test_mark_as_seen_is_idempotent(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """Seeing a notification twice does not record it twice."""
    await notification.mark_as_seen(session, user)
    await session.commit()
    await session.refresh(notification)

    await notification.mark_as_seen(session, user)
    await session.commit()
    await session.refresh(notification)

    assert len(notification.seen_by) == 1


async def test_mark_as_seen_rejects_an_unrelated_user(
    notification: Notification, other_user: User, session: AsyncSession
) -> None:
    """A user with no claim on a notification cannot mark it as seen."""
    with pytest.raises(PermissionError, match="mark as seen"):
        await notification.mark_as_seen(session, other_user)


async def test_mark_as_seen_allows_a_group_member(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
) -> None:
    """Membership of a targeted group grants permission."""
    created = await dal.create_notification(
        verb="announced", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    await session.refresh(created)

    await created.mark_as_seen(session, group_user)
    await session.commit()
    await session.refresh(created)

    assert [seen.id for seen in created.seen_by] == [group_user.id]


async def test_mark_as_seen_rejects_staff_without_audience_membership(
    notification: Notification, staff_user: User, session: AsyncSession
) -> None:
    """Staff cannot mark another user's notification as seen."""
    with pytest.raises(PermissionError, match="mark as seen"):
        await notification.mark_as_seen(session, staff_user)


async def test_mark_as_seen_rejects_superuser_without_audience_membership(
    notification: Notification, superuser_only: User, session: AsyncSession
) -> None:
    """Superuser status alone does not grant notification access."""
    with pytest.raises(PermissionError, match="mark as seen"):
        await notification.mark_as_seen(session, superuser_only)


async def test_to_dict_exposes_the_mapped_columns(
    notification: Notification,
) -> None:
    """The base model can render itself as a plain dictionary."""
    data = notification.to_dict()

    assert data["id"] == notification.id
    assert data["verb"] == "liked your post"
    assert "recipient" not in data


async def test_mark_as_seen_refreshes_projection_when_record_already_exists(
    notification: Notification, user: User, session: AsyncSession
) -> None:
    """An idempotent retry still updates the in-memory seen-by projection."""
    session.add(NotificationSeen(notification_id=notification.id, user_id=str(user.id)))
    await session.flush()

    notification.seen_by = []
    await notification.mark_as_seen(session, user)

    assert [identity.id for identity in notification.seen_by] == [user.id]
