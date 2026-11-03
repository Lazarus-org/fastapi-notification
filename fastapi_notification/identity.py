"""Identity integration for host application user and group models.

The notification schema stores user and group identifiers as opaque strings. This module
is the only boundary between those identifiers and the host application's authentication
and authorization models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Type
from uuid import UUID

from sqlalchemy import Select, String, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.utils.loading import ensure_loaded


@dataclass(frozen=True)
class IdentityReference:
    """A minimal identity representation used when no resolver is configured."""

    id: str
    username: str
    name: str
    email: Optional[str] = None

    def __str__(self) -> str:
        return self.username


def normalize_identity_id(value: Any) -> str:
    """Return a validated string representation of an identity identifier.

    An identity object may be supplied instead of its identifier; in that case
    its ``id`` attribute is used. String storage keeps the notification schema
    independent of the host application's primary-key type.

    Args:
        value: An identifier or an object exposing an ``id`` attribute.

    Returns:
        str: The canonical identifier used by notification association tables.

    Raises:
        ValueError: If the identifier is missing, empty, or longer than 255
            characters.
    """
    identifier = getattr(value, "id", value)
    if identifier is None:
        raise ValueError("Identity identifiers cannot be None.")

    normalized = str(identifier)
    if not normalized or len(normalized) > 255:
        raise ValueError("Identity identifiers must contain 1 to 255 characters.")
    if "\x00" in normalized:
        raise ValueError("Identity identifiers cannot contain NUL characters.")

    return normalized


class IdentityAdapter:
    """Base adapter for integrating host application identities.

    Subclass this adapter when user IDs, group IDs, membership, or identity resolution
    differ from the conventional ``id`` and ``groups`` attributes. The base
    implementation does not query or require package-owned auth tables.

    ``resolve_users`` and ``resolve_groups`` return mappings keyed by the normalized
    identifier. Their default implementations return lightweight
    :class:`IdentityReference` objects, so API serialization does not require access to
    a user or group table.
    """

    user_id_attribute = "id"
    group_id_attribute = "id"
    user_groups_attribute = "groups"
    staff_attribute = "is_staff"
    superuser_attribute = "is_superuser"

    def get_user_id(self, user: Any) -> str:
        """Return the normalized identifier for a host user or raw ID."""
        if isinstance(user, (str, int, UUID)):
            identifier: object = user
        else:
            identifier = getattr(user, self.user_id_attribute, None)
        return normalize_identity_id(identifier)

    def get_group_id(self, group: Any) -> str:
        """Return the normalized identifier for a host group or raw ID."""
        if isinstance(group, (str, int, UUID)):
            identifier: object = group
        else:
            identifier = getattr(group, self.group_id_attribute, None)
        return normalize_identity_id(identifier)

    async def get_group_user_ids(
        self, session: AsyncSession, group: Any
    ) -> Sequence[Any]:
        """Return current users belonging to a group for snapshot delivery.

        Applications using snapshot group audiences must override this method and return
        the member identities at creation time. The default adapter deliberately refuses
        to guess how a host application stores membership.
        """
        del session, group
        raise NotImplementedError(
            "Snapshot group audiences require an identity adapter that "
            "implements get_group_user_ids()."
        )

    async def get_user_group_ids(
        self, session: AsyncSession, user: Any
    ) -> Sequence[str]:
        """Return group identifiers for a user.

        The default implementation reads ``user.groups``. Adapters for external
        membership tables should override this method and query them using the supplied
        session.
        """
        await ensure_loaded(session, user, self.user_groups_attribute)
        groups = getattr(user, self.user_groups_attribute, None) or []
        return [self.get_group_id(group) for group in groups]

    def get_user_group_ids_sync(self, user: Any) -> Sequence[str]:
        """Return group IDs from membership data already loaded in memory.

        This synchronous counterpart is intended for the synchronous
        ``NotificationPermission.user_has_permission`` helper. It never
        performs database I/O. Adapters that override :meth:`get_user_group_ids`
        to query an external membership store must also override this method if
        they need synchronous permission checks. Otherwise the method raises
        rather than silently making an incomplete authorization decision.

        Database-backed application code should prefer
        :meth:`get_user_group_ids`, which is the authoritative async contract.
        """
        if (
            type(self).get_user_group_ids is not IdentityAdapter.get_user_group_ids
            and type(self).get_user_group_ids_sync
            is IdentityAdapter.get_user_group_ids_sync
        ):
            raise RuntimeError(
                "This identity adapter resolves group membership asynchronously; "
                "override get_user_group_ids_sync() for synchronous permission "
                "checks or use validate_permission_async()."
            )

        groups = getattr(user, self.user_groups_attribute, None) or []
        return [self.get_group_id(group) for group in groups]

    def is_staff(self, user: Any) -> bool:
        """Return whether the host application considers the user staff."""
        return bool(getattr(user, self.staff_attribute, False))

    def is_superuser(self, user: Any) -> bool:
        """Return whether the host application considers the user a superuser."""
        return bool(getattr(user, self.superuser_attribute, False))

    async def resolve_users(
        self, session: AsyncSession, user_ids: Sequence[str]
    ) -> Mapping[str, Any]:
        """Resolve user identifiers for API representation.

        Override this method to load the corresponding host user records. The base
        implementation intentionally performs no database query.
        """
        del session
        return {
            identifier: IdentityReference(
                id=identifier, username=identifier, name=identifier
            )
            for identifier in user_ids
        }

    async def resolve_groups(
        self, session: AsyncSession, group_ids: Sequence[str]
    ) -> Mapping[str, Any]:
        """Resolve group identifiers for API representation.

        Override this method to load the corresponding host group records. The base
        implementation intentionally performs no database query.
        """
        del session
        return {
            identifier: IdentityReference(
                id=identifier, username=identifier, name=identifier
            )
            for identifier in group_ids
        }


class BuiltInIdentityAdapter(IdentityAdapter):
    """Optional adapter for the package's example ``User`` and ``Group`` models.

    This adapter is the default for backwards-compatible standalone usage.
    Host applications with their own identity models should configure a custom
    :class:`IdentityAdapter`; notification tables themselves do not have foreign
    keys to these built-in models.
    """

    async def resolve_users(
        self, session: AsyncSession, user_ids: Sequence[str]
    ) -> Mapping[str, Any]:
        from fastapi_notification.models.auth import User

        if not user_ids:
            return {}

        result = await session.execute(
            select(User).where(cast(User.id, String).in_(list(user_ids)))
        )
        return {self.get_user_id(user): user for user in result.scalars().all()}

    async def resolve_groups(
        self, session: AsyncSession, group_ids: Sequence[str]
    ) -> Mapping[str, Any]:
        from fastapi_notification.models.auth import Group

        if not group_ids:
            return {}

        result = await session.execute(
            select(Group).where(cast(Group.id, String).in_(list(group_ids)))
        )
        return {self.get_group_id(group): group for group in result.scalars().all()}


def is_staff_identity(user: Any) -> bool:
    """Return the single package-wide administrative role decision.

    Administrative hard deletion is intentionally staff-only. A superuser flag does not
    imply staff status; applications that want a superuser to administer notifications
    should expose both through their adapter.
    """
    return bool(get_identity_adapter().is_staff(user))


def require_staff_identity(user: Any) -> None:
    """Raise when an identity does not satisfy the staff-only admin policy."""
    if user is None or not is_staff_identity(user):
        raise PermissionError(
            "Staff permission is required for administrative notification deletion."
        )


@dataclass
class _AdapterCache:
    adapter_class: Optional[Type[IdentityAdapter]] = None
    instance: Optional[IdentityAdapter] = None


_adapter_cache = _AdapterCache()


def get_identity_adapter() -> IdentityAdapter:
    """Return the cached instance of the configured identity adapter class."""
    from fastapi_notification.settings.conf import config

    adapter_class = config.identity_adapter
    if not isinstance(adapter_class, type):
        adapter = adapter_class
    else:
        if adapter_class is not _adapter_cache.adapter_class:
            _adapter_cache.instance = adapter_class()
            _adapter_cache.adapter_class = adapter_class
        adapter = _adapter_cache.instance

    required_methods = (
        "get_user_id",
        "get_group_id",
        "get_user_group_ids",
        "is_staff",
        "is_superuser",
        "resolve_users",
        "resolve_groups",
    )
    missing = [
        name for name in required_methods if not callable(getattr(adapter, name, None))
    ]
    if missing:
        raise TypeError(
            "The configured identity adapter is missing required methods: "
            + ", ".join(missing)
        )

    return adapter


def index_resolved_identities(
    identities: Any, identifier_getter: Any
) -> Dict[str, Any]:
    """Normalize an adapter's mapping or sequence result to an ID mapping."""
    if isinstance(identities, Mapping):
        return {normalize_identity_id(key): value for key, value in identities.items()}

    indexed: Dict[str, Any] = {}
    for identity in identities or []:
        indexed[identifier_getter(identity)] = identity
    return indexed


