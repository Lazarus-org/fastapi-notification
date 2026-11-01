from typing import Any, Dict, List, Optional, Sequence, Union

from sqlalchemy import (
    ColumnElement,
    Select,
    delete,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.constants.default_settings import default_serializer_settings
from fastapi_notification.constants.qs_types import (
    ActionObject,
    Actor,
    Data,
    Description,
    Groups,
    Link,
    OptConditions,
    Recipient,
    Recipients,
    Rows,
    Target,
)
from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.models.content_type import (
    ContentType,
    normalize_object_id,
)
from fastapi_notification.models.deleted_notification import DeletedNotification
from fastapi_notification.models.notification import Notification, notification_group
from fastapi_notification.models.notification_recipient import NotificationRecipient
from fastapi_notification.models.notification_seen import NotificationSeen


def _as_sequence(value: Any) -> Sequence[Any]:
    """Normalize one identity or a collection of identities."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or hasattr(value, "id"):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    try:
        return list(value)
    except TypeError:
        return [value]


def _ids(value: Any, identity_type: str = "user") -> List[str]:
    """Extract normalized user or group identifiers through the adapter."""
    adapter = get_identity_adapter()
    getter = adapter.get_user_id if identity_type == "user" else adapter.get_group_id
    return [getter(item) for item in _as_sequence(value)]


# pylint: disable=too-many-arguments
class NotificationQuerySet:
    """Builds the SELECT statements behind every notification query.

    Statements are built rather than executed so the API layer can layer
    filtering, searching, ordering and pagination on top before running them,
    which is the role Django's lazy ``QuerySet`` played in the original package.

    """

    #: Membership conditions are expressed as subqueries rather than joins, so a
    #: notification is never returned twice and no DISTINCT is required.
    def recipient_condition(self, recipients: Any) -> ColumnElement[bool]:
        """Build the condition matching notifications sent to given recipients.

        Args:
            recipients (Any): One or more users.

        Returns:
            ColumnElement[bool]: The membership condition.

        """
        return Notification.id.in_(
            select(NotificationRecipient.notification_id).where(
                NotificationRecipient.recipient_id.in_(_ids(recipients, "user"))
            )
        )

    def group_condition(self, groups: Any) -> ColumnElement[bool]:
        """Build the condition matching notifications sent to given groups.

        Args:
            groups (Any): One or more groups.

        Returns:
            ColumnElement[bool]: The membership condition.

        """
        return Notification.id.in_(
            select(notification_group.c.notification_id).where(
                notification_group.c.group_id.in_(_ids(groups, "group"))
            )
        )

    def seen_condition(self, user: Any) -> ColumnElement[bool]:
        """Build the condition matching notifications seen by a user.

        Args:
            user (Any): The user who has seen the notifications.

        Returns:
            ColumnElement[bool]: The membership condition.

        """
        return Notification.id.in_(
            select(NotificationSeen.notification_id).where(
                NotificationSeen.user_id == get_identity_adapter().get_user_id(user)
            )
        )

    def deleted_condition(self, deleted_by: Recipient = None) -> ColumnElement[bool]:
        """Build the condition matching soft deleted notifications.

        Args:
            deleted_by (Recipient): Restrict to deletions by this user, when
                given.

        Returns:
            ColumnElement[bool]: The membership condition.

        """
        subquery = select(DeletedNotification.notification_id)
        if deleted_by is not None:
            subquery = subquery.where(
                DeletedNotification.user_id
                == get_identity_adapter().get_user_id(deleted_by)
            )
        return Notification.id.in_(subquery)

    def _notifications_statement(
        self,
        exclude_deleted_by: Recipient = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build the base statement shared by every notification query.

        Excludes notifications the given user has soft deleted, and selects
        either whole notifications or just the default summary columns.

        Args:
            exclude_deleted_by (Recipient): Exclude notifications this user has
                deleted.
            display_detail (bool): Whether to select whole notifications rather
                than the default summary columns.
            conditions (OptConditions): Conditions to apply to the statement.

        Returns:
            Select: The statement, ordered newest first.

        """
        if display_detail:
            statement = select(Notification)
        else:
            statement = select(
                *(
                    getattr(Notification, field)
                    for field in (
                        default_serializer_settings.notification_serializer_fields or []
                    )
                )
            )

        if exclude_deleted_by is not None:
            statement = statement.where(
                ~self.deleted_condition(deleted_by=exclude_deleted_by)
            )

        for condition in conditions or []:
            statement = statement.where(condition)

        return statement.order_by(Notification.timestamp.desc())

    def all_notifications(
        self,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
    ) -> Select:
        """Build a statement returning every notification.

        This is the unfiltered view: soft deleted notifications are included,
        since no viewer is given to exclude them for.

        Args:
            recipients (Recipients): The recipients of the notifications.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.

        Returns:
            Select: The statement.

        """
        conditions: List[ColumnElement[bool]] = []
        if recipients:
            conditions.append(self.recipient_condition(recipients))
        if groups:
            conditions.append(self.group_condition(groups))

        return self._notifications_statement(
            display_detail=display_detail, conditions=conditions
        )

    def _sent_statement(
        self,
        is_sent: bool,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build a statement for notifications in a given delivery state.

        The audience conditions are combined with OR: a notification matches if
        it was addressed to any of the given recipients or any of the given
        groups. When ``exclude_deleted_by`` is supplied without an explicit
        recipient filter, the query is narrowed to that user's direct audience
        regardless of staff or superuser status.

        Args:
            is_sent (bool): The delivery state to match.
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications this user has
                deleted, and narrow to their own direct audience when no explicit
                recipient filter is supplied. This applies to every role.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Select: The statement.

        """
        all_conditions: List[ColumnElement[bool]] = list(conditions or [])
        all_conditions.append(Notification.is_sent.is_(is_sent))

        audience: List[ColumnElement[bool]] = []
        if recipients:
            audience.append(self.recipient_condition(recipients))
        elif exclude_deleted_by is not None:
            audience.append(self.recipient_condition(exclude_deleted_by))

        if groups:
            audience.append(self.group_condition(groups))

        if audience:
            all_conditions.append(or_(*audience))

        return self._notifications_statement(
            exclude_deleted_by=exclude_deleted_by,
            display_detail=display_detail,
            conditions=all_conditions,
        )

    def sent(
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build a statement returning sent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications this user has
                deleted.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Select: The statement.

        """
        return self._sent_statement(
            True, recipients, exclude_deleted_by, groups, display_detail, conditions
        )

    def unsent(
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build a statement returning unsent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications this user has
                deleted.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Select: The statement.

        """
        return self._sent_statement(
            False, recipients, exclude_deleted_by, groups, display_detail, conditions
        )

    def seen(
        self,
        seen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build a statement returning notifications a user has seen.

        Args:
            seen_by (Any): The user who has seen the notifications.
            recipients (Recipients): The recipients of the notifications.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Select: The statement.

        """
        all_conditions = list(conditions or [])
        all_conditions.append(self.seen_condition(seen_by))

        return self.sent(
            recipients=recipients,
            exclude_deleted_by=seen_by,
            groups=groups,
            display_detail=display_detail,
            conditions=all_conditions,
        )

    def unseen(
        self,
        unseen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build a statement returning notifications a user has not seen.

        Args:
            unseen_by (Any): The user who has not seen the notifications.
            recipients (Recipients): The recipients of the notifications.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Select: The statement.

        """
        all_conditions = list(conditions or [])
        all_conditions.append(~self.seen_condition(unseen_by))

        return self.sent(
            recipients=recipients,
            exclude_deleted_by=unseen_by,
            groups=groups,
            display_detail=display_detail,
            conditions=all_conditions,
        )

    def deleted(
        self, deleted_by: Recipient = None, display_detail: bool = True
    ) -> Select:
        """Build a statement returning soft deleted notifications.

        Args:
            deleted_by (Recipient): Restrict to deletions by this user.
            display_detail (bool): Whether whole notifications are selected.

        Returns:
            Select: The statement.

        """
        return self._notifications_statement(
            display_detail=display_detail,
            conditions=[self.deleted_condition(deleted_by=deleted_by)],
        )


async def fetch(
    session: AsyncSession, statement: Select, display_detail: bool = False
) -> Union[List[Notification], Rows]:
    """Execute a statement built by the query set and return its rows.

    Args:
        session (AsyncSession): The session used to read.
        statement (Select): The statement to execute.
        display_detail (bool): Whether the statement selects whole
            notifications rather than summary columns.

    Returns:
        Union[List[Notification], Rows]: Notification instances when detailed,
        otherwise a list of dictionaries.

    """
    result = await session.execute(statement)

    if display_detail:
        return list(result.scalars().unique().all())

    return [dict(row) for row in result.mappings().all()]


async def count(session: AsyncSession, statement: Select) -> int:
    """Return how many rows a statement would produce.

    Args:
        session (AsyncSession): The session used to read.
        statement (Select): The statement to count.

    Returns:
        int: The number of matching rows.

    """
    subquery = statement.order_by(None).subquery()
    result = await session.execute(select(func.count()).select_from(subquery))
    return int(result.scalar_one())


# pylint: disable=too-many-arguments,too-many-locals
async def create_notification(
    session: AsyncSession,
    verb: str,
    actor: Actor,
    description: Description = None,
    status: str = "INFO",
    public: bool = True,
    target: Target = None,
    action_object: ActionObject = None,
    link: Link = None,
    is_sent: bool = False,
    data: Data = None,
) -> Notification:
    """Create a notification, resolving its generic relations.

    When no description is supplied one is generated from the actor, verb and
    the target or action object, mirroring the original package.

    Args:
        session (AsyncSession): The session used to write.
        verb (str): The verb of the notification.
        actor (Actor): The actor of the notification.
        description (Description): The description of the notification.
        status (str): The status of the notification. Defaults to ``"INFO"``.
        public (bool): The public status of the notification. Defaults to True.
        target (Target): The target of the notification.
        action_object (ActionObject): The action object of the notification.
        link (Link): The link of the notification.
        is_sent (bool): The send status of the notification. Defaults to False.
        data (Data): Arbitrary JSON data for the notification.

    Returns:
        Notification: The created notification.

    """
    actor_content_type = await ContentType.get_for_model(session, type(actor))

    target_content_type = (
        await ContentType.get_for_model(session, type(target))
        if target is not None
        else None
    )
    action_object_content_type = (
        await ContentType.get_for_model(session, type(action_object))
        if action_object is not None
        else None
    )

    notification = Notification(
        verb=verb,
        description=description,
        status=status,
        public=public,
        link=link,
        is_sent=is_sent,
        data=data,
        actor_content_type_id=actor_content_type.id,
        actor_object_id=normalize_object_id(actor.id),
        target_content_type_id=(
            target_content_type.id if target_content_type else None
        ),
        target_object_id=(
            normalize_object_id(target.id) if target is not None else None
        ),
        action_object_content_type_id=(
            action_object_content_type.id if action_object_content_type else None
        ),
        action_object_object_id=(
            normalize_object_id(action_object.id)
            if action_object is not None
            else None
        ),
    )

    notification.actor = actor
    notification.target = target
    notification.action_object = action_object

    if not notification.description:
        notification.description = notification.title_generator()

    session.add(notification)
    await session.flush()

    return notification


async def update_notification(
    session: AsyncSession,
    notification_id: int,
    is_sent: Optional[bool] = None,
    public: Optional[bool] = None,
    data: Data = None,
) -> Notification:
    """Update the given fields of a notification, leaving the rest untouched.

    Args:
        session (AsyncSession): The session used to write.
        notification_id (int): The ID of the notification.
        is_sent (Optional[bool]): The send status. Left alone when ``None``.
        public (Optional[bool]): The public status. Left alone when ``None``.
        data (Data): The notification data. Left alone when ``None``.

    Returns:
        Notification: The updated notification.

    Raises:
        LookupError: If no notification has the given ID.

    """
    notification = await session.get(Notification, notification_id)
    if notification is None:
        raise LookupError(f"No notification found with id {notification_id}.")

    if is_sent is not None:
        notification.is_sent = is_sent
    if public is not None:
        notification.public = public
    if data is not None:
        notification.data = data

    await session.flush()
    return notification


async def delete_notification(
    session: AsyncSession,
    notification_id: int,
    recipient: Recipient = None,
    soft_delete: bool = True,
) -> None:
    """Delete a notification, either softly or permanently.

    A soft delete records the deletion against the recipient and leaves the
    notification in place for everyone else; a hard delete removes the row.

    Args:
        session (AsyncSession): The session used to write.
        notification_id (int): The ID of the notification.
        recipient (Recipient): The recipient performing the deletion.
        soft_delete (bool): Whether to soft delete. Defaults to True.

    Raises:
        ValueError: If a soft delete is requested without a recipient.
        LookupError: If the notification does not exist or is not visible to
            the recipient.

    """
    if soft_delete and recipient is None:
        raise ValueError("the recipient most be given if it is soft delete")

    query_set = NotificationQuerySet()

    if recipient is None:
        statement = query_set.sent(display_detail=True)
    else:
        group_ids = await get_identity_adapter().get_user_group_ids(session, recipient)
        statement = query_set.sent(
            recipients=recipient,
            exclude_deleted_by=recipient,
            groups=group_ids,
            display_detail=True,
        )

    result = await session.execute(
        statement.where(Notification.id == notification_id)
    )
    instance = result.scalars().unique().one_or_none()

    if instance is None:
        raise LookupError(f"No notification found with id {notification_id}.")

    if soft_delete:
        await DeletedNotification.create(session, instance, recipient)
        return

    await session.delete(instance)
    await session.flush()


async def mark_all_as_seen(session: AsyncSession, user: Any) -> int:
    """Mark every notification a user has not seen as seen.

    Args:
        session (AsyncSession): The session used to write.
        user (Any): The user to mark notifications as seen for.

    Returns:
        int: The number of notifications marked as seen, including notifications
            addressed to groups the user belongs to.

    """
    group_ids = await get_identity_adapter().get_user_group_ids(session, user)
    statement = NotificationQuerySet().unseen(
        unseen_by=user,
        groups=group_ids,
        display_detail=True,
    )
    notifications = await fetch(session, statement, display_detail=True)

    session.add_all(
        [
            NotificationSeen(
                notification_id=notification.id,
                user_id=get_identity_adapter().get_user_id(user),
            )
            for notification in notifications
        ]
    )
    await session.flush()

    return len(notifications)


async def mark_all_as_sent(
    session: AsyncSession,
    recipients: Recipients = None,
    groups: Groups = None,
) -> int:
    """Mark every matching unsent notification as sent.

    Args:
        session (AsyncSession): The session used to write.
        recipients (Recipients): Filter notifications by recipients.
        groups (Groups): Filter notifications by groups.

    Returns:
        int: The number of notifications marked as sent.

    """
    statement = NotificationQuerySet().unsent(
        recipients=recipients, groups=groups, display_detail=True
    )
    notifications = await fetch(session, statement, display_detail=True)
    identifiers = [notification.id for notification in notifications]

    if not identifiers:
        return 0

    await session.execute(
        update(Notification)
        .where(Notification.id.in_(identifiers))
        .values(is_sent=True)
    )
    await session.flush()

    return len(identifiers)


async def clear_all(session: AsyncSession, user: Any) -> None:
    """Soft-delete every notification a user has already seen.

    Notifications addressed directly to the user and to their groups are both
    included.

    Args:
        session (AsyncSession): The session used to write.
        user (Any): The user whose notifications should be cleared.

    """
    group_ids = await get_identity_adapter().get_user_group_ids(session, user)
    statement = NotificationQuerySet().seen(
        seen_by=user,
        groups=group_ids,
        display_detail=True,
    )
    notifications = await fetch(session, statement, display_detail=True)

    session.add_all(
        [
            DeletedNotification(
                notification_id=notification.id,
                user_id=get_identity_adapter().get_user_id(user),
            )
            for notification in notifications
        ]
    )
    await session.flush()


async def delete_many(session: AsyncSession, statement: Select) -> int:
    """Permanently delete every notification matched by a statement.

    Args:
        session (AsyncSession): The session used to write.
        statement (Select): A statement selecting whole notifications.

    Returns:
        int: The number of notifications deleted.

    """
    notifications = await fetch(session, statement, display_detail=True)
    identifiers = [notification.id for notification in notifications]

    if not identifiers:
        return 0

    await session.execute(
        delete(Notification).where(Notification.id.in_(identifiers))
    )
    await session.flush()

    return len(identifiers)


async def add_recipients(
    session: AsyncSession, notification: Notification, recipients: Recipients
) -> None:
    """Address an existing notification to further recipients.

    Args:
        session (AsyncSession): The session used to write.
        notification (Notification): The notification to address.
        recipients (Recipients): The users to address it to.

    """
    recipient_objects = list(_as_sequence(recipients))
    notification.recipient = list(notification.recipient) + recipient_objects
    session.add_all(
        [
            NotificationRecipient(
                notification_id=notification.id, recipient_id=recipient_id
            )
            for recipient_id in _ids(recipients, "user")
        ]
    )
    await session.flush()


async def add_groups(
    session: AsyncSession, notification: Notification, groups: Groups
) -> None:
    """Address an existing notification to further groups.

    The association rows are inserted directly rather than by appending to the
    relationship, which would require the collection to be loaded first.

    Args:
        session (AsyncSession): The session used to write.
        notification (Notification): The notification to address.
        groups (Groups): The groups to address it to.

    """
    group_objects = list(_as_sequence(groups))
    notification.group = list(notification.group) + group_objects
    group_ids = _ids(groups, "group")
    if not group_ids:
        return

    await session.execute(
        insert(notification_group),
        [
            {"notification_id": notification.id, "group_id": group_id}
            for group_id in group_ids
        ],
    )
    await session.flush()


async def get_notification(
    session: AsyncSession, statement: Select, notification_id: int
) -> Optional[Notification]:
    """Fetch a single notification matched by a statement.

    Args:
        session (AsyncSession): The session used to read.
        statement (Select): A statement selecting whole notifications.
        notification_id (int): The ID of the notification to fetch.

    Returns:
        Optional[Notification]: The notification, or ``None`` when it is not
        visible through the statement.

    """
    result = await session.execute(
        statement.where(Notification.id == notification_id)
    )
    return result.scalars().unique().one_or_none()


__all__ = [
    "NotificationQuerySet",
    "add_groups",
    "add_recipients",
    "clear_all",
    "count",
    "create_notification",
    "delete_many",
    "delete_notification",
    "fetch",
    "get_notification",
    "mark_all_as_seen",
    "mark_all_as_sent",
    "update_notification",
]
