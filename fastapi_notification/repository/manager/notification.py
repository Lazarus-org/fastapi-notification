from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, Union, overload

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
from fastapi_notification.identity import (
    get_identity_adapter,
    hydrate_notification_identities,
    require_staff_identity,
)
from fastapi_notification.models.helper.enums import (
    normalize_category,
    normalize_priority,
)
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.manager.read import NotificationReadOperations
from fastapi_notification.repository.queryset import notification as queryset
from fastapi_notification.repository.queryset.deduplication import (
    claim_deduplication_key,
)


# pylint: disable=too-many-arguments,too-many-public-methods
def _validate_deduplication(
    deduplication_key: Optional[str],
    deduplication_scope: str,
    deduplication_key_expires_at: Optional[datetime],
) -> Optional[datetime]:
    """Validate a scoped event key and normalize its optional retention deadline."""
    if deduplication_key is not None:
        if not isinstance(deduplication_key, str):
            raise TypeError("deduplication_key must be a string or None.")
        if (
            not deduplication_key.strip()
            or len(deduplication_key) > 255
            or "\x00" in deduplication_key
        ):
            raise ValueError(
                "deduplication_key must contain 1 to 255 non-NUL characters."
            )
        if not isinstance(deduplication_scope, str):
            raise TypeError("deduplication_scope must be a string.")
        if (
            not deduplication_scope.strip()
            or len(deduplication_scope) > 255
            or "\x00" in deduplication_scope
        ):
            raise ValueError(
                "deduplication_scope must contain 1 to 255 non-NUL characters."
            )
        if deduplication_key_expires_at is not None:
            if not isinstance(deduplication_key_expires_at, datetime):
                raise TypeError(
                    "deduplication_key_expires_at must be a datetime or None."
                )
            if (
                deduplication_key_expires_at.tzinfo is None
                or deduplication_key_expires_at.utcoffset() is None
            ):
                raise ValueError("deduplication_key_expires_at must be timezone-aware.")
            deduplication_key_expires_at = deduplication_key_expires_at.astimezone(
                timezone.utc
            )
            if deduplication_key_expires_at <= datetime.now(timezone.utc):
                raise ValueError("deduplication_key_expires_at must be in the future.")
    elif deduplication_key_expires_at is not None:
        raise ValueError("deduplication_key_expires_at requires deduplication_key.")

    return deduplication_key_expires_at


