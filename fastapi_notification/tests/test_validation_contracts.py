"""Boundary and recovery contracts exercised during release validation."""

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import Boolean, Date, String, select
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from fastapi_notification.identity import BuiltInIdentityAdapter
from fastapi_notification.models.auth import Group, User
from fastapi_notification.models.base import UTCDateTime
from fastapi_notification.models.content_type import coerce_object_id
from fastapi_notification.models.helper.enums import (
    NotificationCategory,
    NotificationPriority,
)
from fastapi_notification.models.helper.enums.notification_taxonomy import (
    normalize_priority,
)
from fastapi_notification.models.notification_preference import normalize_preference_key
from fastapi_notification.models.notification_quiet_hours import validate_timezone
from fastapi_notification.repository.manager.preferences import (
    NotificationPreferenceDataAccessLayer,
)
from fastapi_notification.repository.manager.scheduling import (
    NotificationSchedulingDataAccessLayer,
    _next_run,
)
from fastapi_notification.settings.conf import configure


@pytest.mark.parametrize(
    "value,error", [("invalid", TypeError), (datetime(2026, 1, 1), ValueError)]
)
def test_utc_column_rejects_invalid_bind_values(value: Any, error: Any) -> None:
    with pytest.raises(error):
        UTCDateTime().process_bind_param(value, sqlite_dialect())


def test_utc_column_converts_aware_database_results() -> None:
    value = datetime(2026, 1, 1, 4, tzinfo=timezone(timedelta(hours=4)))
    assert UTCDateTime().process_result_value(value, sqlite_dialect()) == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )


def test_taxonomy_choices_are_public_stable_values() -> None:
    assert ("general", "General") in NotificationCategory.choices()
    assert NotificationCategory.values() == [
        "general",
        "system",
        "security",
        "social",
        "financial",
        "orders",
        "marketing",
    ]
    assert NotificationPriority.choices() == [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]
    with pytest.raises(TypeError):
        normalize_priority(1)
    with pytest.raises(TypeError):
        normalize_preference_key(cast(Any, None))
    with pytest.raises(ValueError):
        validate_timezone("")


class ReferenceBase(DeclarativeBase):
    pass


class DateReference(ReferenceBase):
    __tablename__ = "date_reference"
    id: Mapped[date] = mapped_column(Date, primary_key=True)


class UnknownType(TypeDecorator):
    impl = String
    cache_ok = True

    @property
    def python_type(self) -> Any:
        raise NotImplementedError


class UnknownReference(ReferenceBase):
    __tablename__ = "unknown_reference"
    id: Mapped[str] = mapped_column(UnknownType, primary_key=True)


def test_generic_relation_invalid_model_and_key_type_contracts() -> None:
    with pytest.raises(TypeError, match="not a SQLAlchemy model"):
        coerce_object_id(object, "1")
    with pytest.raises(TypeError, match="supported Python type"):
        coerce_object_id(UnknownReference, "1")
    with pytest.raises(ValueError, match="Boolean"):
        coerce_object_id(User, True)
    value = date(2026, 1, 1)
    assert coerce_object_id(DateReference, value) == value
    with pytest.raises(TypeError, match="Unsupported generic relation"):
        coerce_object_id(DateReference, "not-a-date")


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"start_time": "22:00"}, TypeError),
        ({"start_time": time(22, tzinfo=timezone.utc)}, ValueError),
        ({"end_time": time(22)}, ValueError),
        ({"enabled": "yes"}, TypeError),
        ({"allow_urgent": 1}, TypeError),
    ],
)
async def test_quiet_rule_rejects_invalid_direct_calls(
    session: Any, user: Any, overrides: Any, error: Any
) -> None:
    arguments = {"start_time": time(22), "end_time": time(7)} | overrides
    with pytest.raises(error):
        await NotificationSchedulingDataAccessLayer(session).set_quiet_hours(
            user, **arguments
        )


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"frequency": "monthly"}, ValueError),
        ({"local_time": time(9, tzinfo=timezone.utc)}, ValueError),
        ({"frequency": "weekly", "weekday": True}, ValueError),
        ({"weekday": 1}, ValueError),
        ({"enabled": "yes"}, TypeError),
    ],
)
async def test_digest_rejects_invalid_direct_calls(
    session: Any, user: Any, overrides: Any, error: Any
) -> None:
    arguments = {"local_time": time(9)} | overrides
    with pytest.raises(error):
        await NotificationSchedulingDataAccessLayer(session).set_digest_schedule(
            user, **arguments
        )


