from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession


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

    state = inspect(instance)

    if state.transient or state.detached:
        return instance

    unloaded = {name for name in attributes if name in state.unloaded}
    if unloaded:
        await session.refresh(instance, list(unloaded))

    return instance
