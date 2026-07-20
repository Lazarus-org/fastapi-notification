from typing import Any, Dict, Optional, Tuple, Type

from sqlalchemy import Integer, String, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from fastapi_notification.models.base import Base

# Registry of models that may participate in a generic relation, keyed by the
# ``(app_label, model)`` pair that identifies them in the ``content_type`` table.
_CONTENT_TYPE_REGISTRY: Dict[Tuple[str, str], Type[Any]] = {}


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
    """A lightweight record identifying a model that participates in a generic
    relation.

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

        if content_type is None:
            content_type = cls(app_label=app_label, model=model_name)
            session.add(content_type)
            await session.flush()

        return content_type

    def model_class(self) -> Optional[Type[Any]]:
        """Return the model class this content type points at.

        Returns:
            Optional[Type[Any]]: The registered class, or ``None`` when the model
            has not been registered in the current process.

        """
        return get_registered_model(self.app_label, self.model)

    async def get_object_for_this_type(
        self, session: AsyncSession, object_id: int
    ) -> Optional[Any]:
        """Load a single instance of the referenced model by primary key.

        Args:
            session (AsyncSession): The session used to read.
            object_id (int): The primary key of the instance to load.

        Returns:
            Optional[Any]: The instance, or ``None`` when the model is not
            registered or no row matches.

        """
        model = self.model_class()
        if model is None:
            return None
        return await session.get(model, object_id)