@pytest.mark.parametrize("method", ["create_due_batches", "list_pending_batches"])
@pytest.mark.parametrize("limit", [0, True, 1001])
async def test_scheduler_rejects_invalid_batch_limits(
    session: Any, method: Any, limit: Any
) -> None:
    with pytest.raises(ValueError, match="limit"):
        await getattr(NotificationSchedulingDataAccessLayer(session), method)(
            limit=limit
        )


async def test_scheduler_lease_retry_and_update_contracts(
    session: Any, user: Any
) -> None:
    dal = NotificationSchedulingDataAccessLayer(session)
    assert await dal.next_allowed_at(user, channel="email") is None
    await dal.set_quiet_hours(user, start_time=time(22), end_time=time(7))
    assert (
        await dal.next_allowed_at(
            user, channel="email", at=datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        )
        is None
    )
    with pytest.raises(ValueError):
        await dal.claim_batch(1, stale_after=timedelta(0))
    with pytest.raises(ValueError, match="error_code"):
        await dal.mark_batch_failed(1, " ", claim_token=str(uuid4()))
    with pytest.raises(TypeError):
        await NotificationPreferenceDataAccessLayer(session).set_preference(
            user, enabled=cast(Any, "yes")
        )
    start = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    schedule = await dal.set_digest_schedule(user, local_time=time(9), now=start)
    batches = await dal.create_due_batches(now=schedule.next_run_at)
    assert [
        row.id for row in await dal.list_pending_batches(now=batches[0].scheduled_for)
    ] == [batches[0].id]
    assert await dal.claim_batch(batches[0].id, now=batches[0].scheduled_for)
    assert await dal.list_pending_batches(now=batches[0].scheduled_for) == []
    schedule = await dal.set_digest_schedule(user, local_time=time(10), now=start)
    assert schedule.last_run_at is None
    with pytest.raises(ValueError, match="frequency"):
        _next_run(
            after=start,
            frequency="monthly",
            local_time=time(9),
            timezone_name="UTC",
            weekday=None,
        )


async def test_snapshot_group_audience_survives_membership_removal(
    dal: Any, session: Any, user: Any, group: Any, group_user: Any
) -> None:
    class SnapshotAdapter(BuiltInIdentityAdapter):
        async def get_group_user_ids(self, session: Any, group: Any) -> Any:
            members = await session.scalars(
                select(User).where(
                    User.groups.any(Group.id == int(self.get_group_id(group)))
                )
            )
            return [self.get_user_id(member) for member in members]

    configure(IDENTITY_ADAPTER=SnapshotAdapter)
    snapshot = await dal.create_notification(
        verb="snapshot",
        actor=user,
        recipients=group_user,
        groups=[group, group],
        group_audience_strategy="snapshot",
        is_sent=True,
    )
    dynamic = await dal.create_notification(
        verb="dynamic", actor=user, groups=group, is_sent=True
    )
    await session.commit()
    await session.refresh(group_user, ["groups"])
    group_user.groups.clear()
    await session.commit()
    visible = await dal.sent(recipients=group_user, groups=[], display_detail=True)
    assert [item.id for item in visible] == [snapshot.id]
    assert dynamic.id != snapshot.id
    keyed = await dal.create_notification(
        verb="keyed group", actor=user, groups=group, deduplication_key="keyed-group"
    )
    assert keyed.id != snapshot.id
    await session.flush()
    with pytest.raises(ValueError, match="group_audience_strategy"):
        await dal.create_notification(
            verb="invalid", actor=user, group_audience_strategy="invalid"
        )


@pytest.mark.parametrize(
    "value,error", [("tomorrow", TypeError), (datetime(2026, 1, 1), ValueError)]
)
async def test_notification_update_rejects_invalid_expiration(
    dal: Any, notification: Any, value: Any, error: Any
) -> None:
    with pytest.raises(error):
        await dal.update_notification(notification.id, expires_at=value)


async def test_notification_creation_and_purge_reject_invalid_types(
    dal: Any, user: Any, staff_user: Any
) -> None:
    with pytest.raises(TypeError):
        await dal.create_notification(verb="invalid", actor=user, expires_at="tomorrow")
    with pytest.raises(TypeError):
        await dal.purge_expired("yesterday", actor=staff_user)


