from typing import Any, List, Optional, Union

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

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
from fastapi_notification.identity import hydrate_notification_identities
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.queryset import notification as queryset


# pylint: disable=too-many-arguments,too-many-public-methods
class NotificationDataAccessLayer:
    """Data Access Layer (DAL) for managing notifications.

    Bound to a single :class:`AsyncSession`, this class provides methods for
    creating, updating, deleting and filtering notifications by recipient,
    group, status and visibility.

    Every read method has a ``*_statement`` counterpart that returns the
    underlying statement instead of executing it, which is what the API routes
    use so they can apply filtering, ordering and pagination first.

    Methods:
        create_notification: Creates a new notification with specific details.
        update_notification: Updates selective fields of an existing notification.
        delete_notification: Deletes or soft-deletes a notification.
        all_notifications: Retrieves every notification with optional filters.
        sent: Retrieves all sent notifications with optional filters.
        unsent: Retrieves all unsent notifications with optional filters.
        seen: Retrieves all notifications seen by a given user.
        unseen: Retrieves all notifications not seen by a given user.
        mark_all_as_sent: Marks all unsent notifications as sent.
        mark_all_as_seen: Marks all unseen notifications for a user as seen.
        deleted: Retrieves all deleted notifications, optionally filtered by user.
        clear_all: Clears all seen notifications for a user, marking them deleted.

    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.query_set = queryset.NotificationQuerySet()

    def get_queryset(self) -> queryset.NotificationQuerySet:
        """Return the statement builder backing this data access layer.

        Returns:
            NotificationQuerySet: The statement builder.

        """
        return self.query_set

    async def _execute(
        self, statement: Select, display_detail: bool
    ) -> Union[List[Notification], Rows]:
        """Run a statement and return its rows.

        Args:
            statement (Select): The statement to execute.
            display_detail (bool): Whether whole notifications were selected.

        Returns:
            Union[List[Notification], Rows]: The resulting rows.

        """
        rows = await queryset.fetch(self.session, statement, display_detail)
        if display_detail:
            await hydrate_notification_identities(self.session, rows)
        return rows

    # ------------------------------------------------------------------
    # Statement builders
    # ------------------------------------------------------------------

    def all_notifications_statement(
        self,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
    ) -> Select:
        """Build the statement returning every notification.

        Args:
            recipients (Recipients): The recipients of the notifications.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.

        Returns:
            Select: The statement.

        """
        return self.query_set.all_notifications(recipients, groups, display_detail)

    def sent_statement(
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build the statement returning sent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications deleted by
                this user.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Select: The statement.

        """
        return self.query_set.sent(
            recipients, exclude_deleted_by, groups, display_detail, conditions
        )

    def unsent_statement(
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build the statement returning unsent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications deleted by
                this user.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Select: The statement.

        """
        return self.query_set.unsent(
            recipients, exclude_deleted_by, groups, display_detail, conditions
        )

    def seen_statement(
        self,
        seen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build the statement returning notifications a user has seen.

        Args:
            seen_by (Any): The user who has seen the notifications.
            recipients (Recipients): The recipients of the notifications.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Select: The statement.

        """
        return self.query_set.seen(
            seen_by, recipients, groups, display_detail, conditions
        )

    def unseen_statement(
        self,
        unseen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Select:
        """Build the statement returning notifications a user has not seen.

        Args:
            unseen_by (Any): The user who has not seen the notifications.
            recipients (Recipients): The recipients of the notifications.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Select: The statement.

        """
        return self.query_set.unseen(
            unseen_by, recipients, groups, display_detail, conditions
        )

    def deleted_statement(
        self, deleted_by: Recipient = None, display_detail: bool = True
    ) -> Select:
        """Build the statement returning soft deleted notifications.

        Args:
            deleted_by (Recipient): Restrict to deletions by this user.
            display_detail (bool): Whether whole notifications are selected.

        Returns:
            Select: The statement.

        """
        return self.query_set.deleted(deleted_by, display_detail)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def all_notifications(
        self,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
    ) -> Union[List[Notification], Rows]:
        """Return every notification, whether sent, seen or soft deleted.

        This is the unfiltered view. Unlike :meth:`sent`, :meth:`unsent`,
        :meth:`seen` and :meth:`unseen`, it does not exclude notifications a
        user has cleared, so it reports what is actually stored.

        Args:
            recipients (Recipients): The recipients of the notifications.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are returned.

        Returns:
            Union[List[Notification], Rows]: The matching notifications.

        """
        return await self._execute(
            self.all_notifications_statement(recipients, groups, display_detail),
            display_detail,
        )

    async def sent(
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Union[List[Notification], Rows]:
        """Return all sent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications deleted by
                this user.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are returned.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Union[List[Notification], Rows]: The matching notifications.

        """
        return await self._execute(
            self.sent_statement(
                recipients, exclude_deleted_by, groups, display_detail, conditions
            ),
            display_detail,
        )

    async def unsent(
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Union[List[Notification], Rows]:
        """Return all unsent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications deleted by
                this user.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are returned.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Union[List[Notification], Rows]: The matching notifications.

        """
        return await self._execute(
            self.unsent_statement(
                recipients, exclude_deleted_by, groups, display_detail, conditions
            ),
            display_detail,
        )

    async def seen(
        self,
        seen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Union[List[Notification], Rows]:
        """Return all notifications the given user has seen.

        Args:
            seen_by (Any): The user who has seen the notifications.
            recipients (Recipients): The recipients of the notifications.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are returned.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Union[List[Notification], Rows]: The matching notifications.

        """
        return await self._execute(
            self.seen_statement(
                seen_by, recipients, groups, display_detail, conditions
            ),
            display_detail,
        )

    async def unseen(
        self,
        unseen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Union[List[Notification], Rows]:
        """Return all notifications the given user has not seen.

        Args:
            unseen_by (Any): The user who has not seen the notifications.
            recipients (Recipients): The recipients of the notifications.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are returned.
            conditions (OptConditions): Extra conditions to apply.

        Returns:
            Union[List[Notification], Rows]: The matching notifications.

        """
        return await self._execute(
            self.unseen_statement(
                unseen_by, recipients, groups, display_detail, conditions
            ),
            display_detail,
        )

    async def deleted(
        self, deleted_by: Recipient = None, display_detail: bool = True
    ) -> Union[List[Notification], Rows]:
        """Return all notifications that have been soft deleted.

        Args:
            deleted_by (Recipient): Restrict to deletions by this user.
            display_detail (bool): Whether whole notifications are returned.

        Returns:
            Union[List[Notification], Rows]: The matching notifications.

        """
        return await self._execute(
            self.deleted_statement(deleted_by, display_detail), display_detail
        )

    async def get(
        self, statement: Select, notification_id: int
    ) -> Optional[Notification]:
        """Return a single notification visible through a statement.

        Args:
            statement (Select): A statement selecting whole notifications.
            notification_id (int): The ID of the notification.

        Returns:
            Optional[Notification]: The notification, or ``None``.

        """
        notification = await queryset.get_notification(
            self.session, statement, notification_id
        )
        if notification is not None:
            await hydrate_notification_identities(self.session, [notification])
        return notification

    async def count(self, statement: Select) -> int:
        """Return how many rows a statement would produce.

        Args:
            statement (Select): The statement to count.

        Returns:
            int: The number of matching rows.

        """
        return await queryset.count(self.session, statement)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create_notification(
        self,
        verb: str,
        actor: Actor,
        description: Optional[Description] = None,
        recipients: Optional[Recipients] = None,
        groups: Optional[Groups] = None,
        status: str = "INFO",
        public: bool = True,
        target: Optional[Target] = None,
        action_object: Optional[ActionObject] = None,
        link: Optional[Link] = None,
        is_sent: bool = False,
        data: Optional[Data] = None,
    ) -> Notification:
        """Create a new notification with the provided details.

        Args:
            verb (str): A short phrase describing the action (e.g. "commented on").
            actor (Actor): The user or entity performing the action.
            description (Optional[Description]): Additional context. Generated
                from the actor, verb and target when omitted.
            recipients (Optional[Recipients]): Users who will receive it.
            groups (Optional[Groups]): Groups to target.
            status (str): The status of the notification. Defaults to "INFO".
            public (bool): Whether it is publicly visible. Defaults to True.
            target (Optional[Target]): The object being acted upon.
            action_object (Optional[ActionObject]): The object used to act.
            link (Optional[Link]): A URL associated with the notification.
            is_sent (bool): Whether it is marked as sent. Defaults to False.
            data (Optional[Data]): Any additional JSON data.

        Returns:
            Notification: The created notification instance.

        """
        notification = await queryset.create_notification(
            self.session,
            verb=verb,
            actor=actor,
            description=description,
            status=status,
            public=public,
            target=target,
            action_object=action_object,
            link=link,
            is_sent=is_sent,
            data=data,
        )

        if recipients:
            await queryset.add_recipients(self.session, notification, recipients)

        if groups:
            await queryset.add_groups(self.session, notification, groups)

        return notification

    async def update_notification(
        self,
        notification_id: int,
        is_sent: Optional[bool] = None,
        public: Optional[bool] = None,
        data: Optional[Data] = None,
    ) -> Notification:
        """Update specified fields of an existing notification.

        Args:
            notification_id (int): The ID of the notification to update.
            is_sent (Optional[bool]): The sent status to update.
            public (Optional[bool]): The public visibility to update.
            data (Optional[Data]): Any additional data to update.

        Returns:
            Notification: The updated notification instance.

        """
        return await queryset.update_notification(
            self.session, notification_id, is_sent, public, data
        )

    async def delete_notification(
        self,
        notification_id: int,
        recipient: Optional[Recipient] = None,
        soft_delete: bool = True,
    ) -> None:
        """Delete, or soft delete, the notification with the given ID.

        Args:
            notification_id (int): The ID of the notification to delete.
            recipient (Optional[Recipient]): The user performing the soft
                delete. Required for soft deletes.
            soft_delete (bool): Whether to perform a soft delete. Defaults to
                True.

        """
        await queryset.delete_notification(
            self.session, notification_id, recipient, soft_delete
        )

    async def delete_many(self, statement: Select) -> int:
        """Permanently delete every notification matched by a statement.

        Args:
            statement (Select): A statement selecting whole notifications.

        Returns:
            int: The number of notifications deleted.

        """
        return await queryset.delete_many(self.session, statement)

    async def mark_all_as_sent(
        self,
        recipients: Optional[Recipients] = None,
        groups: Optional[Groups] = None,
    ) -> int:
        """Mark all matching unsent notifications as sent.

        Args:
            recipients (Optional[Recipients]): Recipients to filter by.
            groups (Optional[Groups]): Groups to filter by.

        Returns:
            int: The number of notifications marked as sent.

        """
        return await queryset.mark_all_as_sent(self.session, recipients, groups)

    async def mark_all_as_seen(self, user: Any) -> int:
        """Mark all unseen direct and group notifications for a user as seen.

        Args:
            user (Any): The user to mark notifications as seen for.

        Returns:
            int: The number of notifications marked as seen.

        """
        return await queryset.mark_all_as_seen(self.session, user)

    async def clear_all(self, user: Any) -> None:
        """Soft-delete every seen notification addressed to a user or their groups.

        Args:
            user (Any): The user whose notifications should be cleared.

        """
        await queryset.clear_all(self.session, user)
