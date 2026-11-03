"""Database schema checks for localized templates."""

from sqlalchemy import UniqueConstraint, create_engine

from fastapi_notification.models import Base, Notification, NotificationTemplate


def test_template_model_has_unique_key_locale_constraint() -> None:
    constraints = Base.metadata.tables["notification_template"].constraints
    unique_pairs = {
        tuple(column.name for column in constraint.columns)
        for constraint in constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("key", "locale") in unique_pairs


def test_notification_persists_template_provenance() -> None:
    assert "template_key" in Notification.__table__.columns
    assert "locale" in Notification.__table__.columns
    assert Notification.__table__.columns.template_key.nullable is True
    assert Notification.__table__.columns.locale.nullable is True


def test_metadata_can_be_created_repeatedly_with_template_indexes() -> None:
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
