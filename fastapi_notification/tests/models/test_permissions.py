from typing import Any, List

import pytest

from fastapi_notification.identity import IdentityAdapter
from fastapi_notification.models.permissions.notification_permission import (
    NotificationPermission,
)
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.repository.queryset import notification as queryset
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.models, pytest.mark.models_permissions]


class FakeUser:
    """A stand-in user, so the permission logic can be tested in isolation."""

    def __init__(
        self,
        identifier: int,
        groups: List[Any],
        is_staff: bool = False,
        is_superuser: bool = False,
    ) -> None:
        self.id = identifier
        self.groups = groups
        self.is_staff = is_staff
        self.is_superuser = is_superuser
        self.username = f"user-{identifier}"


class FakeRecord:
    """A stand-in object carrying only an identifier."""

    def __init__(self, identifier: int) -> None:
        self.id = identifier


class FakeNotification:
    """A stand-in notification with plain recipient and group collections."""

    def __init__(self, recipient: List[Any], group: List[Any]) -> None:
        self.id = 1
        self.recipient = recipient
        self.group = group


def test_recipient_has_permission() -> None:
    """A named recipient may act on the notification."""
    user = FakeUser(1, groups=[])
    permission = NotificationPermission(FakeNotification([FakeRecord(1)], []))

    assert permission.user_has_permission(user) is True


def test_group_member_has_permission() -> None:
    """A member of a targeted group may act on the notification."""
    user = FakeUser(2, groups=[FakeRecord(7)])
    permission = NotificationPermission(FakeNotification([], [FakeRecord(7)]))

    assert permission.user_has_permission(user) is True


def test_staff_without_audience_membership_has_no_permission() -> None:
    """Staff status alone does not grant access to a personal notification."""
    user = FakeUser(3, groups=[], is_staff=True)
    permission = NotificationPermission(FakeNotification([], []))

    assert permission.user_has_permission(user) is False


def test_superuser_without_audience_membership_has_no_permission() -> None:
    """Superuser status alone does not grant access to a personal notification."""
    user = FakeUser(5, groups=[], is_superuser=True)
    permission = NotificationPermission(FakeNotification([], []))

    assert permission.user_has_permission(user) is False


def test_unrelated_user_has_no_permission() -> None:
    """Everyone else is refused."""
    user = FakeUser(4, groups=[FakeRecord(9)])
    permission = NotificationPermission(
        FakeNotification([FakeRecord(1)], [FakeRecord(7)])
    )

    assert permission.user_has_permission(user) is False


def test_validate_permission_passes_for_a_recipient() -> None:
    """Validation is silent when the user is allowed."""
    user = FakeUser(1, groups=[])
    permission = NotificationPermission(FakeNotification([FakeRecord(1)], []))

    assert permission.validate_permission(user, "delete") is None


def test_validate_permission_raises_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validation refuses, and leaves a trace, when the user is not allowed."""
    user = FakeUser(4, groups=[])
    permission = NotificationPermission(FakeNotification([], []))

    with pytest.raises(PermissionError, match="permission to delete"):
        permission.validate_permission(user, "delete")

    assert "without permission" in caplog.text


class SlugGroup:
    """A group represented by a non-integer slug identifier."""

    def __init__(self, slug: str) -> None:
        self.slug = slug


class TeamsUser:
    """A host identity exposing team membership instead of ``groups``."""

    def __init__(self, identifier: str, teams: List[SlugGroup]) -> None:
        self.uuid = identifier
        self.teams = teams


class TeamsIdentityAdapter(IdentityAdapter):
    user_id_attribute = "uuid"
    group_id_attribute = "slug"
    user_groups_attribute = "teams"


class DatabaseMembershipAdapter(IdentityAdapter):
    """An adapter whose authoritative membership resolver is asynchronous."""

    async def get_user_group_ids(self, session: Any, user: Any) -> List[str]:
        del session, user
        return ["remote-team"]


class CachedDatabaseMembershipAdapter(DatabaseMembershipAdapter):
    """An adapter that also exposes a preloaded synchronous membership view."""

    def get_user_group_ids_sync(self, user: Any) -> List[str]:
        return list(user.cached_group_ids)


class CachedMembershipUser:
    def __init__(self, identifier: int, cached_group_ids: List[str]) -> None:
        self.id = identifier
        self.cached_group_ids = cached_group_ids


class SlugNotificationGroup:
    def __init__(self, slug: str) -> None:
        self.slug = slug


def test_sync_permission_uses_custom_identity_group_attributes() -> None:
    """The synchronous helper respects a host adapter's configured fields."""
    configure(IDENTITY_ADAPTER=TeamsIdentityAdapter)
    user = TeamsUser("user-uuid", [SlugGroup("moderators")])
    notification = FakeNotification([], [SlugNotificationGroup("moderators")])

    assert NotificationPermission(notification).user_has_permission(user) is True


