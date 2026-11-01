from typing import Any, List, Type

from sqlalchemy import inspect


def get_serializable_model_fields(model: Type[Any]) -> List[str]:
    """Return every field name of a model that can be serialized.

    Covers mapped columns, ORM relationships, and explicitly declared transient
    identity projections. Together these are the names accepted by serializer
    field settings.

    Args:
        model (Type[Any]): The SQLAlchemy model class.

    Returns:
        list: A list of serializable field names on the model.
    """
    mapper = inspect(model)

    serializable_fields = [column.key for column in mapper.columns]
    serializable_fields.extend(
        relationship.key for relationship in mapper.relationships
    )
    serializable_fields.extend(
        field
        for field in getattr(model, "__serializable_identity_fields__", ())
        if field not in serializable_fields
    )

    return serializable_fields
