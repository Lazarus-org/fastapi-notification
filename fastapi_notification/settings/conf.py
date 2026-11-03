import json
import os
from typing import Any, Dict, List, Optional, Type, Union, cast

from fastapi_notification.constants.default_settings import (
    default_api_settings,
    default_pagination_and_filter_settings,
    default_serializer_settings,
    default_throttle_settings,
)
from fastapi_notification.utils.module_loading import import_string

# Values accepted, case insensitively, as booleans when read from the process
# environment.
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

# Explicit overrides registered through ``configure()``. These take precedence
# over the environment so a host application can drive the package entirely from
# Python.
_overrides: Dict[str, Any] = {}


def _parse_environment_value(raw: str, default_value: Any) -> Any:
    """Coerce a raw environment string into the type implied by the default.

    Args:
        raw (str): The raw string read from the environment.
        default_value (Any): The default the setting falls back to, used to
            decide the target type.

    Returns:
        Any: The coerced value, or the raw string when no coercion applies.
    """
    if isinstance(default_value, bool):
        lowered = raw.strip().lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
        return raw

    if isinstance(default_value, list) or default_value is None:
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    return raw


def configure(**settings: Any) -> "NotificationConfig":
    """Set package settings from Python and rebuild the active configuration.

    This is the programmatic counterpart to defining settings in the
    environment, and is the more convenient option for applications that already
    centralise their configuration in code.

    Args:
        **settings (Any): Setting names, with or without the
            ``FASTAPI_NOTIFICATION_`` prefix, mapped to their values.

    Returns:
        NotificationConfig: The rebuilt configuration, which is also the active
        one.
    """
    for name, value in settings.items():
        key = (
            name
            if name.startswith(NotificationConfig.prefix)
            else (f"{NotificationConfig.prefix}{name}")
        )
        _overrides[key.upper()] = value

    return reload_config()


def reset_config() -> "NotificationConfig":
    """Discard every programmatic override and rebuild the configuration.

    Returns:
        NotificationConfig: The rebuilt configuration, which is also the active
        one.
    """
    _overrides.clear()
    return reload_config()


