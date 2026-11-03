from typing import Any, Dict

from fastapi_notification.utils.naturaltime import naturaltime


def generate_title(notification: Dict[str, Any]) -> str:
    """Generate the title for a notification represented as a dictionary.

    Used when the data access layer returns partial rows rather than full model
    instances.

    Args:
        notification (dict): A dictionary representing the notification row.

    Returns:
        str: The title of the notification, including its description and the
        time elapsed since the timestamp.

    Raises:
        ValueError: If no description is present, or the argument is not a
            mapping with ``description`` and ``timestamp`` keys.
    """
    try:
        description = notification.get("description")
        if description:
            timestamp = notification.get("timestamp")
            if timestamp:
                time_since = naturaltime(timestamp)
                return f"{description} {time_since}"

            return description

        raise ValueError("No description provided.")

    except AttributeError as e:
        raise ValueError(
            "The notification must be a dictionary with 'description' and 'timestamp'"
            " keys."
        ) from e
