from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import create_engine, inspect

from fastapi_notification.identity import (
    IdentityAdapter,
    IdentityReference,
    get_identity_adapter,
    normalize_identity_id,
)
from fastapi_notification.models.associations import notification_group
from fastapi_notification.models.base import AuthBase, Base
from fastapi_notification.models.deleted_notification import DeletedNotification
from fastapi_notification.models.notification_recipient import NotificationRecipient
from fastapi_notification.models.notification_seen import NotificationSeen
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.utils]


@dataclass
class ExternalGroup:
    slug: str


@dataclass
class ExternalUser:
    uuid: UUID
    teams: list[ExternalGroup] = field(default_factory=list)
    admin: bool = False


class ExternalIdentityAdapter(IdentityAdapter):
    user_id_attribute = "uuid"
    group_id_attribute = "slug"
    user_groups_attribute = "teams"
    staff_attribute = "admin"


def test_normalize_identity_id_accepts_uuid_and_integer() -> None:
    """Integer and UUID keys have stable string representations."""
    value = UUID("a8098c1a-f86e-11da-bd1a-00112444be1e")

    assert normalize_identity_id(value) == str(value)
    assert normalize_identity_id(42) == "42"


def test_normalize_identity_id_rejects_empty_and_oversized_values() -> None:
    """Opaque identity keys are bounded before they enter indexed columns."""
    with pytest.raises(ValueError, match="1 to 255"):
        normalize_identity_id("")
    with pytest.raises(ValueError, match="1 to 255"):
        normalize_identity_id("x" * 256)


@pytest.mark.asyncio
async def test_adapter_supports_custom_user_and_group_attributes() -> None:
    """A host adapter can map UUID users and slug-based groups."""
    group = ExternalGroup(slug="moderators")
    user = ExternalUser(
        uuid=UUID("a8098c1a-f86e-11da-bd1a-00112444be1e"),
        teams=[group],
        admin=True,
    )
    adapter = ExternalIdentityAdapter()

    assert adapter.get_user_id(user) == str(user.uuid)
    assert adapter.get_group_id(group) == "moderators"
    assert await adapter.get_user_group_ids(None, user) == ["moderators"]
    assert adapter.is_staff(user) is True
    assert adapter.is_superuser(user) is False


@pytest.mark.asyncio
async def test_base_adapter_resolves_ids_without_auth_table_queries() -> None:
    """The generic adapter represents IDs without querying built-in auth tables."""
    adapter = IdentityAdapter()

    users = await adapter.resolve_users(None, ["user-1"])
    groups = await adapter.resolve_groups(None, ["group-1"])

    assert users == {"user-1": IdentityReference("user-1", "user-1", "user-1")}
    assert groups == {"group-1": IdentityReference("group-1", "group-1", "group-1")}


def test_configured_adapter_class_is_used() -> None:
    """The adapter is configured as a class, not a global model replacement."""
    configure(IDENTITY_ADAPTER=ExternalIdentityAdapter)

    assert isinstance(get_identity_adapter(), ExternalIdentityAdapter)


def test_notification_metadata_has_no_auth_model_tables() -> None:
    """Core notification metadata can be created without users or groups."""
    assert "users" not in Base.metadata.tables
    assert "groups" not in Base.metadata.tables
    assert "users" in AuthBase.metadata.tables
    assert "groups" in AuthBase.metadata.tables


def test_identity_association_columns_are_opaque_and_unconstrained() -> None:
    """Notification identity associations do not reference auth tables."""
    for table, column_name in (
        (NotificationRecipient.__table__, "recipient_id"),
        (NotificationSeen.__table__, "user_id"),
        (DeletedNotification.__table__, "user_id"),
        (notification_group, "group_id"),
    ):
        column = table.c[column_name]
        assert column.type.length == 255
        assert not column.foreign_keys


def test_core_metadata_creates_without_authentication_tables() -> None:
    """Creating the core schema does not create package-owned auth tables."""
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert "notification" in table_names
    assert "notification_recipient" in table_names
    assert "notification_seen" in table_names
    assert "deleted_notifications" in table_names
    assert "notification_deduplication" in table_names
    assert "users" not in table_names
    assert "groups" not in table_names


class FakeScalarResult:
    """A minimal SQLAlchemy result wrapper for adapter unit tests."""

    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class FakeExecutionResult:
    """A result exposing the row and scalar interfaces used by the adapter."""

    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def scalars(self):
        return FakeScalarResult(self.rows)


