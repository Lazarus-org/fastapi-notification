from typing import Any, List

from fastapi_notification.identity import get_identity_adapter
from fastapi_notification.models.notification import Notification
from fastapi_notification.settings.conf import config
from fastapi_notification.utils.get_model_fields import get_serializable_model_fields
from fastapi_notification.validators.config_validators import (
    Error,
    validate_boolean_setting,
    validate_list_fields,
    validate_optional_class_setting,
    validate_permission_class_setting,
    validate_throttle_rate,
)


class ImproperlyConfigured(Exception):
    """Raised when the package configuration is invalid.

    Attributes:
        errors (List[Error]): Every problem found, so they can be fixed in one
            pass rather than one at a time.

    """

    def __init__(self, errors: List[Error]) -> None:
        self.errors = errors
        joined = "\n".join(f"  - {error}" for error in errors)
        super().__init__(
            f"fastapi-notification is improperly configured:\n{joined}"
        )


# pylint: disable=too-many-statements
def check_notification_settings(**kwargs: Any) -> List[Error]:
    """Validate every notification setting and report what is wrong.

    Args:
        **kwargs (Any): Accepted for forward compatibility; unused.

    Returns:
        List[Error]: A list of errors for any detected configuration issues.

    """
    errors: List[Error] = []

    identity_setting_name = f"{config.prefix}IDENTITY_ADAPTER"
    identity_setting_value = config.get_setting(identity_setting_name, None)
    if (
        isinstance(identity_setting_value, (str, type))
        or identity_setting_value is None
    ):
        errors.extend(
            validate_optional_class_setting(
                identity_setting_value, identity_setting_name
            )
        )

    if config.identity_adapter is None:
        errors.append(
            Error(
                "The identity adapter is not configured.",
                hint=(
                    "Set IDENTITY_ADAPTER to an IdentityAdapter class or an "
                    "importable class path."
                ),
                id=f"fastapi_notification.E015_{config.prefix}IDENTITY_ADAPTER",
            )
        )
    else:
        try:
            get_identity_adapter()
        except Exception as error:
            errors.append(
                Error(
                    f"The configured identity adapter is invalid: {error}",
                    hint="Configure a class implementing the IdentityAdapter contract.",
                    id=f"fastapi_notification.E016_{config.prefix}IDENTITY_ADAPTER",
                )
            )

    errors.extend(
        validate_boolean_setting(
            config.include_soft_delete, f"{config.prefix}API_INCLUDE_SOFT_DELETE"
        )
    )
    errors.extend(
        validate_boolean_setting(
            config.include_hard_delete, f"{config.prefix}API_INCLUDE_HARD_DELETE"
        )
    )
    errors.extend(
        validate_boolean_setting(
            config.include_serializer_full_details,
            f"{config.prefix}SERIALIZER_INCLUDE_FULL_DETAILS",
        )
    )
    errors.extend(
        validate_boolean_setting(
            config.exclude_serializer_null_fields,
            f"{config.prefix}SERIALIZER_EXCLUDE_NULL_FIELDS",
        )
    )
    errors.extend(
        validate_boolean_setting(
            config.api_allow_list, f"{config.prefix}API_ALLOW_LIST"
        )
    )
    errors.extend(
        validate_boolean_setting(
            config.api_allow_retrieve, f"{config.prefix}API_ALLOW_RETRIEVE"
        )
    )

    errors.extend(
        validate_list_fields(
            config.notification_serializer_fields,
            f"{config.prefix}SERIALIZER_FIELDS",
            available_fields=["title"]
            + get_serializable_model_fields(Notification),
            allow_none=True,
        )
    )
    errors.extend(
        validate_list_fields(
            config.user_serializer_fields, f"{config.prefix}USER_SERIALIZER_FIELDS"
        )
    )
    errors.extend(
        validate_list_fields(
            config.api_ordering_fields, f"{config.prefix}API_ORDERING_FIELDS"
        )
    )
    errors.extend(
        validate_list_fields(
            config.api_search_fields, f"{config.prefix}API_SEARCH_FIELDS"
        )
    )

    errors.extend(
        validate_throttle_rate(
            config.staff_user_throttle_rate,
            f"{config.prefix}STAFF_USER_THROTTLE_RATE",
        )
    )
    errors.extend(
        validate_throttle_rate(
            config.authenticated_user_throttle_rate,
            f"{config.prefix}AUTHENTICATED_USER_THROTTLE_RATE",
        )
    )

    for setting_name in (
        "SERIALIZER_CLASS",
        "USER_SERIALIZER_CLASS",
        "GROUP_SERIALIZER_CLASS",
        "API_THROTTLE_CLASS",
        "API_PAGINATION_CLASS",
        "API_FILTERSET_CLASS",
    ):
        qualified = f"{config.prefix}{setting_name}"
        errors.extend(
            validate_optional_class_setting(
                config.get_setting(qualified, None), qualified
            )
        )

    errors.extend(
        validate_permission_class_setting(
            config.get_setting(
                f"{config.prefix}API_EXTRA_PERMISSION_CLASS", None
            ),
            f"{config.prefix}API_EXTRA_PERMISSION_CLASS",
        )
    )

    return errors


def run_checks() -> None:
    """Validate the settings and raise if any of them are wrong.

    Called when a router is built, so misconfiguration surfaces at startup
    rather than on the first request.

    Raises:
        ImproperlyConfigured: If any setting fails validation.

    """
    errors = check_notification_settings()
    if errors:
        raise ImproperlyConfigured(errors)
