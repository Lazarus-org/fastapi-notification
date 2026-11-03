"""Built-in notification categories and priority levels."""

import re
from enum import Enum
from typing import Any, List, Tuple


class NotificationCategory(str, Enum):
    """Built-in category keys; applications may also use custom category keys."""

    GENERAL = "general"
    SYSTEM = "system"
    SECURITY = "security"
    SOCIAL = "social"
    FINANCIAL = "financial"
    ORDERS = "orders"
    MARKETING = "marketing"

    @classmethod
    def choices(cls) -> List[Tuple[str, str]]:
        """Return built-in category keys and display labels."""
        return [
            (member.value, member.value.replace("_", " ").title()) for member in cls
        ]

    @classmethod
    def values(cls) -> List[str]:
        """Return built-in category keys."""
        return [member.value for member in cls]


class NotificationPriority(str, Enum):
    """Priority levels ordered from least to most urgent."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

    @classmethod
    def choices(cls) -> List[Tuple[str, str]]:
        """Return priority keys and human-readable labels."""
        return [(member.value, member.value.title()) for member in cls]

    @classmethod
    def values(cls) -> List[str]:
        """Return supported priority keys."""
        return [member.value for member in cls]


_CATEGORY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def normalize_category(value: Any) -> str:
    """Normalize and validate a built-in or application-defined category key.

    Category keys are case-insensitive on input and persisted in lowercase. Namespaced
    custom keys such as ``com.example.billing`` are supported.
    """
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str):
        raise TypeError("category must be a string or NotificationCategory.")
    normalized = value.strip().lower()
    if not _CATEGORY_PATTERN.fullmatch(normalized):
        raise ValueError(
            "category must be 1 to 64 characters and contain only lowercase "
            "letters, numbers, dots, underscores or hyphens."
        )
    return normalized


def normalize_priority(value: Any) -> str:
    """Normalize and validate a supported priority value."""
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str):
        raise TypeError("priority must be a string or NotificationPriority.")
    normalized = value.strip().lower()
    if normalized not in NotificationPriority.values():
        raise ValueError(
            "priority must be one of: " + ", ".join(NotificationPriority.values()) + "."
        )
    return normalized
