from dataclasses import dataclass
from typing import Any, List, Optional

from fastapi_notification.utils.module_loading import import_string

VALID_TIME_UNITS = ["second", "minute", "hour", "day"]


@dataclass(frozen=True)
class Error:
    """A single configuration problem found during startup validation.

    Attributes:
        msg (str): What is wrong.
        hint (Optional[str]): How to fix it.
        id (str): A stable identifier for the class of problem.

    """

    msg: str
    id: str
    hint: Optional[str] = None

    def __str__(self) -> str:
        """Render the error as a single readable line.

        Returns:
            str: The message, identifier and hint if one is present.

        """
        rendered = f"({self.id}) {self.msg}"
        if self.hint:
            rendered = f"{rendered} HINT: {self.hint}"
        return rendered


def validate_boolean_setting(value: Any, config_name: str) -> List[Error]:
    """Validate that a setting holds a boolean.

    Args:
        value (Any): The value to validate.
        config_name (str): The name of the setting being validated.

    Returns:
        List[Error]: The errors found, empty when the value is valid.

    """
    errors: List[Error] = []
    if not isinstance(value, bool):
        errors.append(
            Error(
                f"{config_name} is not a boolean.",
                hint=f"Ensure {config_name} is either True or False.",
                id=f"fastapi_notification.E001_{config_name}",
            )
        )
    return errors


def validate_list_fields(
    fields: Any,
    config_name: str,
    available_fields: Optional[List] = None,
    allow_none: bool = False,
) -> List[Error]:
    """Validate that a setting holds a non-empty list of known field names.

    Args:
        fields (Any): The value to validate.
        config_name (str): The name of the setting being validated.
        available_fields (Optional[List]): The field names accepted, when the
            setting is restricted to a known set.
        allow_none (bool): Whether ``None`` is a valid value.

    Returns:
        List[Error]: The errors found, empty when the value is valid.

    """
    errors: List[Error] = []
    if allow_none and fields is None:
        return errors

    if not isinstance(fields, list):
        errors.append(
            Error(
                f"{config_name} is not a list.",
                hint=f"Ensure {config_name} is a list of fields.",
                id=f"fastapi_notification.E002_{config_name}",
            )
        )
    elif not fields:
        errors.append(
            Error(
                f"{config_name} is an empty list.",
                hint=f"Ensure {config_name} contains at least one field.",
                id=f"fastapi_notification.E003_{config_name}",
            )
        )
    else:
        for field in fields:
            if not isinstance(field, str):
                errors.append(
                    Error(
                        f"Invalid type in {config_name}: {field} is not a string.",
                        hint=f"Ensure all elements in {config_name} are strings.",
                        id=f"fastapi_notification.E004_{config_name}",
                    )
                )
            if available_fields and field not in available_fields:
                errors.append(
                    Error(
                        f"The field '{field}' in '{config_name}' is invalid.",
                        hint=(
                            f"Valid fields for '{config_name}' are: "
                            f"{', '.join(available_fields)}."
                        ),
                        id=f"fastapi_notification.E014_{config_name}",
                    )
                )

    return errors


def validate_throttle_rate(rate: Any, setting_name: str) -> List[Error]:
    """Validate that a throttle rate reads as ``{number}/{time_unit}``.

    Args:
        rate (Any): The throttle rate to validate, e.g. ``"10/minute"``.
        setting_name (str): The name of the setting being validated.

    Returns:
        List[Error]: The errors found, empty when the rate is valid.

    """
    errors: List[Error] = []
    if not isinstance(rate, str) or "/" not in rate:
        errors.append(
            Error(
                f"'{setting_name}' must be a string in the format 'number/time_unit'"
                " (e.g., '10/minute').",
                id="fastapi_notification.E005",
            )
        )
        return errors

    parts = rate.split("/")
    if len(parts) != 2:
        errors.append(
            Error(
                f"'{setting_name}' is not in the correct format. Expected"
                " 'number/time_unit'.",
                id="fastapi_notification.E006",
            )
        )
        return errors

    number, time_unit = parts

    if not number.isdigit():
        errors.append(
            Error(
                f"'{setting_name}' must start with a valid integer."
                f" Found: '{number}'.",
                id="fastapi_notification.E007",
            )
        )

    if time_unit not in VALID_TIME_UNITS:
        errors.append(
            Error(
                f"'{setting_name}' has an invalid time unit: '{time_unit}'.",
                hint=f"Valid time units are: {', '.join(VALID_TIME_UNITS)}.",
                id="fastapi_notification.E008",
            )
        )

    return errors


