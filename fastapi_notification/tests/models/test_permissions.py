from typing import Any, List

import pytest

from fastapi_notification.models.permissions.notification_permission import (
    NotificationPermission,
)

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
    permission = NotificationPermission(FakeNotification([FakeRecord(1)], [FakeRecord(7)]))

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
