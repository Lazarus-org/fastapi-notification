"""Safe, deliberately small template interpolation for notification text."""

import re
from string import Formatter
from typing import Any, Mapping, Optional

_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FORMATTER = Formatter()


def validate_template(template: str) -> None:
    """Reject attribute access, indexing, conversions and format expressions."""
    if not isinstance(template, str):
        raise TypeError("Template content must be a string.")
    parsed = _FORMATTER.parse(template)
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if not _FIELD.fullmatch(field_name):
            raise ValueError(
                "Template variables must be simple identifiers; attribute "
                "and item access are not supported."
            )
        if format_spec or conversion:
            raise ValueError("Template format specifications are not supported.")


def render_template(template: str, context: Optional[Mapping[str, Any]] = None) -> str:
    """Render simple ``{variable}`` placeholders without evaluating expressions."""
    validate_template(template)
    if context is not None and not isinstance(context, Mapping):
        raise TypeError("Template context must be a mapping.")
    values = context or {}
    output = []
    for literal, field_name, format_spec, conversion in _FORMATTER.parse(template):
        del format_spec, conversion
        output.append(literal)
        if field_name is None:
            continue
        if field_name not in values:
            raise ValueError(f"Missing template variable: {field_name}")
        value = values[field_name]
        if value is None:
            raise ValueError(f"Template variable {field_name!r} cannot be None.")
        output.append(str(value))
    return "".join(output)


__all__ = ["render_template", "validate_template"]