def test_sync_permission_rejects_async_only_membership_adapters() -> None:
    """An async-only membership adapter cannot silently under-authorize sync checks."""
    configure(IDENTITY_ADAPTER=DatabaseMembershipAdapter)
    user = FakeUser(9, groups=[])
    notification = FakeNotification([], [FakeRecord(7)])

    with pytest.raises(RuntimeError, match="resolves group membership asynchronously"):
        NotificationPermission(notification).user_has_permission(user)


def test_sync_permission_supports_explicit_cached_membership_adapter() -> None:
    """An adapter may expose a safe preloaded view for synchronous checks."""
    configure(IDENTITY_ADAPTER=CachedDatabaseMembershipAdapter)
    user = CachedMembershipUser(10, ["remote-team"])
    notification = FakeNotification([], [FakeRecord("remote-team")])

    assert NotificationPermission(notification).user_has_permission(user) is True


@pytest.mark.asyncio
async def test_dal_hard_delete_requires_a_staff_actor() -> None:
    """The DAL does not expose an unguarded permanent-delete path."""
    dal = NotificationDataAccessLayer(None)  # The guard runs before database I/O.
    user = FakeUser(30, groups=[])

    with pytest.raises(PermissionError, match="Staff permission is required"):
        await dal.delete_notification(1, soft_delete=False, actor=user)


@pytest.mark.asyncio
async def test_dal_hard_delete_requires_an_explicit_actor() -> None:
    """Omitting the actor cannot silently turn a DAL call into admin access."""
    dal = NotificationDataAccessLayer(None)

    with pytest.raises(PermissionError, match="Staff permission is required"):
        await dal.delete_notification(1, soft_delete=False)


@pytest.mark.asyncio
async def test_dal_bulk_hard_delete_requires_a_staff_actor() -> None:
    """Bulk deletion applies the same staff policy as single deletion."""
    dal = NotificationDataAccessLayer(None)
    user = FakeUser(31, groups=[])

    with pytest.raises(PermissionError, match="Staff permission is required"):
        await dal.delete_many(None, actor=user)


@pytest.mark.asyncio
async def test_dal_hard_delete_rejects_superuser_without_staff() -> None:
    """Superuser status does not bypass the DAL staff-only admin policy."""
    dal = NotificationDataAccessLayer(None)
    superuser = FakeUser(32, groups=[], is_superuser=True)

    with pytest.raises(PermissionError, match="Staff permission is required"):
        await dal.delete_notification(1, soft_delete=False, actor=superuser)


@pytest.mark.asyncio
async def test_dal_bulk_hard_delete_requires_an_explicit_actor() -> None:
    """The bulk DAL operation rejects a missing actor consistently."""
    dal = NotificationDataAccessLayer(None)

    with pytest.raises(PermissionError, match="Staff permission is required"):
        await dal.delete_many(None)


@pytest.mark.asyncio
async def test_low_level_query_delete_requires_staff_actor() -> None:
    """The lower-level persistence helper cannot bypass the admin policy."""
    user = FakeUser(33, groups=[])

    with pytest.raises(PermissionError, match="Staff permission is required"):
        await queryset.delete_notification(
            None, 1, soft_delete=False, actor=user
        )


@pytest.mark.asyncio
async def test_low_level_bulk_delete_requires_staff_actor() -> None:
    """The lower-level bulk persistence helper uses the same admin policy."""
    user = FakeUser(34, groups=[])

    with pytest.raises(PermissionError, match="Staff permission is required"):
        await queryset.delete_many(None, None, actor=user)
