from typing import Any, Dict, List, Union

from fastapi_notification.constants.default_settings import default_serializer_settings
from fastapi_notification.settings.conf import config
from fastapi_notification.utils.serialization import (
    filter_non_empty_fields,
    generate_title,
)


class NotificationDynamicSerializer:
    """Serializer that selects its fields from configuration.

    When ``SERIALIZER_FIELDS`` is set, exactly those fields are returned; otherwise a
    ``title`` is returned alongside the default summary fields.

    Rows arrive either as notification instances or as the plain mappings the data
    access layer returns for summary queries, and both are handled.
    """

    @classmethod
    def fields(cls) -> List[str]:
        """Return the field names this serializer emits.

        Returns:
            List[str]: The configured fields, or the packaged defaults.
        """
        return config.notification_serializer_fields or [
            "title",
            *(default_serializer_settings.notification_serializer_fields or []),
        ]

    @classmethod
    def get_title(cls, notification: Union[Any, Dict[str, Any]]) -> str:
        """Generate the title for a notification.

        Args:
            notification (Union[Any, Dict[str, Any]]): The notification instance
                or its mapping representation.

        Returns:
            str: The generated title.
        """
        if config.notification_serializer_fields:
            return str(notification)

        if isinstance(notification, dict):
            return generate_title(notification)

        return str(notification)

    @classmethod
    def to_representation(cls, instance: Union[Any, Dict[str, Any]]) -> Dict[str, Any]:
        """Serialize a notification into a dictionary of the configured fields.

        Args:
            instance (Union[Any, Dict[str, Any]]): The notification instance or
                mapping to serialize.

        Returns:
            Dict[str, Any]: The serialized representation.
        """
        data: Dict[str, Any] = {}

        for field in cls.fields():
            if field == "title":
                data["title"] = cls.get_title(instance)
                continue

            if isinstance(instance, dict):
                data[field] = instance.get(field)
            else:
                data[field] = getattr(instance, field, None)

        if config.exclude_serializer_null_fields:
            return filter_non_empty_fields(data)

        return data

    @classmethod
    def to_representation_many(cls, instances: Any) -> List[Dict[str, Any]]:
        """Serialize many notifications into a list of dictionaries.

        Args:
            instances (Any): The notifications to serialize.

        Returns:
            List[Dict[str, Any]]: The serialized representations.
        """
        return [cls.to_representation(instance) for instance in instances]
