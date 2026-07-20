from importlib import import_module
from typing import Any


def import_string(dotted_path: str) -> Any:
    """Import a dotted module path and return the attribute it designates.

    Args:
        dotted_path (str): The dotted path, e.g. ``"myapp.module.MyClass"``.

    Returns:
        Any: The attribute named by the last segment of the path.

    Raises:
        ImportError: If the path is malformed, the module cannot be imported, or
            the module does not define the named attribute.

    """
    try:
        module_path, class_name = dotted_path.rsplit(".", 1)
    except ValueError as error:
        raise ImportError(f"{dotted_path} doesn't look like a module path") from error

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError as error:
        raise ImportError(
            f"Module '{module_path}' does not define a '{class_name}' attribute/class"
        ) from error
