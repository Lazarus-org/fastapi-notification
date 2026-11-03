from typing import Any, Dict, Iterable, List

from pydantic import BaseModel, ConfigDict

from fastapi_notification.settings.conf import config
from fastapi_notification.utils.serialization import filter_non_empty_fields


class BaseSerializer(BaseModel):
    """Base class for every serializer the package exposes.

    Reads from ORM instances as well as plain mappings, and honours the
    ``SERIALIZER_EXCLUDE_NULL_FIELDS`` setting when producing output.
    """

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def to_representation(cls, instance: Any) -> Dict[str, Any]:
        """Serialize a single instance into a dictionary.

        Args:
            instance (Any): The ORM instance, or mapping, to serialize.

        Returns:
            Dict[str, Any]: The serialized representation, with null fields
            stripped when the setting asks for it.
        """
        data = cls.model_validate(instance).model_dump()

        if config.exclude_serializer_null_fields:
            return filter_non_empty_fields(data)

        return data

    @classmethod
    def to_representation_many(cls, instances: Iterable[Any]) -> List[Dict[str, Any]]:
        """Serialize many instances into a list of dictionaries.

        Args:
            instances (Iterable[Any]): The instances to serialize.

        Returns:
            List[Dict[str, Any]]: The serialized representations.
        """
        return [cls.to_representation(instance) for instance in instances]