async def _association_ids(
    session: AsyncSession,
    statement: Select[int, str],
    notification_ids: Sequence[int],
) -> Dict[int, list[str]]:
    """Index batched association rows without triggering ORM relationship loads."""
    indexed: Dict[int, list[str]] = {identifier: [] for identifier in notification_ids}
    result = await session.execute(statement)
    for notification_id, identity_id in result.all():
        indexed[notification_id].append(identity_id)
    return indexed


async def _notification_audiences(
    session: AsyncSession, notifications: Sequence[Any]
) -> Tuple[Dict[int, list[str]], Dict[int, list[str]], Dict[int, list[str]]]:
    """Fetch each audience projection once for a batch of notifications."""
    from fastapi_notification.models.associations import notification_group
    from fastapi_notification.models.notification_recipient import NotificationRecipient
    from fastapi_notification.models.notification_seen import NotificationSeen

    notification_ids = [item.id for item in notifications]
    recipients_by_notification = await _association_ids(
        session,
        select(
            NotificationRecipient.notification_id, NotificationRecipient.recipient_id
        ).where(NotificationRecipient.notification_id.in_(notification_ids)),
        notification_ids,
    )
    groups_by_notification = await _association_ids(
        session,
        select(
            notification_group.c.notification_id, notification_group.c.group_id
        ).where(notification_group.c.notification_id.in_(notification_ids)),
        notification_ids,
    )
    seen_by_notification = await _association_ids(
        session,
        select(NotificationSeen.notification_id, NotificationSeen.user_id).where(
            NotificationSeen.notification_id.in_(notification_ids)
        ),
        notification_ids,
    )

    return recipients_by_notification, groups_by_notification, seen_by_notification


