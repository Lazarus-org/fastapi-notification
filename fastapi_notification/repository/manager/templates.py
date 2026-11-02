"""Data access and locale fallback for notification templates."""

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_notification.models.helper.enums import normalize_category
from fastapi_notification.models.notification_template import (
    NotificationTemplate,
    normalize_locale,
    normalize_template_key,
)
from fastapi_notification.utils.templates import render_template, validate_template


@dataclass(frozen=True)
class RenderedNotificationTemplate:
    """Immutable rendered text and provenance for one notification."""

    verb: str
    description: Optional[str]
    category: str
    key: str
    locale: str


class NotificationTemplateDataAccessLayer:
    """Register, retrieve and render localized notification templates.

    The caller owns the transaction. Methods flush writes but never commit.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def register(
        self,
        key: str,
        locale: str,
        verb_template: str,
        description_template: Optional[str] = None,
        category: str = "general",
        is_active: bool = True,
    ) -> NotificationTemplate:
        """Create or update the localized template identified by key and locale."""
        key = normalize_template_key(key)
        locale = normalize_locale(locale)
        category = normalize_category(category)
        validate_template(verb_template)
        if len(verb_template) > 127:
            raise ValueError("verb_template must not exceed 127 characters.")
        if description_template is not None:
            validate_template(description_template)
        if not isinstance(is_active, bool):
            raise TypeError("is_active must be a boolean.")

        statement = select(NotificationTemplate).where(
            NotificationTemplate.key == key,
            NotificationTemplate.locale == locale,
        )
        existing = await self.session.scalar(statement)
        if existing is not None:
            existing.verb_template = verb_template
            existing.description_template = description_template
            existing.category = category
            existing.is_active = is_active
            await self.session.flush()
            return existing

        template = NotificationTemplate(
            key=key,
            locale=locale,
            verb_template=verb_template,
            description_template=description_template,
            category=category,
            is_active=is_active,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(template)
                await self.session.flush()
            return template
        except IntegrityError:
            # Another worker may have registered the same pair. Re-read it and
            # update the canonical row rather than leaving the session failed.
            existing = await self.session.scalar(statement.with_for_update())
            if existing is None:
                raise
            existing.verb_template = verb_template
            existing.description_template = description_template
            existing.category = category
            existing.is_active = is_active
            await self.session.flush()
            return existing

    async def get(self, key: str, locale: str) -> Optional[NotificationTemplate]:
        """Return an exact active translation, if registered."""
        key = normalize_template_key(key)
        locale = normalize_locale(locale)
        return await self.session.scalar(
            select(NotificationTemplate).where(
                NotificationTemplate.key == key,
                NotificationTemplate.locale == locale,
                NotificationTemplate.is_active.is_(True),
            )
        )

    async def resolve(
        self,
        key: str,
        locale: str,
        default_locale: str = "en",
    ) -> NotificationTemplate:
        """Resolve exact locale, base language, then configured default locale."""
        key = normalize_template_key(key)
        requested = normalize_locale(locale)
        default = normalize_locale(default_locale)
        candidates = [requested]
        base_language = requested.split("-", 1)[0]
        if base_language not in candidates:
            candidates.append(base_language)
        if default not in candidates:
            candidates.append(default)

        for candidate in candidates:
            template = await self.get(key, candidate)
            if template is not None:
                return template
        raise LookupError(
            f"No active template {key!r} found for {requested!r} or fallback "
            f"locale {default!r}."
        )

    async def render(
        self,
        key: str,
        locale: str = "en",
        context: Optional[Mapping[str, Any]] = None,
        default_locale: str = "en",
    ) -> RenderedNotificationTemplate:
        """Resolve a translation and render its immutable text snapshot."""
        template = await self.resolve(key, locale, default_locale)
        rendered_verb = render_template(template.verb_template, context)
        if len(rendered_verb) > 127:
            raise ValueError(
                "Rendered notification verb must not exceed 127 characters."
            )
        return RenderedNotificationTemplate(
            verb=rendered_verb,
            description=(
                render_template(template.description_template, context)
                if template.description_template is not None
                else None
            ),
            category=template.category,
            key=template.key,
            locale=template.locale,
        )

    async def delete(self, key: str, locale: str) -> bool:
        """Delete one locale version, including inactive records."""
        key = normalize_template_key(key)
        locale = normalize_locale(locale)
        template = await self.session.scalar(
            select(NotificationTemplate).where(
                NotificationTemplate.key == key,
                NotificationTemplate.locale == locale,
            )
        )
        if template is None:
            return False
        await self.session.delete(template)
        await self.session.flush()
        return True


__all__ = ["NotificationTemplateDataAccessLayer", "RenderedNotificationTemplate"]
