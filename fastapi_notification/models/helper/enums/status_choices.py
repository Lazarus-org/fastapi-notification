from enum import Enum
from typing import List, Tuple


class NotificationStatus(str, Enum):
    """The set of statuses a notification can carry.

    Mirrors the semantics of a Django ``TextChoices`` enumeration: members are plain
    strings, so they serialize and persist transparently, while :meth:`choices` exposes
    the human readable label for each value.
    """

    ERROR = "ERROR"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    INFO = "INFO"
    CRITICAL = "CRITICAL"
    SENSITIVE = "SENSITIVE"
    INFRASTRUCTURE = "INFRASTRUCTURE"

    @property
    def label(self) -> str:
        """Return the human readable description of the status.

        Returns:
            str: The descriptive label for this status member.
        """
        return _LABELS[self.value]

    @classmethod
    def choices(cls) -> List[Tuple[str, str]]:
        """Return every status as a ``(value, label)`` pair.

        Returns:
            List[Tuple[str, str]]: The available statuses and their labels.
        """
        return [(member.value, member.label) for member in cls]

    @classmethod
    def values(cls) -> List[str]:
        """Return every status value.

        Returns:
            List[str]: The available status values.
        """
        return [member.value for member in cls]


_LABELS = {
    "ERROR": "Error - Indicates critical errors that require immediate attention",
    "SUCCESS": "Success - Indicates successful completion of an operation",
    "WARNING": (
        "Warning - Indicates potential issues or concerns that should be addressed"
    ),
    "INFO": "Information - Provides general informational messages",
    "CRITICAL": "Critical - Indicates critical issues that may impact functionality",
    "SENSITIVE": "Sensitive - Indicates notifications related to sensitive data",
    "INFRASTRUCTURE": (
        "Infrastructure - Indicates notifications related to system infrastructure"
    ),
}
