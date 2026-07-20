from typing import List, Set


class DisableMethodsMixin:
    """Tracks which router operations are switched off in settings.

    A disabled operation is never registered on the router, so it is absent from
    the application and from its OpenAPI schema, rather than being registered
    only to reject every request.

    """

    def disable_methods(self, methods: List[str]) -> None:
        """Mark the named operations as disabled.

        Args:
            methods (List[str]): The operation names to disable, e.g.
                ``["LIST", "RETRIEVE"]``.

        Example:
            To disable listing and retrieval::

                self.disable_methods(["LIST", "RETRIEVE"])

        """
        if not hasattr(self, "disabled_methods"):
            self.disabled_methods: Set[str] = set()

        self.disabled_methods.update(method.upper() for method in methods)

    def is_method_enabled(self, method: str) -> bool:
        """Report whether an operation should be registered.

        Args:
            method (str): The operation name, e.g. ``"LIST"``.

        Returns:
            bool: Whether the operation is enabled.

        """
        return method.upper() not in getattr(self, "disabled_methods", set())
