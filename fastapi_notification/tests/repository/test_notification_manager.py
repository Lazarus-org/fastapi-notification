from typing import Any, List

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.deleted_notification import DeletedNotification
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.repository.queryset.notification import NotificationQuerySet

pytestmark = [pytest.mark.managers]


async def test_create_addresses_recipients_and_groups(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    session: AsyncSession,
) -> None:
    """A notification can be addressed to users and groups at once."""
    created = await dal.create_notification(
        verb="announced", actor=user, recipients=user, groups=group, is_sent=True
    )
    await session.commit()
    await session.refresh(created)

    assert [person.id for person in created.recipient] == [user.id]
    assert [targeted.id for targeted in created.group] == [group.id]


async def test_create_stores_every_supplied_field(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Every field passed to create is persisted."""
    created = await dal.create_notification(
        verb="published",
        actor=user,
        description="a description",
        status="WARNING",
        public=False,
        link="https://example.com/posts/1",
        is_sent=True,
        data={"key": "value"},
    )
    await session.commit()

    assert created.status == "WARNING"
    assert created.public is False
    assert created.link == "https://example.com/posts/1"
    assert created.data == {"key": "value"}


async def test_create_accepts_a_list_of_recipients(
    dal: NotificationDataAccessLayer,
    user: User,
    other_user: User,
    session: AsyncSession,
) -> None:
    """Several recipients can be addressed in one call."""
    created = await dal.create_notification(
        verb="announced", actor=user, recipients=[user, other_user], is_sent=True
    )
    await session.commit()
    await session.refresh(created)

    assert len(created.recipient) == 2


async def test_sent_and_unsent_are_partitioned(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """A notification is either sent or unsent, never both."""
    await dal.create_notification(
        verb="delivered", actor=user, recipients=user, is_sent=True
    )
    await dal.create_notification(verb="queued", actor=user, recipients=user)
    await session.commit()

    sent = await dal.sent(recipients=user, display_detail=True)
    unsent = await dal.unsent(recipients=user, display_detail=True)

    assert [item.verb for item in sent] == ["delivered"]
    assert [item.verb for item in unsent] == ["queued"]


async def test_summary_rows_carry_only_the_default_fields(
    dal: NotificationDataAccessLayer, notification: Notification, user: User
) -> None:
    """Without detail, rows are plain mappings of the summary columns."""
    rows = await dal.sent(recipients=user)

    assert set(rows[0]) == {"id", "description", "status", "link", "timestamp"}


async def test_all_notifications_can_be_narrowed(
    dal: NotificationDataAccessLayer,
    user: User,
    other_user: User,
    session: AsyncSession,
) -> None:
    """Listing everything can still be filtered by audience."""
    await dal.create_notification(verb="for ann", actor=user, recipients=user)
    await dal.create_notification(verb="for bob", actor=user, recipients=other_user)
    await session.commit()

    everything = await dal.all_notifications(display_detail=True)
    just_ann = await dal.all_notifications(recipients=user, display_detail=True)

    assert len(everything) == 2
    assert [item.verb for item in just_ann] == ["for ann"]


async def test_all_notifications_can_be_narrowed_by_group(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    session: AsyncSession,
) -> None:
    """Listing everything can be filtered by group."""
    await dal.create_notification(verb="for the group", actor=user, groups=group)
    await dal.create_notification(verb="for nobody", actor=user)
    await session.commit()

    rows = await dal.all_notifications(groups=group, display_detail=True)

    assert [item.verb for item in rows] == ["for the group"]


async def test_unseen_then_seen_after_marking(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    user: User,
    session: AsyncSession,
) -> None:
    """Marking a notification as seen moves it between the two views."""
    assert len(await dal.unseen(user, display_detail=True)) == 1
    assert len(await dal.seen(user, display_detail=True)) == 0

    await dal.mark_all_as_seen(user)
    await session.commit()

    assert len(await dal.unseen(user, display_detail=True)) == 0
    assert len(await dal.seen(user, display_detail=True)) == 1


async def test_mark_all_as_seen_reports_how_many(
    dal: NotificationDataAccessLayer,
    notifications: List[Notification],
    user: User,
    session: AsyncSession,
) -> None:
    """Marking everything as seen reports the number affected."""
    assert await dal.mark_all_as_seen(user) == 3
    await session.commit()

    assert await dal.mark_all_as_seen(user) == 0


async def test_mark_all_as_seen_includes_group_notifications(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
) -> None:
    """Bulk seen operations include notifications addressed to user groups."""
    await dal.create_notification(
        verb="group announcement", actor=user, groups=group, is_sent=True
    )
    await session.commit()

    assert await dal.mark_all_as_seen(group_user) == 1
    await session.commit()

    assert len(
        await dal.unseen(group_user, groups=[group], display_detail=True)
    ) == 0
    assert len(await dal.seen(group_user, groups=[group], display_detail=True)) == 1


async def test_mark_all_as_seen_does_not_duplicate_multiple_audiences(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
) -> None:
    """A notification addressed directly and through a group is counted once."""
    await dal.create_notification(
        verb="shared announcement",
        actor=user,
        recipients=group_user,
        groups=group,
        is_sent=True,
    )
    await session.commit()

    assert await dal.mark_all_as_seen(group_user) == 1
    await session.commit()
    assert len(await dal.seen(group_user, groups=[group], display_detail=True)) == 1


async def test_mark_all_as_sent_reports_how_many(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Marking everything as sent reports the number affected."""
    await dal.create_notification(verb="queued", actor=user, recipients=user)
    await session.commit()

    assert await dal.mark_all_as_sent(recipients=user) == 1
    await session.commit()

    assert await dal.mark_all_as_sent(recipients=user) == 0


async def test_mark_all_as_sent_can_target_a_group(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    session: AsyncSession,
) -> None:
    """Sending can be scoped to a group's notifications."""
    await dal.create_notification(verb="queued", actor=user, groups=group)
    await session.commit()

    assert await dal.mark_all_as_sent(groups=group) == 1


async def test_staff_only_see_notifications_addressed_to_them(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    staff_user: User,
) -> None:
    """Staff status does not widen the personal notification audience."""
    assert len(await dal.unseen(staff_user, display_detail=True)) == 0


async def test_superusers_only_see_notifications_addressed_to_them(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    superuser_only: User,
) -> None:
    """Superuser status does not widen the personal notification audience."""
    assert len(await dal.unseen(superuser_only, display_detail=True)) == 0


async def test_regular_users_only_see_their_own(
    dal: NotificationDataAccessLayer, notification: Notification, other_user: User
) -> None:
    """A regular user sees nothing addressed to someone else."""
    assert len(await dal.unseen(other_user, display_detail=True)) == 0


async def test_group_members_see_group_notifications(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
) -> None:
    """Membership of a targeted group brings a notification into view."""
    await dal.create_notification(
        verb="announced", actor=user, groups=group, is_sent=True
    )
    await session.commit()

    rows = await dal.unseen(group_user, groups=[group], display_detail=True)

    assert [item.verb for item in rows] == ["announced"]


async def test_clear_all_soft_deletes_seen_notifications(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    user: User,
    session: AsyncSession,
) -> None:
    """Clearing hides seen notifications without destroying them."""
    await dal.mark_all_as_seen(user)
    await session.commit()

    await dal.clear_all(user)
    await session.commit()

    assert len(await dal.seen(user, display_detail=True)) == 0
    assert len(await dal.deleted(user)) == 1
    assert await session.get(Notification, notification.id) is not None


async def test_clear_all_includes_group_notifications(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
) -> None:
    """Bulk clearing soft-deletes seen notifications addressed to groups."""
    notification = await dal.create_notification(
        verb="group activity", actor=user, groups=group, is_sent=True
    )
    await session.commit()

    assert await dal.mark_all_as_seen(group_user) == 1
    await session.commit()
    await dal.clear_all(group_user)
    await session.commit()

    assert len(
        await dal.seen(group_user, groups=[group], display_detail=True)
    ) == 0
    assert len(await dal.deleted(group_user)) == 1
    assert await session.get(Notification, notification.id) is not None


async def test_deleted_can_be_listed_for_everyone(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    user: User,
    session: AsyncSession,
) -> None:
    """Soft deletions can be listed across every user."""
    await dal.delete_notification(notification.id, recipient=user, soft_delete=True)
    await session.commit()

    assert len(await dal.deleted()) == 1


async def test_soft_delete_hides_only_for_that_user(
    dal: NotificationDataAccessLayer,
    user: User,
    other_user: User,
    session: AsyncSession,
) -> None:
    """One recipient clearing a notification leaves it for the others."""
    created = await dal.create_notification(
        verb="announced", actor=user, recipients=[user, other_user], is_sent=True
    )
    await session.commit()

    await dal.delete_notification(created.id, recipient=user, soft_delete=True)
    await session.commit()

    assert len(await dal.sent(exclude_deleted_by=user, display_detail=True)) == 0
    assert len(await dal.sent(exclude_deleted_by=other_user, display_detail=True)) == 1


async def test_soft_delete_requires_a_recipient(
    dal: NotificationDataAccessLayer, notification: Notification
) -> None:
    """A soft delete has to be attributed to someone."""
    with pytest.raises(ValueError, match="most be given"):
        await dal.delete_notification(notification.id, soft_delete=True)


async def test_hard_delete_removes_the_row(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    session: AsyncSession,
) -> None:
    """A hard delete destroys the notification."""
    await dal.delete_notification(notification.id, soft_delete=False)
    await session.commit()

    assert await session.get(Notification, notification.id) is None


async def test_staff_cannot_delete_another_users_notification_with_recipient_scope(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    staff_user: User,
    session: AsyncSession,
) -> None:
    """Passing a staff identity does not bypass recipient authorization."""
    with pytest.raises(LookupError, match="No notification found"):
        await dal.delete_notification(
            notification.id, recipient=staff_user, soft_delete=False
        )

    await session.rollback()
    assert await session.get(Notification, notification.id) is not None


async def test_group_member_can_soft_delete_group_notification(
    dal: NotificationDataAccessLayer,
    user: User,
    group: Group,
    group_user: User,
    session: AsyncSession,
) -> None:
    """Group audience membership permits clearing a group notification."""
    notification = await dal.create_notification(
        verb="group update", actor=user, groups=group, is_sent=True
    )
    await session.commit()

    await dal.delete_notification(notification.id, recipient=group_user)
    await session.commit()

    deleted = await dal.deleted(group_user, display_detail=True)
    assert [item.id for item in deleted] == [notification.id]


async def test_deleting_an_unknown_notification_is_reported(
    dal: NotificationDataAccessLayer, user: User
) -> None:
    """Deleting something that is not there fails clearly."""
    with pytest.raises(LookupError, match="No notification found"):
        await dal.delete_notification(9999, recipient=user, soft_delete=True)


async def test_deleting_someone_elses_notification_is_reported(
    dal: NotificationDataAccessLayer, notification: Notification, other_user: User
) -> None:
    """A notification you cannot see is one you cannot delete."""
    with pytest.raises(LookupError):
        await dal.delete_notification(
            notification.id, recipient=other_user, soft_delete=True
        )


async def test_update_changes_only_what_is_given(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    session: AsyncSession,
) -> None:
    """Fields left out of an update keep their previous value."""
    updated = await dal.update_notification(notification.id, public=False)
    await session.commit()

    assert updated.public is False
    assert updated.is_sent is True
    assert updated.data is None


async def test_update_can_change_every_field(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    session: AsyncSession,
) -> None:
    """Everything an update accepts can be changed at once."""
    updated = await dal.update_notification(
        notification.id, is_sent=False, public=False, data={"key": "value"}
    )
    await session.commit()

    assert updated.is_sent is False
    assert updated.public is False
    assert updated.data == {"key": "value"}


async def test_updating_an_unknown_notification_is_reported(
    dal: NotificationDataAccessLayer,
) -> None:
    """Updating something that is not there fails clearly."""
    with pytest.raises(LookupError, match="No notification found"):
        await dal.update_notification(9999, public=False)


async def test_get_returns_a_visible_notification(
    dal: NotificationDataAccessLayer, notification: Notification, user: User
) -> None:
    """A notification visible through a statement can be fetched by id."""
    statement = dal.sent_statement(recipients=user, display_detail=True)

    fetched = await dal.get(statement, notification.id)

    assert fetched is not None
    assert fetched.id == notification.id


async def test_get_is_none_for_an_invisible_notification(
    dal: NotificationDataAccessLayer, notification: Notification, other_user: User
) -> None:
    """A notification outside the statement is not fetched."""
    statement = dal.sent_statement(recipients=other_user, display_detail=True)

    assert await dal.get(statement, notification.id) is None


async def test_count_matches_the_rows_returned(
    dal: NotificationDataAccessLayer, notifications: List[Notification], user: User
) -> None:
    """Counting a statement agrees with running it."""
    statement = dal.sent_statement(recipients=user, display_detail=True)

    assert await dal.count(statement) == 3


async def test_delete_many_removes_every_match(
    dal: NotificationDataAccessLayer,
    notifications: List[Notification],
    user: User,
    session: AsyncSession,
) -> None:
    """A statement's worth of notifications can be destroyed at once."""
    statement = dal.sent_statement(recipients=user, display_detail=True)

    assert await dal.delete_many(statement) == 3
    await session.commit()

    assert await dal.count(dal.sent_statement(display_detail=True)) == 0


async def test_delete_many_on_no_matches_is_a_no_op(
    dal: NotificationDataAccessLayer, user: User
) -> None:
    """Deleting nothing reports nothing deleted."""
    statement = dal.sent_statement(recipients=user, display_detail=True)

    assert await dal.delete_many(statement) == 0


async def test_the_query_set_is_exposed(dal: NotificationDataAccessLayer) -> None:
    """The statement builder behind the data access layer is reachable."""
    assert isinstance(dal.get_queryset(), NotificationQuerySet)


async def test_notifications_are_ordered_newest_first(
    dal: NotificationDataAccessLayer, notifications: List[Notification], user: User
) -> None:
    """Listings lead with the most recent notification."""
    rows = await dal.sent(recipients=user, display_detail=True)

    assert [item.id for item in rows] == sorted(
        [item.id for item in notifications], reverse=True
    )


async def test_deleted_notifications_are_excluded_from_listings(
    dal: NotificationDataAccessLayer,
    notification: Notification,
    user: User,
    session: AsyncSession,
) -> None:
    """A cleared notification stops appearing for the user who cleared it."""
    session.add(
        DeletedNotification(
            notification_id=notification.id, user_id=str(user.id)
        )
    )
    await session.commit()

    assert len(await dal.sent(exclude_deleted_by=user, display_detail=True)) == 0


async def test_extra_conditions_narrow_a_listing(
    dal: NotificationDataAccessLayer, user: User, session: AsyncSession
) -> None:
    """Callers can pass their own conditions through to the statement."""
    await dal.create_notification(
        verb="urgent", actor=user, recipients=user, status="CRITICAL", is_sent=True
    )
    await dal.create_notification(
        verb="routine", actor=user, recipients=user, is_sent=True
    )
    await session.commit()

    rows = await dal.sent(
        recipients=user,
        display_detail=True,
        conditions=[Notification.status == "CRITICAL"],
    )

    assert [item.verb for item in rows] == ["urgent"]
