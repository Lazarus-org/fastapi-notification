"""Tests for safe localized notification template primitives."""

import pytest

from fastapi_notification.models.notification_template import (
    normalize_locale,
    normalize_template_key,
)
from fastapi_notification.utils.templates import render_template, validate_template


def test_render_template_substitutes_simple_variables():
    assert render_template(
        "Order {order_number} paid by {customer}",
        {"order_number": "A-42", "customer": "Alex"},
    ) == "Order A-42 paid by Alex"


def test_render_template_preserves_escaped_braces():
    assert render_template("Use {{order_number}} literally") == (
        "Use {order_number} literally"
    )


def test_render_template_rejects_missing_variables():
    with pytest.raises(ValueError, match="Missing template variable"):
        render_template("Hello {name}", {})


def test_render_template_rejects_none_values():
    with pytest.raises(ValueError, match="cannot be None"):
        render_template("Hello {name}", {"name": None})


@pytest.mark.parametrize(
    "template",
    ["{user.name}", "{user[0]}", "{value!r}", "{value:>10}"],
)
def test_validate_template_rejects_expressions(template):
    with pytest.raises(ValueError):
        validate_template(template)


def test_validate_template_rejects_unmatched_braces():
    with pytest.raises(ValueError):
        validate_template("Hello {name")


def test_normalize_locale_supports_language_region():
    assert normalize_locale("fa_ir") == "fa-IR"
    assert normalize_locale("EN-us") == "en-US"


def test_normalize_locale_rejects_invalid_value():
    with pytest.raises(ValueError):
        normalize_locale("not a locale")


def test_normalize_template_key_normalizes_case_and_whitespace():
    assert normalize_template_key(" Orders.Payment_Received ") == (
        "orders.payment_received"
    )


def test_normalize_template_key_rejects_invalid_value():
    with pytest.raises(ValueError):
        normalize_template_key("../unsafe")


def test_render_template_rejects_non_mapping_context():
    with pytest.raises(TypeError, match="must be a mapping"):
        render_template("Hello {name}", ["Alex"])


def test_template_model_normalizes_fields_on_assignment():
    from fastapi_notification.models.notification_template import NotificationTemplate

    template = NotificationTemplate(
        key=" Orders.Paid ",
        locale="en_us",
        category="Orders",
        verb_template="paid",
        description_template="Order {number} paid",
    )

    assert template.key == "orders.paid"
    assert template.locale == "en-US"
    assert template.category == "orders"


def test_template_model_rejects_unsafe_template_on_assignment():
    from fastapi_notification.models.notification_template import NotificationTemplate

    with pytest.raises(ValueError):
        NotificationTemplate(
            key="orders.paid",
            locale="en",
            verb_template="paid",
            description_template="Hello {user.name}",
        )


def test_validate_template_rejects_non_string_input():
    with pytest.raises(TypeError, match="must be a string"):
        validate_template(None)


def test_normalizers_reject_non_string_values():
    from fastapi_notification.models.notification_template import (
        normalize_locale,
        normalize_template_key,
    )

    with pytest.raises(TypeError):
        normalize_locale(None)
    with pytest.raises(TypeError):
        normalize_template_key(None)


def test_template_model_rejects_verb_longer_than_notification_column():
    from fastapi_notification.models.notification_template import NotificationTemplate

    with pytest.raises(ValueError, match="127 characters"):
        NotificationTemplate(
            key="orders.long",
            locale="en",
            verb_template="x" * 128,
        )
