"""Typed notification reads and statement builders shared by the public DAL."""

from typing import Any, Dict, List, Literal, Optional, Union, overload

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.constants.qs_types import (
    Groups,
    OptConditions,
    Recipient,
    Recipients,
    Rows,
)
from fastapi_notification.identity import hydrate_notification_identities
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.queryset import notification as queryset


class NotificationReadOperations:
    """Read operations on the caller-owned async session and statement builder."""

    session: AsyncSession
    query_set: queryset.NotificationQuerySet

    def get_queryset(self) -> queryset.NotificationQuerySet:
        """Return the statement builder backing this data access layer.

        Returns:
            NotificationQuerySet: The statement builder.
        """
        return self.query_set

    @overload
    async def _execute(
        self, statement: Select, display_detail: Literal[False]
    ) -> Rows: ...

    @overload
    async def _execute(
        self, statement: Select, display_detail: Literal[True]
    ) -> List[Notification]: ...

    @overload
    async def _execute(
        self, statement: Select, display_detail: bool
    ) -> Union[List[Notification], Rows]: ...

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

    def sent_statement(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> Select:
        """Build the statement returning sent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications deleted by
                this user.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.
            include_expired (bool): Include expired rows for historical queries.

        Returns:
            Select: The statement.
        """
        return self.query_set.sent(
            recipients,
            exclude_deleted_by,
            groups,
            display_detail,
            conditions,
            include_expired,
        )

    def unsent_statement(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> Select:
        """Build the statement returning unsent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications deleted by
                this user.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are selected.
            conditions (OptConditions): Extra conditions to apply.
            include_expired (bool): Include expired rows for historical queries.

        Returns:
            Select: The statement.
        """
        return self.query_set.unsent(
            recipients,
            exclude_deleted_by,
            groups,
            display_detail,
            conditions,
            include_expired,
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

    @overload
    async def all_notifications(
        self,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: Literal[False] = False,
    ) -> Rows: ...

    @overload
    async def all_notifications(
        self,
        recipients: Recipients = None,
        groups: Groups = None,
        *,
        display_detail: Literal[True],
    ) -> List[Notification]: ...

    @overload
    async def all_notifications(
        self,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
    ) -> Union[List[Notification], Rows]: ...

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

    @overload
    async def sent(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: Literal[False] = False,
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> Rows: ...

    @overload
    async def sent(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        *,
        display_detail: Literal[True],
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> List[Notification]: ...

    @overload
    async def sent(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> Union[List[Notification], Rows]: ...

    async def sent(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> Union[List[Notification], Rows]:
        """Return all sent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications deleted by
                this user.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are returned.
            conditions (OptConditions): Extra conditions to apply.
            include_expired (bool): Include expired rows for historical inspection.

        Returns:
            Union[List[Notification], Rows]: The matching notifications.
        """
        return await self._execute(
            self.sent_statement(
                recipients,
                exclude_deleted_by,
                groups,
                display_detail,
                conditions,
                include_expired,
            ),
            display_detail,
        )

    @overload
    async def unsent(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: Literal[False] = False,
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> Rows: ...

    @overload
    async def unsent(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        *,
        display_detail: Literal[True],
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> List[Notification]: ...

    @overload
    async def unsent(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> Union[List[Notification], Rows]: ...

    async def unsent(  # pylint: disable=too-many-arguments
        self,
        recipients: Recipients = None,
        exclude_deleted_by: Recipient = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
        include_expired: bool = False,
    ) -> Union[List[Notification], Rows]:
        """Return all unsent notifications.

        Args:
            recipients (Recipients): The recipients of the notifications.
            exclude_deleted_by (Recipient): Exclude notifications deleted by
                this user.
            groups (Groups): The groups of the notifications.
            display_detail (bool): Whether whole notifications are returned.
            conditions (OptConditions): Extra conditions to apply.
            include_expired (bool): Include expired rows for historical inspection.

        Returns:
            Union[List[Notification], Rows]: The matching notifications.
        """
        return await self._execute(
            self.unsent_statement(
                recipients,
                exclude_deleted_by,
                groups,
                display_detail,
                conditions,
                include_expired,
            ),
            display_detail,
        )

    @overload
    async def seen(
        self,
        seen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: Literal[False] = False,
        conditions: OptConditions = None,
    ) -> Rows: ...

    @overload
    async def seen(
        self,
        seen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        *,
        display_detail: Literal[True],
        conditions: OptConditions = None,
    ) -> List[Notification]: ...

    @overload
    async def seen(
        self,
        seen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Union[List[Notification], Rows]: ...

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

    @overload
    async def unseen(
        self,
        unseen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: Literal[False] = False,
        conditions: OptConditions = None,
    ) -> Rows: ...

    @overload
    async def unseen(
        self,
        unseen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        *,
        display_detail: Literal[True],
        conditions: OptConditions = None,
    ) -> List[Notification]: ...

    @overload
    async def unseen(
        self,
        unseen_by: Any,
        recipients: Recipients = None,
        groups: Groups = None,
        display_detail: bool = False,
        conditions: OptConditions = None,
    ) -> Union[List[Notification], Rows]: ...

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

    @overload
    async def deleted(
        self, deleted_by: Recipient = None, display_detail: Literal[True] = True
    ) -> List[Notification]: ...

    @overload
    async def deleted(
        self, deleted_by: Recipient = None, *, display_detail: Literal[False]
    ) -> Rows: ...

    @overload
    async def deleted(
        self, deleted_by: Recipient = None, display_detail: bool = True
    ) -> Union[List[Notification], Rows]: ...

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

    async def summary(self, statement: Select, user: Any) -> Dict[str, Any]:
        """Return total/read counts and category/priority breakdowns.

        The statement is expected to be restricted to the authenticated user's
        sent audience and to exclude notifications that user has cleared. The
        aggregate is executed as one SQL query and does not load notification
        ORM objects.

        Args:
            statement (Select): The scoped statement, including optional filters.
            user (Any): The identity whose read state is summarized.

        Returns:
            Dict[str, Any]: Total/read counts plus grouped category and priority
                breakdowns. Each breakdown contains total, unread and read.
        """
        aggregate = self.query_set.summary_statement(statement, user)
        result = await self.session.execute(aggregate)
        summary: Dict[str, Any] = {
            "total": 0,
            "unread": 0,
            "read": 0,
            "by_category": {},
            "by_priority": {},
        }
        for row in result.mappings().all():
            category = row["category"]
            priority = row["priority"]
            is_seen = bool(row["is_seen"])
            count = int(row["count"] or 0)
            state_key = "read" if is_seen else "unread"

            summary["total"] += count
            summary[state_key] += count

            for dimension, value in (
                ("by_category", category),
                ("by_priority", priority),
            ):
                breakdown = summary[dimension].setdefault(
                    value, {"total": 0, "unread": 0, "read": 0}
                )
                breakdown["total"] += count
                breakdown[state_key] += count

        return summary

    async def preview(
        self, statement: Select, user: Any, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Return bounded recent notification fields and their read state.

        The query selects only the columns required by the preview response; it
        does not instantiate ORM objects or hydrate generic relations.

        Args:
            statement (Select): The scoped statement, including optional filters.
            user (Any): The identity whose read state is included.
            limit (int): Maximum number of records to return.

        Returns:
            List[Dict[str, Any]]: Preview rows including the ``is_seen`` flag.
        """
        preview_statement = self.query_set.preview_statement(statement, user, limit)
        result = await self.session.execute(preview_statement)
        return [dict(row) for row in result.mappings().all()]

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