class NotificationDataAccessLayer(NotificationReadOperations):
    """Data Access Layer (DAL) for managing notifications.

    Bound to a single :class:`AsyncSession`, this class provides methods for
    creating, updating, deleting and filtering notifications by recipient,
    group, status, category, priority and visibility.

    Every read method has a ``*_statement`` counterpart that returns the
    underlying statement instead of executing it, which is what the API routes
    use so they can apply filtering, ordering and pagination first.

    Methods:
        create_notification: Creates or reuses a notification for a scoped event key.
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
        summary: Returns aggregate total, unread and read notification counts.
        preview: Returns a bounded set of recent notifications with read state.
        purge_expired: Explicitly removes expired notifications after retention.
        clear_all: Clears all seen notifications for a user, marking them deleted.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.query_set = queryset.NotificationQuerySet()

    async def _snapshot_audience(
        self, recipients: Recipients, groups: Groups, group_audience_strategy: str
    ) -> Tuple[Recipients, Groups]:
        """Resolve a snapshot once, preserving dynamic audiences unchanged."""
        if group_audience_strategy not in {"dynamic", "snapshot"}:
            raise ValueError("group_audience_strategy must be 'dynamic' or 'snapshot'.")

        if group_audience_strategy == "snapshot" and groups:
            adapter = get_identity_adapter()
            group_items = (
                list(groups) if isinstance(groups, (list, tuple, set)) else [groups]
            )
            snapshot_members: List[object] = []
            for group in group_items:
                snapshot_members.extend(
                    await adapter.get_group_user_ids(self.session, group)
                )
            # Persist a frozen audience as individual recipient associations.
            existing_recipients = (
                list(recipients)
                if isinstance(recipients, (list, tuple, set))
                else ([recipients] if recipients is not None else [])
            )
            recipients = list(
                {
                    adapter.get_user_id(member): member
                    for member in existing_recipients + snapshot_members
                }.values()
            )
            groups = None

        return recipients, groups

    # Existing positional API remains backward compatible; complex work is delegated.
    async def create_notification(  # pylint: disable=too-many-positional-arguments,too-many-locals
        self,
        verb: Optional[str] = None,
        actor: Actor = None,
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
        expires_at: Optional[datetime] = None,
        deduplication_key: Optional[str] = None,
        deduplication_scope: str = "global",
        deduplication_key_expires_at: Optional[datetime] = None,
        category: Optional[str] = None,
        priority: str = "normal",
        group_audience_strategy: str = "dynamic",
        template_key: Optional[str] = None,
        locale: str = "en",
        template_context: Optional[Dict[str, Any]] = None,
        default_locale: str = "en",
    ) -> Notification:
        """Create a notification, optionally deduplicating a business event.

        An active ``(deduplication_scope, deduplication_key)`` pair is
        idempotent: a retry returns the original notification unchanged. It
        does not merge new recipients or overwrite the original content. When
        the key expiry is reached, a new notification may claim the key; the
        previous notification remains unchanged.

        Args:
            verb (Optional[str]): A short phrase describing the action when no
                template is used. May be omitted when ``template_key`` is supplied.
            actor (Actor): The user or entity performing the action.
            description (Optional[Description]): Additional context.
            recipients (Optional[Recipients]): Users who will receive it.
            groups (Optional[Groups]): Groups to target.
            status (str): The notification status. Defaults to ``"INFO"``.
            public (bool): Whether it is publicly visible.
            target (Optional[Target]): The object being acted upon.
            action_object (Optional[ActionObject]): The object used to act.
            link (Optional[Link]): A URL associated with the action.
            is_sent (bool): Whether the notification is marked as sent.
            data (Optional[Data]): Additional JSON data.
            expires_at (Optional[datetime]): Notification visibility expiration.
            deduplication_key (Optional[str]): Optional event identifier.
            deduplication_scope (str): Namespace for the key; defaults to
                ``"global"``. Use a tenant, user or event namespace when needed.
            deduplication_key_expires_at (Optional[datetime]): When the key may
                be reused. ``None`` retains it until its notification is deleted.
            category (Optional[str]): Explicit category override. If omitted with
                a template, the template's category is used; otherwise ``general``.
            priority (str): One of ``low``, ``normal``, ``high`` or ``urgent``.
            group_audience_strategy (str): ``dynamic`` (default) resolves current
                membership at read time; ``snapshot`` captures members at creation.
            template_key (Optional[str]): Optional localized event template key.
            locale (str): Requested BCP-47 locale; defaults to ``en``.
            template_context (Optional[Dict[str, Any]]): Values for simple
                ``{variable}`` placeholders in the template.
            default_locale (str): Fallback locale after exact and base-language
                lookup; defaults to ``en``.

        Returns:
            Notification: The newly created notification, or the original
                notification when an active scoped key already exists.

        Raises:
            TypeError: If a key, scope or key expiry has an unsupported type.
            ValueError: If a key/scope is empty or too long, or the expiry is
                naive or not in the future, or if category/priority is invalid.
        """
        if actor is None:
            raise ValueError("actor is required to create a notification.")

        resolved_template_key = None
        resolved_locale = None
        if template_key is not None:
            from fastapi_notification.repository.manager.templates import (
                NotificationTemplateDataAccessLayer,
            )

            rendered = await NotificationTemplateDataAccessLayer(self.session).render(
                template_key,
                locale=locale,
                context=template_context,
                default_locale=default_locale,
            )
            verb = rendered.verb
            description = rendered.description
            category = category if category is not None else rendered.category
            resolved_template_key = rendered.key
            resolved_locale = rendered.locale
        elif verb is None:
            raise ValueError("verb is required when template_key is not provided.")

        if category is None:
            category = "general"
        category = normalize_category(category)
        priority = normalize_priority(priority)
        recipients, groups = await self._snapshot_audience(
            recipients, groups, group_audience_strategy
        )

        deduplication_key_expires_at = _validate_deduplication(
            deduplication_key, deduplication_scope, deduplication_key_expires_at
        )

        if deduplication_key is None:
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
                expires_at=expires_at,
                category=category,
                priority=priority,
                template_key=resolved_template_key,
                locale=resolved_locale,
            )
            if recipients:
                await queryset.add_recipients(self.session, notification, recipients)
            if groups:
                await queryset.add_groups(self.session, notification, groups)
            return notification

        # Keep the candidate notification, key claim and audience associations
        # atomic while leaving the outer transaction under caller control.
        async with self.session.begin_nested():
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
                expires_at=expires_at,
                category=category,
                priority=priority,
                template_key=resolved_template_key,
                locale=resolved_locale,
            )
            selected, claimed = await claim_deduplication_key(
                self.session,
                notification,
                scope=deduplication_scope,
                key=deduplication_key,
                expires_at=deduplication_key_expires_at,
            )
            if not claimed:
                # An active key is immutable: retries return the original
                # notification and never merge recipients or overwrite content.
                await self.session.delete(notification)
                await self.session.flush()
                await selected.resolve_generic_relations(self.session)
                await hydrate_notification_identities(self.session, [selected])
                return selected

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
        expires_at: Optional[datetime] = None,
        clear_expires_at: bool = False,
        category: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> Notification:
        """Update specified fields of an existing notification.

        Args:
            notification_id (int): The ID of the notification to update.
            is_sent (Optional[bool]): The sent status to update.
            public (Optional[bool]): The public visibility to update.
            data (Optional[Data]): Any additional data to update.
            expires_at (Optional[datetime]): New expiration instant.
            clear_expires_at (bool): Explicitly remove the current expiration.
            category (Optional[str]): New category key; ``None`` leaves it unchanged.
            priority (Optional[str]): New priority; ``None`` leaves it unchanged.

        Returns:
            Notification: The updated notification instance.
        """
        if category is not None:
            category = normalize_category(category)
        if priority is not None:
            priority = normalize_priority(priority)

        return await queryset.update_notification(
            self.session,
            notification_id,
            is_sent,
            public,
            data,
            expires_at,
            clear_expires_at,
            category,
            priority,
        )

    async def delete_notification(
        self,
        notification_id: int,
        recipient: Optional[Recipient] = None,
        soft_delete: bool = True,
        actor: Any = None,
    ) -> None:
        """Delete, or soft delete, the notification with the given ID.

        Args:
            notification_id (int): The ID of the notification to delete.
            recipient (Optional[Recipient]): The user performing the soft
                delete. Required for soft deletes.
            soft_delete (bool): Whether to perform a soft delete. Defaults to
                True.
            actor (Any): Staff identity performing a permanent deletion.
                Required when ``soft_delete`` is False.

        Raises:
            PermissionError: If permanent deletion is requested without a staff
                actor.
        """
        if not soft_delete:
            require_staff_identity(actor)

        await queryset.delete_notification(
            self.session, notification_id, recipient, soft_delete, actor
        )

    async def delete_many(self, statement: Select, *, actor: Any = None) -> int:
        """Permanently delete every notification matched by a statement.

        This is a privileged operation and requires a staff ``actor``.

        Args:
            statement (Select): A statement selecting whole notifications.
            actor (Any): Staff identity performing the deletion.

        Returns:
            int: The number of notifications deleted.

        Raises:
            PermissionError: If the actor is not staff.
        """
        require_staff_identity(actor)
        return await queryset.delete_many(self.session, statement, actor=actor)

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

    async def purge_expired(
        self,
        expired_before: datetime,
        *,
        limit: Optional[int] = None,
        actor: Any = None,
    ) -> int:
        """Permanently remove expired notifications older than a chosen cutoff.

        Expired rows are retained by default. This method is an explicit
        administrative cleanup operation; the caller controls the retention
        period by choosing ``expired_before`` and owns the transaction commit.

        Args:
            expired_before (datetime): Timezone-aware cutoff for expiration.
            limit (Optional[int]): Optional maximum number of rows to purge.
            actor (Any): Staff identity performing the cleanup.

        Returns:
            int: Number of notifications permanently removed.
        """
        return await queryset.purge_expired(
            self.session, expired_before, limit=limit, actor=actor
        )

    async def clear_all(self, user: Any) -> None:
        """Soft-delete every seen notification addressed to a user or their groups.

        Args:
            user (Any): The user whose notifications should be cleared.
        """
        await queryset.clear_all(self.session, user)
