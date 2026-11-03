"""Typing boundaries for deliberately invalid inputs and minimal unit transports."""

from typing import Awaitable, Callable, cast

from sqlalchemy.ext.asyncio import AsyncSession


def session_double(value: object) -> AsyncSession:
    """Treat a tested minimal session double as the AsyncSession contract it exercises.

    This is confined to existing unit tests. Real integration sessions are not wrapped
    or replaced, and no database behavior is simulated by this helper.
    """
    return cast(AsyncSession, value)


def call_result(function: Callable[[], object]) -> object:
    """Retain explicit None-return assertions without discarding the return value."""
    return function()


async def async_call_result(function: Callable[[], Awaitable[object]]) -> object:
    """Retain explicit None-return assertions for async dependencies."""
    return await function()
