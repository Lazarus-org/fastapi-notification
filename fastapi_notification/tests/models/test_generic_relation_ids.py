"""Tests for integer, UUID and string generic relation identifiers."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import String, Text, Uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.api.schemas.dynamic_notification import (
    NotificationDynamicSerializer,
)
from fastapi_notification.models.auth import User
from fastapi_notification.models.base import AuthBase
from fastapi_notification.models.content_type import (
    ContentType,
    coerce_object_id,
    normalize_object_id,
)
from fastapi_notification.models.notification import Notification
from fastapi_notification.repository.manager.notification import (
    NotificationDataAccessLayer,
)
from fastapi_notification.settings.conf import configure, reset_config

pytestmark = [pytest.mark.models, pytest.mark.models_content_type]


class UUIDReference(AuthBase):
    """Small host model with a UUID primary key for generic-relation tests."""

    __tablename__ = "issue5_uuid_reference"
    __app_label__ = "issue5"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)


class StringReference(AuthBase):
    """Small host model with an opaque string primary key."""

    __tablename__ = "issue5_string_reference"
    __app_label__ = "issue5"

    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)


class CompositeReference(AuthBase):
    """Model used to document the generic relation single-PK limitation."""

    __tablename__ = "issue5_composite_reference"
    __app_label__ = "issue5"

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(50), primary_key=True)


def test_normalize_object_id_accepts_integer_uuid_and_string() -> None:
    """Supported identifier types share a stable textual representation."""
    identifier = uuid4()

    assert normalize_object_id(42) == "42"
    assert normalize_object_id(identifier) == str(identifier)
    assert normalize_object_id("post:alpha/2026") == "post:alpha/2026"


@pytest.mark.parametrize("identifier", [True, 1.5, None, b"binary-id"])
def test_normalize_object_id_rejects_unsupported_types(identifier: object) -> None:
    """Unsupported identifiers fail early instead of being stored ambiguously."""
    with pytest.raises(TypeError, match="integers, UUIDs or strings"):
        normalize_object_id(identifier)


def test_coerce_object_id_restores_integer_primary_key_type() -> None:
    """Integer identifiers are converted back before SQLAlchemy lookup."""
    assert coerce_object_id(User, "42") == 42
    assert isinstance(coerce_object_id(User, "42"), int)


def test_coerce_object_id_restores_uuid_primary_key_type() -> None:
    """UUID text is converted back to uuid.UUID."""
    identifier = uuid4()

    resolved = coerce_object_id(UUIDReference, str(identifier))

    assert resolved == identifier
    assert isinstance(resolved, UUID)


def test_coerce_object_id_preserves_string_primary_key_type() -> None:
    """String identifiers remain byte-for-byte unchanged."""
    identifier = "post:alpha/2026"

    assert coerce_object_id(StringReference, identifier) == identifier


def test_coerce_object_id_rejects_invalid_uuid() -> None:
    """Malformed UUID values cannot reach the database lookup."""
    with pytest.raises(ValueError):
        coerce_object_id(UUIDReference, "not-a-uuid")


def test_coerce_object_id_rejects_composite_primary_keys() -> None:
    """Generic relations require a single-column primary key."""
    with pytest.raises(TypeError, match="single-column primary key"):
        coerce_object_id(CompositeReference, "record-1")


def test_generic_object_id_columns_use_text_storage() -> None:
    """Generic object IDs can store every supported identifier representation."""
    assert isinstance(Notification.__table__.c.actor_object_id.type, Text)
    assert isinstance(Notification.__table__.c.target_object_id.type, Text)
    assert isinstance(Notification.__table__.c.action_object_object_id.type, Text)


def test_notification_model_normalizes_generic_ids_on_direct_assignment() -> None:
    """Direct ORM construction accepts the supported Python identifier types."""
    uuid_identifier = uuid4()
    notification = Notification(
        verb="linked",
        actor_content_type_id=1,
        actor_object_id=42,
        target_object_id=uuid_identifier,
        action_object_object_id="external:record/alpha",
    )

    assert notification.actor_object_id == "42"
    assert notification.target_object_id == str(uuid_identifier)
    assert notification.action_object_object_id == "external:record/alpha"


def test_notification_model_rejects_missing_actor_identifier() -> None:
    """An actor relation cannot be created without its primary key."""
    with pytest.raises(TypeError, match="requires an object ID"):
        Notification(
            verb="linked",
            actor_content_type_id=1,
            actor_object_id=None,
        )


async def test_content_type_resolves_uuid_primary_key(
    session: AsyncSession,
) -> None:
    """A UUID-backed model resolves from its stored textual object ID."""
    identifier = uuid4()
    instance = UUIDReference(id=identifier, label="UUID object")
    session.add(instance)
    await session.flush()

    content_type = await ContentType.get_for_model(session, UUIDReference)
    loaded = await content_type.get_object_for_this_type(session, str(identifier))

    assert loaded is instance
    assert isinstance(loaded.id, UUID)


async def test_content_type_resolves_string_primary_key(
    session: AsyncSession,
) -> None:
    """A string-backed model resolves opaque identifiers without alteration."""
    identifier = "post:alpha/2026"
    instance = StringReference(id=identifier, label="String object")
    session.add(instance)
    await session.flush()

    content_type = await ContentType.get_for_model(session, StringReference)
    loaded = await content_type.get_object_for_this_type(session, identifier)

    assert loaded is instance
    assert loaded.id == identifier


async def test_content_type_returns_none_for_invalid_typed_identifier(
    session: AsyncSession,
) -> None:
    """An invalid stored identifier is treated as an unresolved relation."""
    content_type = await ContentType.get_for_model(session, UUIDReference)

    assert await content_type.get_object_for_this_type(session, "not-a-uuid") is None


async def test_content_type_rejects_composite_primary_key_models(
    session: AsyncSession,
) -> None:
    """Unsupported generic relation models fail clearly during resolution."""
    content_type = await ContentType.get_for_model(session, CompositeReference)

    with pytest.raises(TypeError, match="single-column primary key"):
        await content_type.get_object_for_this_type(session, "record-1")


async def test_generic_relations_round_trip_integer_uuid_and_string_ids(
    session: AsyncSession,
    dal: NotificationDataAccessLayer,
    user: User,
) -> None:
    """All supported PK types survive notification persistence and resolution."""
    uuid_identifier = uuid4()
    uuid_object = UUIDReference(id=uuid_identifier, label="UUID target")
    string_object = StringReference(
        id="comment:alpha/2026", label="String action object"
    )
    session.add_all([uuid_object, string_object])
    await session.flush()

    notification = await dal.create_notification(
        verb="referenced",
        actor=user,
        target=uuid_object,
        action_object=string_object,
    )

    assert notification.actor_object_id == str(user.id)
    assert notification.target_object_id == str(uuid_identifier)
    assert notification.action_object_object_id == "comment:alpha/2026"

    notification_id = notification.id
    await session.commit()
    session.expunge(notification)

    reloaded = await session.get(Notification, notification_id)
    assert reloaded is not None
    await reloaded.resolve_generic_relations(session)

    assert reloaded.actor.id == user.id
    assert isinstance(reloaded.actor.id, int)
    assert reloaded.target.id == uuid_identifier
    assert isinstance(reloaded.target.id, UUID)
    assert reloaded.action_object.id == "comment:alpha/2026"
    assert isinstance(reloaded.action_object.id, str)


def test_dynamic_serializer_emits_generic_ids_as_strings() -> None:
    """Configured API fields serialize normalized generic identifiers."""
    configure(
        SERIALIZER_FIELDS=[
            "actor_object_id",
            "target_object_id",
            "action_object_object_id",
        ]
    )
    instance = SimpleNamespace(
        actor_object_id="42",
        target_object_id="c2b5a0e2-65e8-4f16-a7d5-27d8b8e0a001",
        action_object_object_id="external:record/alpha",
    )

    try:
        payload = NotificationDynamicSerializer.to_representation(instance)
    finally:
        reset_config()

    assert payload == {
        "actor_object_id": "42",
        "target_object_id": "c2b5a0e2-65e8-4f16-a7d5-27d8b8e0a001",
        "action_object_object_id": "external:record/alpha",
    }