class FakeSession:
    """Return queued result sets for successive async execute calls."""

    def __init__(self, result_sets):
        self.result_sets = list(result_sets)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeExecutionResult(self.result_sets.pop(0))


@pytest.mark.asyncio
async def test_adapter_returns_empty_groups_when_user_has_no_group_attribute():
    """A host user without a group property belongs to no notification groups."""
    adapter = IdentityAdapter()

    assert await adapter.get_user_group_ids(None, object()) == []


def test_adapter_rejects_missing_user_and_group_identifiers():
    """Identity models must expose the configured stable identifier."""
    adapter = IdentityAdapter()

    with pytest.raises(ValueError, match="cannot be None"):
        adapter.get_user_id(object())
    with pytest.raises(ValueError, match="cannot be None"):
        adapter.get_group_id(object())


def test_normalize_identity_id_supports_objects_and_rejects_nul():
    """Identity-like objects and invalid strings are handled explicitly."""

    class Identity:
        id = "external-user"

    assert normalize_identity_id(Identity()) == "external-user"
    with pytest.raises(ValueError, match="NUL"):
        normalize_identity_id("invalid\x00identifier")


@pytest.mark.asyncio
async def test_built_in_adapter_resolves_optional_auth_models():
    """The optional adapter resolves the example User and Group records."""
    from fastapi_notification.identity import BuiltInIdentityAdapter
    from fastapi_notification.models.auth import Group, User

    user = User(id=7, username="seven", email="seven@example.com")
    group = Group(id=9, name="nine")
    adapter = BuiltInIdentityAdapter()

    users = await adapter.resolve_users(FakeSession([[user]]), ["7"])
    groups = await adapter.resolve_groups(FakeSession([[group]]), ["9"])

    assert users == {"7": user}
    assert groups == {"9": group}
    assert await adapter.resolve_users(FakeSession([]), []) == {}
    assert await adapter.resolve_groups(FakeSession([]), []) == {}


@pytest.mark.asyncio
async def test_hydrate_notification_identities_batches_all_associations():
    """Recipient, group, and seen-by identities are resolved in three batches."""
    from fastapi_notification.identity import hydrate_notification_identities
    from fastapi_notification.models.notification import Notification

    notification = Notification(id=21)
    session = FakeSession(
        [
            [(21, "recipient-1")],
            [(21, "group-1")],
            [(21, "viewer-1")],
        ]
    )

    await hydrate_notification_identities(session, [notification])

    assert len(session.statements) == 3
    assert notification.recipient[0].id == "recipient-1"
    assert notification.group[0].id == "group-1"
    assert notification.seen_by[0].id == "viewer-1"


@pytest.mark.asyncio
async def test_hydrate_notification_identities_preserves_unresolved_ids():
    """Unresolvable host records remain visible as ID-only references."""
    from fastapi_notification.identity import (
        IdentityAdapter,
        hydrate_notification_identities,
    )
    from fastapi_notification.models.notification import Notification

    class PartialAdapter(IdentityAdapter):
        async def resolve_users(self, session, user_ids):
            return {}

        async def resolve_groups(self, session, group_ids):
            return {}

    configure(IDENTITY_ADAPTER=PartialAdapter)
    notification = Notification(id=22)
    session = FakeSession([[(22, "missing-user")], [(22, "missing-group")], []])

    await hydrate_notification_identities(session, [notification])

    assert notification.recipient[0].id == "missing-user"
    assert notification.group[0].id == "missing-group"


@pytest.mark.asyncio
async def test_hydrate_notification_identities_skips_empty_notification_lists():
    """An empty list does not execute association queries."""
    from fastapi_notification.identity import hydrate_notification_identities

    session = FakeSession([])

    await hydrate_notification_identities(session, [])

    assert session.statements == []


@pytest.mark.asyncio
async def test_notification_load_identities_delegates_to_adapter():
    """The model exposes an explicit loader for direct SQLAlchemy queries."""
    from fastapi_notification.models.notification import Notification

    notification = Notification(id=23)
    session = FakeSession([[], [], []])

    result = await notification.load_identities(session)

    assert result is notification
    assert len(session.statements) == 3


