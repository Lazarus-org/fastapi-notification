from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Type
from uuid import UUID

from sqlalchemy import Integer, String, UniqueConstraint, inspect, select
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.models.base import Base
from fastapi_notification.models.state import insert_if_absent

# Registry of models that may participate in a generic relation, keyed by the
# ``(app_label, model)`` pair that identifies them in the ``content_type`` table.
_CONTENT_TYPE_REGISTRY: Dict[Tuple[str, str], Type[Any]] = {}


def normalize_object_id(object_id: Any) -> str:
    """Normalize a supported generic-relation primary key for persistence.

    Integer, UUID and string identifiers are stored in a common textual
    representation. The original Python type is recovered from the registered
    model's SQLAlchemy primary-key column when the object is loaded.

    Args:
        object_id (Any): The model instance primary key.

    Returns:
        str: The canonical textual representation of the identifier.

    Raises:
        TypeError: If the identifier is not an integer, UUID or string.
    """
    if isinstance(object_id, bool) or not isinstance(object_id, (int, UUID, str)):
        raise TypeError(
            "Generic relation primary keys must be integers, UUIDs or strings."
        )
    return str(object_id)


def coerce_object_id(model: Type[Any], object_id: Any) -> Any:
    """Convert a stored generic-relation identifier to its model PK type.

    Only single-column primary keys are supported. SQLAlchemy's mapped primary
    key type is authoritative, so UUID strings become ``uuid.UUID`` instances,
    integer strings become integers, and string identifiers remain unchanged.

    Args:
        model (Type[Any]): The registered SQLAlchemy model.
        object_id (Any): The persisted textual identifier.

    Returns:
        Any: The identifier converted to the model's primary-key Python type.

    Raises:
        TypeError: If the model has a composite primary key or an unsupported
            primary-key type.
        ValueError: If the stored identifier cannot be converted.
    """
    try:
        mapper = inspect(model)
    except NoInspectionAvailable as exc:
        raise TypeError(
            "The registered content model is not a SQLAlchemy model."
        ) from exc

    primary_keys = mapper.primary_key
    if len(primary_keys) != 1:
        raise TypeError(
            "Generic relations require models with a single-column primary key."
        )

    try:
        primary_key_type = primary_keys[0].type.python_type
    except (AttributeError, NotImplementedError) as exc:
        raise TypeError(
            "The model primary-key column does not expose a supported Python type."
        ) from exc

    if primary_key_type is str:
        return str(object_id)
    if primary_key_type is int:
        if isinstance(object_id, bool):
            raise ValueError("Boolean values are not valid integer identifiers.")
        return int(object_id)
    if primary_key_type is UUID:
        return object_id if isinstance(object_id, UUID) else UUID(str(object_id))

    if isinstance(object_id, primary_key_type):
        return object_id

    try:
        return primary_key_type(object_id)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TypeError(
            f"Unsupported generic relation primary-key type: "
            f"{primary_key_type.__name__}."
        ) from exc


def natural_key_for_model(model: Type[Any]) -> Tuple[str, str]:
    """Derive the ``(app_label, model)`` natural key that identifies a model.

    The app label defaults to the top level package the model is declared in and
    the model name is the lowercased class name, mirroring how Django derives a
    ``ContentType`` natural key.

    Args:
        model (Type[Any]): The model class to derive a natural key for.

    Returns:
        Tuple[str, str]: The app label and lowercased model name.
    """
    app_label = getattr(model, "__app_label__", None) or model.__module__.split(".")[0]
    return app_label, model.__name__.lower()


def register_content_model(model: Type[Any]) -> Type[Any]:
    """Register a model so it can be used as a generic relation target.

    Any object referenced as a notification ``actor``, ``target`` or
    ``action_object`` must be registered, so that the stored content type can be
    resolved back into a concrete model class.

    Args:
        model (Type[Any]): The model class to register.

    Returns:
        Type[Any]: The same model class, so this can be used as a decorator.
    """
    _CONTENT_TYPE_REGISTRY[natural_key_for_model(model)] = model
    return model


def get_registered_model(app_label: str, model: str) -> Optional[Type[Any]]:
    """Look up a registered model class by its natural key.

    Args:
        app_label (str): The app label of the model.
        model (str): The lowercased model name.

    Returns:
        Optional[Type[Any]]: The registered class, or ``None`` when unknown.
    """
    return _CONTENT_TYPE_REGISTRY.get((app_label, model))


class ContentType(Base):
    """A lightweight record identifying a model that participates in a generic relation.

    Attributes:
        app_label (str): The package the referenced model belongs to.
        model (str): The lowercased name of the referenced model.
    """

    __tablename__ = "content_type"
    __table_args__ = (
        UniqueConstraint("app_label", "model", name="content_type_natural_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_label: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    def __str__(self) -> str:
        """Return the natural key of the content type as a dotted string.

        Returns:
            str: The ``app_label.model`` representation.
        """
        return f"{self.app_label}.{self.model}"

    @classmethod
    async def get_for_model(
        cls, session: AsyncSession, model: Type[Any]
    ) -> "ContentType":
        """Fetch, creating when needed, the content type describing a model.

        Args:
            session (AsyncSession): The session used to read and write.
            model (Type[Any]): The model class to describe.

        Returns:
            ContentType: The persisted content type for the model.
        """
        app_label, model_name = natural_key_for_model(model)
        register_content_model(model)

        result = await session.execute(
            select(cls).where(cls.app_label == app_label, cls.model == model_name)
        )
        content_type = result.scalar_one_or_none()
        if content_type is not None:
            return content_type

        # The initial read avoids a write for the common already-registered
        # case. The unique natural key plus conflict-safe insert resolves races
        # when two workers register the same model for the first time.
        content_type, _ = await insert_if_absent(
            session,
            cls,
            {"app_label": app_label, "model": model_name},
            ("app_label", "model"),
        )
        return content_type

    def model_class(self) -> Optional[Type[Any]]:
        """Return the model class this content type points at.

        Returns:
            Optional[Type[Any]]: The registered class, or ``None`` when the model
            has not been registered in the current process.
        """
        return get_registered_model(self.app_label, self.model)

    async def get_object_for_this_type(
        self, session: AsyncSession, object_id: Any
    ) -> Optional[Any]:
        """Load a referenced object using its model-specific primary-key type.

        Stored generic identifiers are textual so integer, UUID and string
        primary keys share one persistence representation. Before querying,
        the identifier is converted back to the SQLAlchemy model's PK type.

        Args:
            session (AsyncSession): The session used to read.
            object_id (Any): The stored primary-key identifier.

        Returns:
            Optional[Any]: The instance, or ``None`` when the model is
            unregistered, the identifier is invalid, or no row matches.

        Raises:
            TypeError: If the registered model is not mapped or does not have
                a supported single-column primary key.
        """
        model = self.model_class()
        if model is None or object_id is None:
            return None

        try:
            typed_object_id = coerce_object_id(model, object_id)
        except (ValueError, OverflowError):
            return None

        return await session.get(model, typed_object_id)


__all__ = [
    "ContentType",
    "coerce_object_id",
    "get_registered_model",
    "natural_key_for_model",
    "normalize_object_id",
    "register_content_model",
]
