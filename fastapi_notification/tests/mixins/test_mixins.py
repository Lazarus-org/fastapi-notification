from typing import Any

import pytest

from fastapi_notification.api.filters.notification_filter import NotificationFilter
from fastapi_notification.api.paginations.limit_offset_pagination import (
    DefaultLimitOffSetPagination,
)
from fastapi_notification.mixins import ConfigurableAttrsMixin, DisableMethodsMixin
from fastapi_notification.settings.conf import configure

pytestmark = [pytest.mark.mixins]


class Configurable(ConfigurableAttrsMixin):
    """A bare host for the configuration mixin."""


class Switchable(DisableMethodsMixin):
    """A bare host for the method disabling mixin."""


def test_attributes_are_read_from_the_settings() -> None:
    """The mixin picks up the ordering, search and pagination settings."""
    host = Configurable()
    host.configure_attrs()

    assert host.ordering_fields == ["id", "timestamp", "public"]
    assert host.search_fields == ["verb", "description"]
    assert host.pagination_class is DefaultLimitOffSetPagination


def test_the_dependency_chain_covers_auth_and_throttling() -> None:
    """Authentication and throttling are both applied by default."""
    host = Configurable()
    host.configure_attrs()

    assert len(host.dependencies) == 2


def test_the_extra_permission_joins_the_chain() -> None:
    """Configuring an extra permission adds it to the chain."""
    configure(
        API_EXTRA_PERMISSION_CLASS=(
            "fastapi_notification.tests.mixins.test_mixins.AllowAll"
        )
    )

    host = Configurable()
    host.configure_attrs()

    assert len(host.dependencies) == 3


def test_switching_throttling_off_shortens_the_chain() -> None:
    """With no throttle class, no throttling dependency is applied."""
    configure(API_THROTTLE_CLASS=None)

    host = Configurable()
    host.configure_attrs()

    assert len(host.dependencies) == 1


def test_pagination_can_be_switched_off() -> None:
    """With no pagination class, results are returned unwrapped."""
    configure(API_PAGINATION_CLASS=None)

    host = Configurable()
    host.configure_attrs()

    assert host.paginator is None
    assert host.paginate(None, ["a", "b"], 2) == ["a", "b"]
    assert host.apply_pagination("statement", None) == "statement"


def test_the_default_filter_set_is_used() -> None:
    """With nothing configured, the packaged filter set is used."""
    host = Configurable()
    host.configure_attrs()

    assert host.get_filter_dependency() is NotificationFilter


def test_a_configured_filter_set_is_used() -> None:
    """A configured filter set replaces the packaged one."""
    configure(
        API_FILTERSET_CLASS=(
            "fastapi_notification.tests.mixins.test_mixins.CustomFilter"
        )
    )

    host = Configurable()
    host.configure_attrs()

    assert host.get_filter_dependency() is CustomFilter


def test_every_method_is_enabled_by_default() -> None:
    """Nothing is disabled until something asks for it."""
    host = Switchable()

    assert host.is_method_enabled("LIST") is True


def test_disabled_methods_are_reported() -> None:
    """A disabled operation is reported as such, case insensitively."""
    host = Switchable()
    host.disable_methods(["LIST"])

    assert host.is_method_enabled("LIST") is False
    assert host.is_method_enabled("list") is False
    assert host.is_method_enabled("RETRIEVE") is True


def test_disabling_accumulates() -> None:
    """Disabling twice adds to the set rather than replacing it."""
    host = Switchable()
    host.disable_methods(["LIST"])
    host.disable_methods(["RETRIEVE"])

    assert host.is_method_enabled("LIST") is False
    assert host.is_method_enabled("RETRIEVE") is False


class AllowAll:
    """An extra permission that lets every request through."""

    def __call__(self, request: Any, user: Any) -> bool:
        return True


class CustomFilter(NotificationFilter):
    """A stand-in filter set, used to prove the setting is honoured."""