def test_resolved_identity_index_accepts_mapping_and_sequence_results():
    """Adapter resolution results are normalized regardless of their shape."""
    from fastapi_notification.identity import index_resolved_identities

    adapter = IdentityAdapter()
    reference = IdentityReference("sequence-user", "sequence-user", "sequence-user")

    assert index_resolved_identities(
        {"mapping-user": reference}, adapter.get_user_id
    ) == {"mapping-user": reference}
    assert index_resolved_identities([reference], adapter.get_user_id) == {
        "sequence-user": reference
    }


def test_identity_adapter_instance_is_cached_for_repeated_lookups():
    """The configured adapter is instantiated once and reused."""
    configure(IDENTITY_ADAPTER=ExternalIdentityAdapter)

    first = get_identity_adapter()
    second = get_identity_adapter()

    assert first is second


def test_identity_reference_string_uses_its_display_identifier():
    """Identity references have a useful display representation."""
    reference = IdentityReference("user-1", "user-1", "user-1")

    assert str(reference) == "user-1"


def test_adapter_accepts_raw_scalar_user_and_group_ids():
    """Raw integer and UUID values can be used without model instances."""
    from uuid import UUID

    adapter = IdentityAdapter()
    identifier = UUID("a8098c1a-f86e-11da-bd1a-00112444be1e")

    assert adapter.get_user_id(42) == "42"
    assert adapter.get_group_id(identifier) == str(identifier)


def test_configured_adapter_instance_is_supported():
    """A prebuilt adapter instance can be supplied directly."""
    adapter = ExternalIdentityAdapter()
    configure(IDENTITY_ADAPTER=adapter)

    assert get_identity_adapter() is adapter


def test_get_identity_adapter_rejects_an_incomplete_instance():
    """The adapter contract is checked before an instance is returned."""
    configure(IDENTITY_ADAPTER=object())

    with pytest.raises(TypeError, match="missing required methods"):
        get_identity_adapter()


def test_queryset_identity_helpers_normalize_external_ids():
    """Recipient and group query helpers use the configured adapter."""
    from fastapi_notification.repository.queryset.notification import _ids

    configure(IDENTITY_ADAPTER=ExternalIdentityAdapter)
    user = ExternalUser(uuid=UUID("a8098c1a-f86e-11da-bd1a-00112444be1e"))
    group = ExternalGroup(slug="moderators")

    assert _ids(user, "user") == [str(user.uuid)]
    assert _ids(group, "group") == ["moderators"]
    assert _ids("user-1", "user") == ["user-1"]


def test_notification_filter_normalizes_external_user_and_group_ids():
    """Filter parameters are compared using normalized opaque identity IDs."""
    from fastapi_notification.api.filters.notification_filter import NotificationFilter

    configure(IDENTITY_ADAPTER=ExternalIdentityAdapter)
    user_id = "a8098c1a-f86e-11da-bd1a-00112444be1e"
    filterset = NotificationFilter(
        group__id="moderators",
        recipient__id=user_id,
        status=None,
        public=None,
        timestamp_after=None,
        timestamp_before=None,
        search=None,
        ordering=None,
    )

    conditions = filterset.filter_conditions()

    assert len(conditions) == 2
    compiled_conditions = [
        str(condition.compile(compile_kwargs={"literal_binds": True}))
        for condition in conditions
    ]
    assert "moderators" in compiled_conditions[0]
    assert user_id in compiled_conditions[1]


@pytest.mark.asyncio
async def test_snapshot_membership_requires_explicit_adapter_support():
    adapter = IdentityAdapter()
    with pytest.raises(NotImplementedError, match="get_group_user_ids"):
        await adapter.get_group_user_ids(None, "engineering")


@pytest.mark.asyncio
async def test_custom_adapter_can_resolve_snapshot_group_members():
    class SnapshotAdapter(IdentityAdapter):
        async def get_group_user_ids(self, session, group):
            assert session is None
            return ["user-1", "user-2"]

    adapter = SnapshotAdapter()
    members = await adapter.get_group_user_ids(None, "engineering")
    assert members == ["user-1", "user-2"]


@pytest.mark.asyncio
async def test_group_resolution_loads_unloaded_relationship(
    session: Any, group_user: Any, group: Any
) -> None:
    """Checking relationship presence must not trigger implicit async ORM I/O."""
    session.expire(group_user, ["groups"])
    assert "groups" in inspect(group_user).unloaded
    assert await IdentityAdapter().get_user_group_ids(session, group_user) == [
        str(group.id)
    ]


@pytest.mark.asyncio
async def test_group_resolution_accepts_identity_without_groups() -> None:
    assert await IdentityAdapter().get_user_group_ids(None, object()) == []