async def test_expiration_comparison_rejects_naive_instants() -> None:
    from fastapi_notification.repository.queryset.notification import (
        NotificationQuerySet,
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        NotificationQuerySet().not_expired_condition(datetime(2026, 1, 1))


@pytest.mark.parametrize(
    "expiry", [datetime(2026, 1, 1), datetime(2020, 1, 1, tzinfo=timezone.utc)]
)
async def test_dedup_claim_rejects_invalid_expiry_at_persistence_boundary(
    session: Any, notification: Any, expiry: Any
) -> None:
    from fastapi_notification.repository.queryset.deduplication import (
        claim_deduplication_key,
    )

    with pytest.raises(ValueError):
        await claim_deduplication_key(
            session, notification, scope="test", key="event", expires_at=expiry
        )


async def test_dedup_claim_bounds_adversarial_conflict_retries(
    monkeypatch: Any,
) -> None:
    from fastapi_notification.repository.queryset import deduplication

    attempts = []

    async def missing(*args: Any) -> Any:
        return None

    async def conflict(*args: Any) -> Any:
        attempts.append(1)
        return None, False

    monkeypatch.setattr(deduplication, "_get_key_record", missing)
    monkeypatch.setattr(deduplication, "insert_if_absent", conflict)
    with pytest.raises(RuntimeError, match="concurrent retries"):
        await deduplication.claim_deduplication_key(
            cast(Any, None),
            cast(Any, SimpleNamespace(id=1)),
            scope="test",
            key="event",
            expires_at=None,
        )
    assert len(attempts) == 5


async def test_dedup_claim_retries_lost_expiry_reclamation(monkeypatch: Any) -> None:
    from fastapi_notification.repository.queryset import deduplication

    expired = SimpleNamespace(
        id=1, expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc)
    )
    records = iter([expired, None])

    async def get_record(*args: Any) -> Any:
        return next(records)

    async def insert(*args: Any) -> Any:
        return None, True

    class LostUpdateSession:
        async def execute(self, statement: Any) -> Any:
            return SimpleNamespace(rowcount=0)

    monkeypatch.setattr(deduplication, "_get_key_record", get_record)
    monkeypatch.setattr(deduplication, "insert_if_absent", insert)
    notification: Any = SimpleNamespace(id=2)
    assert await deduplication.claim_deduplication_key(
        cast(Any, LostUpdateSession()),
        notification,
        scope="test",
        key="event",
        expires_at=None,
    ) == (notification, True)


def test_permission_requires_synchronous_membership_contract(monkeypatch: Any) -> None:
    from fastapi_notification.models.permissions import notification_permission

    monkeypatch.setattr(
        notification_permission,
        "get_identity_adapter",
        lambda: SimpleNamespace(get_user_id=lambda value: str(value.id)),
    )
    permission = notification_permission.NotificationPermission(
        SimpleNamespace(recipient=[], group=[])
    )
    with pytest.raises(RuntimeError, match="synchronous membership resolver"):
        permission.user_has_permission(SimpleNamespace(id=1))


def test_throttle_does_not_treat_invalid_host_identity_as_anonymous() -> None:
    from fastapi_notification.api.throttlings.role_base_throttle import (
        RoleBasedUserRateThrottle,
    )

    with pytest.raises(ValueError):
        RoleBasedUserRateThrottle().get_cache_key(SimpleNamespace(id=None))


def test_permission_setting_rejects_importable_function() -> None:
    from fastapi_notification.validators.config_validators import (
        validate_permission_class_setting,
    )

    errors = validate_permission_class_setting("builtins.print", "PERMISSION")
    assert len(errors) == 1
    assert errors[0].id == "fastapi_notification.E017_PERMISSION"


async def test_unseen_api_hides_permission_revocation_after_lookup(
    client: Any, as_user: Any, notification: Any, user: Any, monkeypatch: Any
) -> None:
    from fastapi_notification.models.notification import Notification

    async def revoked(self: Any, session: Any, identity: Any) -> Any:
        raise PermissionError("audience changed")

    monkeypatch.setattr(Notification, "mark_as_unseen", revoked)
    as_user(user)
    response = await client.post(f"/notifications/{notification.id}/mark_as_unseen/")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}


async def test_purge_handles_driver_without_delete_rowcount(
    session: Any, dal: Any, user: Any, staff_user: Any, monkeypatch: Any
) -> None:
    from sqlalchemy import Delete

    from fastapi_notification.models.notification import Notification

    expired = datetime(2020, 1, 1, tzinfo=timezone.utc)
    notification = await dal.create_notification(
        verb="expired", actor=user, expires_at=expired
    )
    await session.commit()
    notification_id = notification.id
    execute = session.execute

    async def execute_without_rowcount(
        statement: Any, *args: Any, **kwargs: Any
    ) -> Any:
        result = await execute(statement, *args, **kwargs)
        if (
            isinstance(statement, Delete)
            and getattr(statement.table, "name", None) == "notification"
        ):
            return SimpleNamespace(rowcount=None)
        return result

    monkeypatch.setattr(session, "execute", execute_without_rowcount)
    assert (
        await dal.purge_expired(
            datetime(2021, 1, 1, tzinfo=timezone.utc), actor=staff_user
        )
        == 1
    )
    await session.commit()
    assert await session.get(Notification, notification_id) is None
