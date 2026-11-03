"""Unit tests for localized template resolution using a lightweight session fake."""

from unittest.mock import AsyncMock, Mock

import pytest

from fastapi_notification.models.notification_template import NotificationTemplate
from fastapi_notification.repository.manager.templates import (
    NotificationTemplateDataAccessLayer,
)


@pytest.mark.asyncio
async def test_resolve_tries_exact_locale_then_base_language_then_default():
    session = AsyncMock()
    fa_template = NotificationTemplate(
        key="orders.payment_received",
        locale="fa",
        category="orders",
        verb_template="پرداخت دریافت شد",
        description_template="سفارش {number} پرداخت شد",
        is_active=True,
    )
    session.scalar.side_effect = [None, fa_template]

    result = await NotificationTemplateDataAccessLayer(session).resolve(
        "orders.payment_received", "fa-IR", "en"
    )

    assert result is fa_template
    assert session.scalar.await_count == 2


@pytest.mark.asyncio
async def test_resolve_uses_default_locale_when_base_language_missing():
    session = AsyncMock()
    english = NotificationTemplate(
        key="orders.payment_received",
        locale="en",
        category="orders",
        verb_template="payment received",
        is_active=True,
    )
    session.scalar.side_effect = [None, None, english]

    result = await NotificationTemplateDataAccessLayer(session).resolve(
        "orders.payment_received", "fa-IR", "en"
    )

    assert result is english
    assert session.scalar.await_count == 3


@pytest.mark.asyncio
async def test_resolve_raises_when_no_translation_or_fallback_exists():
    session = AsyncMock()
    session.scalar.return_value = None

    with pytest.raises(LookupError, match="No active template"):
        await NotificationTemplateDataAccessLayer(session).resolve(
            "orders.payment_received", "fa-IR", "en"
        )


@pytest.mark.asyncio
async def test_render_returns_rendered_text_and_resolved_locale():
    session = AsyncMock()
    template = NotificationTemplate(
        key="orders.payment_received",
        locale="fa",
        category="orders",
        verb_template="پرداخت دریافت شد",
        description_template="سفارش {number} پرداخت شد",
        is_active=True,
    )
    session.scalar.side_effect = [None, template]

    rendered = await NotificationTemplateDataAccessLayer(session).render(
        "orders.payment_received",
        locale="fa-IR",
        context={"number": "A-42"},
    )

    assert rendered.verb == "پرداخت دریافت شد"
    assert rendered.description == "سفارش A-42 پرداخت شد"
    assert rendered.category == "orders"
    assert rendered.key == "orders.payment_received"
    assert rendered.locale == "fa"


@pytest.mark.asyncio
async def test_render_rejects_rendered_verb_over_column_limit():
    session = AsyncMock()
    template = NotificationTemplate(
        key="orders.long",
        locale="en",
        category="orders",
        verb_template="{value}",
        is_active=True,
    )
    session.scalar.return_value = template

    with pytest.raises(ValueError, match="127 characters"):
        await NotificationTemplateDataAccessLayer(session).render(
            "orders.long", context={"value": "x" * 128}
        )


@pytest.mark.asyncio
async def test_register_updates_existing_translation():
    session = AsyncMock()
    existing = NotificationTemplate(
        key="orders.paid",
        locale="en",
        category="general",
        verb_template="old",
        description_template=None,
        is_active=True,
    )
    session.scalar.return_value = existing

    result = await NotificationTemplateDataAccessLayer(session).register(
        key="orders.paid",
        locale="en",
        verb_template="new",
        description_template="Order {number} paid",
        category="orders",
    )

    assert result is existing
    assert result.verb_template == "new"
    assert result.description_template == "Order {number} paid"
    assert result.category == "orders"
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_returns_exact_active_translation():
    session = AsyncMock()
    template = NotificationTemplate(
        key="orders.paid",
        locale="en",
        verb_template="paid",
        is_active=True,
    )
    session.scalar.return_value = template

    result = await NotificationTemplateDataAccessLayer(session).get("orders.paid", "en")

    assert result is template