# pylint: disable=too-many-instance-attributes
class NotificationConfig:
    """A configuration handler for the FastAPI Notification API.

    Settings are resolved in order of precedence: values registered through
    :func:`configure`, then environment variables, then the packaged defaults.

    Attributes:
        identity_adapter (Type[Any]): The adapter integrating host identities.
        include_soft_delete (bool): Whether soft delete is enabled for notifications.
        include_hard_delete (bool): Whether hard delete is enabled for notifications.
        include_serializer_full_details (bool): Whether full details are included in the serializer.
        exclude_serializer_null_fields (bool): Whether null fields are stripped from responses.
        api_allow_list (bool): Whether the API allows listing notifications.
        api_allow_retrieve (bool): Whether the API allows retrieving single notifications.
        notification_serializer_fields (Optional[List[str]]): Fields included in the notification serializer.
        notification_serializer_class (Optional[Type[Any]]): The class used for Notification serialization.
        user_serializer_fields (List[str]): Fields included in the user serializer.
        user_serializer_class (Optional[Type[Any]]): The class used for User serialization.
        group_serializer_class (Optional[Type[Any]]): The class used for Group serialization.
        authenticated_user_throttle_rate (str): Throttle rate for authenticated users.
        staff_user_throttle_rate (str): Throttle rate for staff users.
        api_throttle_class (Optional[Type[Any]]): The class used for request throttling.
        api_pagination_class (Optional[Type[Any]]): The class used for pagination.
        api_extra_permission_class (Optional[Type[Any]]): An additional permission dependency.
        api_filterset_class (Optional[Type[Any]]): The class used for filtering.
        api_ordering_fields (List[str]): Fields that can be used for ordering.
        api_search_fields (List[str]): Fields that can be searched.
    """

    prefix = "FASTAPI_NOTIFICATION_"

    def __init__(self) -> None:
        """Load every setting from the overrides, environment or defaults."""
        self.identity_adapter: Any = self.get_optional_classes(
            f"{self.prefix}IDENTITY_ADAPTER",
            default_api_settings.identity_adapter,
        )
        self.include_soft_delete: bool = self.get_setting(
            f"{self.prefix}API_INCLUDE_SOFT_DELETE",
            default_api_settings.include_soft_delete,
        )
        self.include_hard_delete: bool = self.get_setting(
            f"{self.prefix}API_INCLUDE_HARD_DELETE",
            default_api_settings.include_hard_delete,
        )
        self.include_serializer_full_details: bool = self.get_setting(
            f"{self.prefix}SERIALIZER_INCLUDE_FULL_DETAILS",
            default_api_settings.include_serializer_full_details,
        )
        self.exclude_serializer_null_fields: bool = self.get_setting(
            f"{self.prefix}SERIALIZER_EXCLUDE_NULL_FIELDS",
            default_api_settings.exclude_serializer_none_fields,
        )
        self.api_allow_list: bool = self.get_setting(
            f"{self.prefix}API_ALLOW_LIST", default_api_settings.allow_list
        )
        self.api_allow_retrieve: bool = self.get_setting(
            f"{self.prefix}API_ALLOW_RETRIEVE",
            default_api_settings.allow_retrieve,
        )
        self.notification_serializer_fields: Optional[List[str]] = self.get_setting(
            f"{self.prefix}SERIALIZER_FIELDS",
            None,
        )
        self.notification_serializer_class: Optional[Type[Any]] = (
            self._get_class_setting(
                f"{self.prefix}SERIALIZER_CLASS",
                default_serializer_settings.notification_serializer_class,
            )
        )
        self.user_serializer_fields: List[str] = self.get_setting(
            f"{self.prefix}USER_SERIALIZER_FIELDS",
            default_serializer_settings.user_serializer_fields,
        )
        self.user_serializer_class: Optional[Type[Any]] = self._get_class_setting(
            f"{self.prefix}USER_SERIALIZER_CLASS",
            default_serializer_settings.user_serializer_class,
        )
        self.group_serializer_class: Optional[Type[Any]] = self._get_class_setting(
            f"{self.prefix}GROUP_SERIALIZER_CLASS",
            default_serializer_settings.group_serializer_class,
        )
        self.authenticated_user_throttle_rate: str = self.get_setting(
            f"{self.prefix}AUTHENTICATED_USER_THROTTLE_RATE",
            default_throttle_settings.authenticated_user_throttle_rate,
        )
        self.staff_user_throttle_rate: str = self.get_setting(
            f"{self.prefix}STAFF_USER_THROTTLE_RATE",
            default_throttle_settings.staff_user_throttle_rate,
        )
        self.api_throttle_class: Optional[Type[Any]] = self._get_class_setting(
            f"{self.prefix}API_THROTTLE_CLASS",
            default_throttle_settings.throttle_class,
        )
        self.api_pagination_class: Optional[Type[Any]] = self._get_class_setting(
            f"{self.prefix}API_PAGINATION_CLASS",
            default_pagination_and_filter_settings.pagination_class,
        )
        self.api_extra_permission_class: Optional[Type[Any]] = self._get_class_setting(
            f"{self.prefix}API_EXTRA_PERMISSION_CLASS",
            default_api_settings.extra_permission_class,
        )
        self.api_filterset_class: Optional[Type[Any]] = self._get_class_setting(
            f"{self.prefix}API_FILTERSET_CLASS",
            default_pagination_and_filter_settings.filterset_class,
        )
        self.api_ordering_fields: List[str] = self.get_setting(
            f"{self.prefix}API_ORDERING_FIELDS",
            default_pagination_and_filter_settings.ordering_fields,
        )
        self.api_search_fields: List[str] = self.get_setting(
            f"{self.prefix}API_SEARCH_FIELDS",
            default_pagination_and_filter_settings.search_fields,
        )

    def get_setting(self, setting_name: str, default_value: Any) -> Any:
        """Retrieve a setting, falling back to the supplied default.

        Args:
            setting_name (str): The name of the setting to retrieve.
            default_value (Any): The value to return if the setting is not set.

        Returns:
            Any: The value of the setting or the default value if not found.
        """
        if setting_name in _overrides:
            return _overrides[setting_name]

        raw = os.environ.get(setting_name)
        if raw is None:
            return default_value

        return _parse_environment_value(raw, default_value)

    def _get_class_setting(
        self, setting_name: str, default_path: Optional[Union[str, List[str]]]
    ) -> Optional[Type[Any]]:
        """View a validated single-class setting from the generic import boundary.

        The public loader also supports lists. Single-class settings are validated by
        the startup checks; invalid raw values remain intact for those checks. Imported
        host classes have no common nominal base class.
        """
        return cast(
            Optional[Type[Any]], self.get_optional_classes(setting_name, default_path)
        )

    def get_optional_classes(
        self,
        setting_name: str,
        default_path: Optional[Union[str, List[str]]],
    ) -> Optional[Union[Type[Any], List[Type[Any]]]]:
        """Resolve a setting holding one or more importable class paths.

        A value that is already a class, rather than a path, is returned as is,
        so settings can be supplied directly in Python.

        Args:
            setting_name (str): The name of the setting for the class path.
            default_path (Optional[Union[str, List[str]]]): The default import
                path, or list of paths, for the class.

        Returns:
            Optional[Union[Type[Any], List[Type[Any]]]]: The imported class or
            classes, or ``None`` if the import fails or the path is invalid.
        """
        class_path: Any = self.get_setting(setting_name, default_path)

        if class_path and isinstance(class_path, str):
            try:
                return import_string(class_path)
            except ImportError:
                return None
        elif class_path and isinstance(class_path, list):
            try:
                return [
                    import_string(cls_path)
                    for cls_path in class_path
                    if isinstance(cls_path, str)
                ]
            except ImportError:
                return []
        elif class_path and not isinstance(class_path, (str, list)):
            return class_path

        return None


config = NotificationConfig()


def reload_config() -> NotificationConfig:
    """Rebuild the active configuration in place.

    The module level ``config`` object is mutated rather than replaced, so
    modules that imported it keep seeing the current values.

    Returns:
        NotificationConfig: The active configuration.
    """
    fresh = NotificationConfig()
    config.__dict__.update(fresh.__dict__)
    return config
