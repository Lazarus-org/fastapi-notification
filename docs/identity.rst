Identity Integration
====================

``fastapi-notification`` does not own authentication, users, groups, or group
membership. It stores recipient, seen-by, deleted-by and group identifiers as
opaque strings and delegates identity-specific behavior to an adapter. This
allows integer, UUID and string primary keys without foreign keys to host auth
tables.

Core and Optional Models
------------------------

Notification models are declared on ``Base``. The example ``User``, ``Group``
and ``Permission`` models use the separate ``AuthBase`` metadata. Applications
using their own identity models should create only ``Base.metadata`` and omit
``AuthBase.metadata``.

The built-in models remain available for standalone examples and tests. To use
them, create both metadata collections and configure
``IDENTITY_ADAPTER="fastapi_notification.identity.BuiltInIdentityAdapter"``.

Adapter Contract
----------------

Subclass :class:`~fastapi_notification.identity.IdentityAdapter` and configure
the class or an instance before creating the router. The base adapter supports conventional
``id``, ``groups``, ``is_staff`` and ``is_superuser`` attributes. Override the
attribute names or methods when your application differs.

The required methods are:

``get_user_id(user)``
    Return the stable user identifier.

``get_group_id(group)``
    Return the stable group identifier.

``get_user_group_ids(session, user)``
    Return group identifiers for a user. Override this when membership is
    stored in a separate association table. This is the authoritative method
    used by asynchronous permission checks and repository operations.

``is_staff(user)`` and ``is_superuser(user)``
    Return the host application's authorization flags.

``resolve_users(session, user_ids)`` and ``resolve_groups(session, group_ids)``
    Return mappings keyed by normalized identifiers for API serialization. The
    base adapter returns ID-only references and performs no database query.

The optional synchronous helper ``get_user_group_ids_sync(user)`` returns
group identifiers from already-loaded in-memory membership data. The base
implementation reads the configured ``user_groups_attribute``. If an adapter
overrides the async method to query an external membership store, it must also
override this synchronous helper to support the synchronous
``NotificationPermission.user_has_permission`` method. Prefer the async
``validate_permission_async`` method for database-backed code.

Example
-------

.. code-block:: python

   from typing import Any, Mapping, Sequence

   from sqlalchemy import String, cast, select
   from sqlalchemy.ext.asyncio import AsyncSession

   from fastapi_notification import IdentityAdapter, configure
   from myapp.models import AppGroup, AppUser


   class AppIdentityAdapter(IdentityAdapter):
       user_id_attribute = "uuid"
       group_id_attribute = "slug"
       user_groups_attribute = "groups"
       staff_attribute = "is_admin"
       superuser_attribute = "is_root"

       async def resolve_users(
           self, session: AsyncSession, user_ids: Sequence[str]
       ) -> Mapping[str, Any]:
           result = await session.scalars(
               select(AppUser).where(cast(AppUser.uuid, String).in_(list(user_ids)))
           )
           return {str(user.uuid): user for user in result.all()}

       async def resolve_groups(
           self, session: AsyncSession, group_ids: Sequence[str]
       ) -> Mapping[str, Any]:
           result = await session.scalars(
               select(AppGroup).where(AppGroup.slug.in_(list(group_ids)))
           )
           return {str(group.slug): group for group in result.all()}


   configure(
       IDENTITY_ADAPTER=AppIdentityAdapter,
       USER_SERIALIZER_FIELDS=["uuid"],
       GROUP_SERIALIZER_CLASS="myapp.serializers.AppGroupSerializer",
   )

The default ``USER_SERIALIZER_FIELDS=["id"]`` works with ID-only references.
When resolving host records, configure the serializer fields to match the
attributes exposed by those models.

When querying ``Notification`` directly with SQLAlchemy, call
``await notification.load_identities(session)`` before reading its transient
``recipient``, ``group`` or ``seen_by`` projections. The data access layer and
HTTP routes hydrate these projections automatically.

Identifier Storage
------------------

Recipient, group, seen-by and deleted-by identifiers are converted to strings
and limited to 255 characters before they are written. This preserves UUID and
string identifiers while keeping association columns indexable. Existing
integer IDs are stored as their base-10 string form. Generic actor, target and action-object identifiers are also stored as text
and restored to the registered SQLAlchemy model's primary-key Python type when
relations are resolved.

Because this changes association column types and removes auth foreign keys,
existing pre-release development databases should be recreated or migrated to
the new schema before using this checkpoint.

Group audience strategies
--------------------------

Notifications can use ``group_audience_strategy="dynamic"`` (the default) or
``group_audience_strategy="snapshot"`` when created through the data access
layer. Dynamic audiences retain the group association and resolve membership
when a recipient reads the notification. Snapshot audiences resolve current
group members at creation time and persist those users as individual recipient
associations; later membership changes do not change that captured audience.

Applications using snapshot audiences must override
``IdentityAdapter.get_group_user_ids(session, group)`` and return the current
member identity objects or IDs. The base adapter raises
``NotImplementedError`` rather than assuming a host application's membership
schema. Snapshot audiences do not retain a dynamic group grant.