@pytest.mark.asyncio
async def test_delete_removes_existing_translation():
    session = AsyncMock()
    template = NotificationTemplate(
        key="orders.paid",
        locale="en",
        verb_template="paid",
        is_active=False,
    )
    session.scalar.return_value = template

    result = await NotificationTemplateDataAccessLayer(session).delete(
        "orders.paid", "en"
    )

    assert result is True
    session.delete.assert_awaited_once_with(template)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_returns_false_when_translation_does_not_exist():
    session = AsyncMock()
    session.scalar.return_value = None

    result = await NotificationTemplateDataAccessLayer(session).delete(
        "orders.paid", "en"
    )

    assert result is False
    session.delete.assert_not_awaited()


class _NestedTransaction:
    """Minimal async context manager representing a SQLAlchemy savepoint."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_register_inserts_new_translation_inside_savepoint():
    session = AsyncMock()
    session.add = Mock()
    session.scalar.return_value = None
    session.begin_nested = Mock(return_value=_NestedTransaction())

    result = await NotificationTemplateDataAccessLayer(session).register(
        key="orders.created",
        locale="en",
        verb_template="created",
        description_template="Order {number} created",
        category="orders",
    )

    assert isinstance(result, NotificationTemplate)
    assert result.key == "orders.created"
    assert result.locale == "en"
    session.add.assert_called_once_with(result)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_recovers_from_concurrent_unique_key_insert():
    from sqlalchemy.exc import IntegrityError

    session = AsyncMock()
    session.add = Mock()
    existing = NotificationTemplate(
        key="orders.created",
        locale="en",
        verb_template="old",
        is_active=True,
    )
    session.scalar.side_effect = [None, existing]
    session.begin_nested = Mock(return_value=_NestedTransaction())
    session.flush.side_effect = [
        IntegrityError("insert", {}, Exception("duplicate")),
        None,
    ]

    result = await NotificationTemplateDataAccessLayer(session).register(
        key="orders.created",
        locale="en",
        verb_template="new",
    )

    assert result is existing
    assert existing.verb_template == "new"
    assert session.scalar.await_count == 2
    assert session.flush.await_count == 2


@pytest.mark.asyncio
async def test_register_reraises_integrity_error_without_canonical_row():
    from sqlalchemy.exc import IntegrityError

    session = AsyncMock()
    session.add = Mock()
    session.scalar.side_effect = [None, None]
    session.begin_nested = Mock(return_value=_NestedTransaction())
    error = IntegrityError("insert", {}, Exception("constraint"))
    session.flush.side_effect = error

    with pytest.raises(IntegrityError):
        await NotificationTemplateDataAccessLayer(session).register(
            key="orders.created", locale="en", verb_template="created"
        )


@pytest.mark.asyncio
async def test_register_rejects_invalid_active_flag():
    with pytest.raises(TypeError, match="is_active must be a boolean"):
        await NotificationTemplateDataAccessLayer(AsyncMock()).register(
            key="orders.created",
            locale="en",
            verb_template="created",
            is_active=1,
        )


@pytest.mark.asyncio
async def test_register_rejects_verb_template_over_column_limit():
    with pytest.raises(ValueError, match="127 characters"):
        await NotificationTemplateDataAccessLayer(AsyncMock()).register(
            key="orders.created", locale="en", verb_template="x" * 128
        )


@pytest.mark.asyncio
async def test_resolve_prefers_exact_locale_when_available():
    session = AsyncMock()
    exact = NotificationTemplate(
        key="orders.created",
        locale="fa-IR",
        verb_template="ساخته شد",
        is_active=True,
    )
    session.scalar.return_value = exact

    result = await NotificationTemplateDataAccessLayer(session).resolve(
        "orders.created", "fa-IR", "en"
    )

    assert result is exact
    session.scalar.assert_awaited_once()
