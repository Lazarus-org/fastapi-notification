from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession


def loaded_collection(instance: Any, name: str) -> Any:
    """Return a relationship's contents, or an empty list if it is not loaded.

    Serializers must never trigger a lazy load: under the async ORM that raises
    rather than emitting a query. Reading through this helper keeps rendering
    safe for instances whose relationships were not eagerly loaded.

    Args:
        instance (Any): The model instance to read from.
        name (str): The relationship name.

    Returns:
        Any: The loaded contents, or an empty list.
    """
    if instance is None:
        return []

    state = inspect(instance, raiseerr=False)

    if state is not None and name in state.unloaded:
        return []

    return getattr(instance, name, []) or []


async def ensure_loaded(session: AsyncSession, instance: Any, *attributes: str) -> Any:
    """Load the named relationships on an instance if they are not loaded yet.

    Under the async ORM, touching an unloaded relationship raises rather than
    emitting a query, so anything that walks a relationship must guarantee it is
    loaded first. Instances that were just constructed in Python, rather than
    returned by a query, are the usual reason an attribute is still unloaded.

    Args:
        session (AsyncSession): The session used to read.
        instance (Any): The model instance to load attributes on.
        *attributes (str): The relationship names to guarantee are loaded.

    Returns:
        Any: The same instance, with the requested attributes loaded.
    """
    if instance is None:
        return instance

    state = inspect(instance, raiseerr=False)
    if state is None:
        return instance

    if state.transient or state.detached:
        return instance

    unloaded = {name for name in attributes if name in state.unloaded}
    if unloaded:
        await session.refresh(instance, list(unloaded))

    return instance