async def hydrate_notification_identities(
    session: AsyncSession, notifications: Sequence[Any]
) -> None:
    """Populate recipient, group, and seen-by projections for notifications.

    All association rows are fetched in batches, then the configured adapter resolves
    identities. No ORM relationship to a package-owned auth table is involved in the
    notification query itself.
    """
    if not notifications:
        return

    recipients_by_notification, groups_by_notification, seen_by_notification = (
        await _notification_audiences(session, notifications)
    )

    user_ids = sorted(
        {
            identity_id
            for values in (
                *recipients_by_notification.values(),
                *seen_by_notification.values(),
            )
            for identity_id in values
        }
    )
    group_ids = sorted(
        {
            identity_id
            for values in groups_by_notification.values()
            for identity_id in values
        }
    )

    adapter = get_identity_adapter()
    users = index_resolved_identities(
        await adapter.resolve_users(session, user_ids), adapter.get_user_id
    )
    groups = index_resolved_identities(
        await adapter.resolve_groups(session, group_ids), adapter.get_group_id
    )

    # Preserve associations even when a host resolver cannot find a deleted or
    # otherwise unavailable identity record. The identifier remains useful to
    # clients and can still be audited.
    for identifier in user_ids:
        users.setdefault(
            identifier,
            IdentityReference(id=identifier, username=identifier, name=identifier),
        )
    for identifier in group_ids:
        groups.setdefault(
            identifier,
            IdentityReference(id=identifier, username=identifier, name=identifier),
        )

    for notification in notifications:
        notification.recipient = [
            users[identity_id]
            for identity_id in recipients_by_notification[notification.id]
            if identity_id in users
        ]
        notification.group = [
            groups[identity_id]
            for identity_id in groups_by_notification[notification.id]
            if identity_id in groups
        ]
        notification.seen_by = [
            users[identity_id]
            for identity_id in seen_by_notification[notification.id]
            if identity_id in users
        ]


__all__ = [
    "BuiltInIdentityAdapter",
    "IdentityAdapter",
    "IdentityReference",
    "get_identity_adapter",
    "hydrate_notification_identities",
    "is_staff_identity",
    "require_staff_identity",
    "index_resolved_identities",
    "normalize_identity_id",
]
