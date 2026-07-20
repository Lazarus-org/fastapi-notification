from typing import Any, List, Type

from sqlalchemy import inspect


def get_serializable_model_fields(model: Type[Any]) -> List[str]:
    """Return every field name of a model that can be serialized.

    Covers the mapped columns as well as the relationships declared on the
    model, which together form the set of names accepted by the serializer field
    settings.

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

    return serializable_fields