def validate_optional_class_setting(
    setting_value: Any, setting_name: str
) -> List[Error]:
    """Validate that a setting holds an importable class path.

    Args:
        setting_value (Any): The value to validate, typically a class path.
        setting_name (str): The name of the setting being validated.

    Returns:
        List[Error]: The errors found, empty when the value is valid.

    """
    errors: List[Error] = []

    if setting_value is None:
        return errors

    if isinstance(setting_value, type):
        return errors

    if not isinstance(setting_value, str):
        errors.append(
            Error(
                f"The setting '{setting_name}' must be a valid string representing a"
                " class path.",
                hint=(
                    f"Ensure '{setting_name}' is set to a string"
                    " (e.g., 'myapp.module.MyClass')."
                ),
                id=f"fastapi_notification.E009_{setting_name}",
            )
        )
        return errors

    try:
        import_string(setting_value)
    except ImportError:
        errors.append(
            Error(
                f"Cannot import the class from the setting '{setting_name}'.",
                hint=(
                    f"Ensure the class path '{setting_value}' is valid and importable."
                ),
                id=f"fastapi_notification.E010_{setting_name}",
            )
        )

    return errors


def validate_optional_classes_setting(
    setting_value: Any, setting_name: str
) -> List[Error]:
    """Validate that a setting holds a list of importable class paths.

    Args:
        setting_value (Any): The value to validate, typically a list of class
            paths.
        setting_name (str): The name of the setting being validated.

    Returns:
        List[Error]: The errors found, empty when the value is valid.

    """
    errors: List[Error] = []

    if setting_value is None:
        return errors

    if not isinstance(setting_value, list):
        errors.append(
            Error(
                f"Invalid type for setting '{setting_name}'.",
                hint=(
                    "The setting must be a list of strings."
                    " (e.g., ['myapp.module.MyClass'])"
                ),
                id=f"fastapi_notification.E011_{setting_name}",
            )
        )
        return errors

    for path in setting_value:
        if not isinstance(path, str):
            errors.append(
                Error(
                    f"Invalid type for class path in '{setting_name}'.",
                    hint=(
                        "Each item in the list must be a valid string representing a"
                        " class path."
                    ),
                    id=f"fastapi_notification.E012_{setting_name}",
                )
            )
        else:
            try:
                import_string(path)
            except ImportError:
                errors.append(
                    Error(
                        f"Cannot import the class from '{path}' in setting"
                        f" '{setting_name}'.",
                        hint=f"Ensure that '{path}' is a valid importable class path.",
                        id=f"fastapi_notification.E013_{setting_name}",
                    )
                )

    return errors


def validate_permission_class_setting(
    setting_value: Any, setting_name: str
) -> List[Error]:
    """Validate the no-argument callable class used for extra permissions.

    The package instantiates this class for each request and calls the resulting
    object with ``(request, user)``. Validate the import and construction
    contract during router startup instead of failing on the first request.
    """
    errors = validate_optional_class_setting(setting_value, setting_name)
    if errors or setting_value is None:
        return errors

    permission_class = (
        import_string(setting_value)
        if isinstance(setting_value, str)
        else setting_value
    )
    if not isinstance(permission_class, type):
        return [
            Error(
                f"The setting '{setting_name}' must resolve to a permission class.",
                hint=(
                    "Provide a class with a no-argument constructor and a "
                    "callable __call__(request, user) method."
                ),
                id=f"fastapi_notification.E017_{setting_name}",
            )
        ]

    try:
        permission = permission_class()
    except Exception as error:  # pylint: disable=broad-except
        return [
            Error(
                f"The permission class in '{setting_name}' cannot be instantiated: "
                f"{error}",
                hint=(
                    "Provide a permission class with a no-argument constructor; "
                    "request-specific data is supplied to __call__(request, user)."
                ),
                id=f"fastapi_notification.E018_{setting_name}",
            )
        ]

    if not callable(permission):
        return [
            Error(
                f"The permission class in '{setting_name}' is not callable.",
                hint="Implement __call__(request, user) on the permission class.",
                id=f"fastapi_notification.E019_{setting_name}",
            )
        ]

    return []
