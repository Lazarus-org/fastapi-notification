from typing import List

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fastapi_notification.models.base import AuthBase
from fastapi_notification.models.content_type import register_content_model

user_group = Table(
    "user_group",
    AuthBase.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)

group_permission = Table(
    "group_permission",
    AuthBase.metadata,
    Column("group_id", ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


@register_content_model
class Permission(AuthBase):
    """A named capability that can be attached to a group.

    Attributes:
        name (str): The human readable description of the permission.
        codename (str): The machine readable identifier of the permission.
    """

    __tablename__ = "permissions"
    __app_label__ = "auth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    codename: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    def __str__(self) -> str:
        """Return the permission name.

        Returns:
            str: The human readable permission name.
        """
        return self.name


@register_content_model
class Group(AuthBase):
    """An optional collection of users that notifications can be addressed to.

    Attributes:
        name (str): The unique name of the group.
        permissions (List[Permission]): The permissions granted by the group.
        users (List[User]): The members of the group.
    """

    __tablename__ = "groups"
    __app_label__ = "auth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)

    permissions: Mapped[List[Permission]] = relationship(
        secondary=group_permission, lazy="selectin"
    )
    users: Mapped[List["User"]] = relationship(
        secondary=user_group, back_populates="groups", lazy="selectin"
    )

    def __str__(self) -> str:
        """Return the group name.

        Returns:
            str: The name of the group.
        """
        return self.name


@register_content_model
class User(AuthBase):
    """The default user model shipped with the package.

    This optional example model lives on ``AuthBase`` rather than the core
    notification ``Base``. Host applications with their own identity models can
    configure an ``IdentityAdapter`` and omit these tables entirely.

    Attributes:
        username (str): The unique identifier used to address the user.
        email (str): The email address of the user.
        is_active (bool): Whether the account is usable.
        is_staff (bool): Whether the user has elevated, staff level access.
        is_superuser (bool): The host application's superuser flag. The package
            does not treat it as automatic notification audience or staff access.
        groups (List[Group]): The groups the user belongs to.
    """

    __tablename__ = "users"
    __app_label__ = "auth"

    #: The field that uniquely identifies a user, mirroring ``USERNAME_FIELD``.
    USERNAME_FIELD = "username"
    #: Additional identifying fields, mirroring ``REQUIRED_FIELDS``.
    REQUIRED_FIELDS = ("email",)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    groups: Mapped[List[Group]] = relationship(
        secondary=user_group, back_populates="users", lazy="selectin"
    )

    def __str__(self) -> str:
        """Return the username.

        Returns:
            str: The username of the user.
        """
        return self.username
