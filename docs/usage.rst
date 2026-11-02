Usage
=====

The HTTP API is only one way to use the package. Everything the routes do goes
through ``NotificationDataAccessLayer``, which you can call directly from your
own code: background jobs, CLI commands, domain services, or routes of your
own.

The Data Access Layer
---------------------

The data access layer (DAL) is bound to a single async SQLAlchemy session.
Construct one per session, or per request:

.. code-block:: python

   from sqlalchemy.ext.asyncio import AsyncSession

   from fastapi_notification import NotificationDataAccessLayer

   async with Session() as session:
       dal = NotificationDataAccessLayer(session)

Inside a FastAPI route, build it from the session your dependency yields:

.. code-block:: python

   from fastapi import Depends
   from sqlalchemy.ext.asyncio import AsyncSession

   from fastapi_notification import NotificationDataAccessLayer


   @app.get("/my-notifications")
   async def my_notifications(
       session: AsyncSession = Depends(get_session),
       user=Depends(get_current_user),
   ):
       dal = NotificationDataAccessLayer(session)
       return await dal.unseen(unseen_by=user)

Transactions
~~~~~~~~~~~~

**The caller owns the transaction.** Every write method flushes the session so
that generated primary keys are available, but none of them commit. Nothing is
durable until you commit yourself, which means a sequence of DAL calls can be
treated as a single unit of work and rolled back as one.

.. code-block:: python

   async with Session() as session:
       dal = NotificationDataAccessLayer(session)

       notification = await dal.create_notification(verb="signed up", actor=user)
       await dal.mark_all_as_sent(recipients=[user])

       await session.commit()

Creating Notifications
----------------------

``create_notification()`` writes the notification and addresses it to any
recipients and groups given.

.. code-block:: python

   from datetime import datetime, timedelta, timezone

   notification = await dal.create_notification(
       verb="commented on",
       actor=alice,
       description="Alice commented on your post",
       recipients=[bob, carol],
       groups=[moderators],
       status="INFO",
       category="orders",
       priority="high",
       public=True,
       target=post,
       action_object=comment,
       link="https://example.com/posts/123#comment-7",
       is_sent=True,
       data={"post_id": 123, "comment_id": 7},
       expires_at=datetime.now(timezone.utc) + timedelta(days=30),
   )

   await session.commit()

Only ``verb`` and ``actor`` are required. The parameters are:

``verb`` (``str``, required)
    A short phrase describing the action, for example ``"liked"`` or
    ``"commented on"``.


``actor`` (any registered model instance, required)
    The user or object performing the action.

``description`` (``Optional[str]``, default ``None``)
    Additional context. When omitted, a description is generated from the
    actor, the verb, and the target or action object — see below.

``recipients`` (a user or a sequence of users, default ``None``)
    The users the notification is addressed to.

``groups`` (a group or a sequence of groups, default ``None``)
    The groups the notification is addressed to. Both may be given.

``status`` (``str``, default ``"INFO"``)
    One of the ``NotificationStatus`` values. Describes the notification's
    nature or state; it is independent of urgency.

``category`` (``str``, default ``"general"``)
    A lowercase category key. Built-ins are ``general``, ``system``, ``security``,
    ``social``, ``financial``, ``orders`` and ``marketing``. Applications may
    use custom namespaced keys such as ``com.example.billing``.

``priority`` (``str``, default ``"normal"``)
    One of ``low``, ``normal``, ``high`` or ``urgent``. Priority describes
    urgency and is not inferred from ``status``.

``public`` (``bool``, default ``True``)
    Whether the notification is publicly visible.

``target`` (any registered model instance, default ``None``)
    The object being acted upon.

``action_object`` (any registered model instance, default ``None``)
    The object used to perform the action.

``link`` (``Optional[str]``, default ``None``)
    A URL associated with the notification.

``is_sent`` (``bool``, default ``False``)
    Whether the notification counts as delivered. Notifications are only
    visible to their recipients once this is true, so create them unsent if you
    want to stage delivery and call ``mark_all_as_sent()`` later.

``data`` (``Optional[Dict[str, Any]]``, default ``None``)
    Arbitrary JSON stored alongside the notification.

``expires_at`` (``Optional[datetime]``, default ``None``)
    Optional timezone-aware expiration instant. Naive datetimes are rejected;
    aware values are normalized to UTC. Expired notifications are hidden from
    normal recipient queries but retained in the database.

``deduplication_key`` (``Optional[str]``, default ``None``)
    Stable event identifier used to prevent duplicate notification creation.
    When omitted, each call creates a new notification.

``deduplication_scope`` (``str``, default ``"global"``)
    Namespace in which the key must be unique. Use tenant/account scope when
    the event identifier is not globally unique.

``deduplication_key_expires_at`` (``Optional[datetime]``, default ``None``)
    Time after which the key may be reused. Must be timezone-aware and in the
    future. ``None`` retains the key until the notification is permanently
    deleted.

.. _idempotent-notification-creation:

Idempotent Creation and Deduplication
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a notification is created from a retryable background job, payment
callback, webhook or event consumer, pass a stable ``deduplication_key`` to
prevent the same business event from creating multiple notifications.

.. code-block:: python

   notification = await dal.create_notification(
       verb="payment received",
       actor=payment,
       recipients=[customer],
       is_sent=True,
       deduplication_scope=f"tenant:{tenant.id}",
       deduplication_key=f"payment-received:{payment.id}",
       deduplication_key_expires_at=(
           datetime.now(timezone.utc) + timedelta(days=7)
       ),
   )
   await session.commit()

The key is unique within its scope. The default scope is ``"global"``; use a
scope that reflects the uniqueness boundary of your business event, such as a
tenant or account identifier. Keys and scopes must be non-empty strings of at
most 255 characters.

When an active key is reused, ``create_notification()`` returns the original
notification unchanged. It does not update the original content, merge
recipients/groups, or create a second notification. This makes retries
idempotent and avoids accidentally broadening the audience on a duplicate
request. The caller still owns the transaction and must commit or roll it back.
A retry does not extend or otherwise change the original key's expiry policy.

``deduplication_key_expires_at`` is independent of the notification's own
``expires_at``. A ``None`` key expiry retains the key until the notification is
permanently deleted. Once the key expiry is reached, the next creation using
the same scope and key may atomically claim it for a new notification. The old
notification remains unchanged. Permanently deleting or explicitly purging a
notification releases its key; merely expiring it from recipient inboxes does
not.

If ``deduplication_key`` is omitted, every call creates a new notification as
usual.


Expiration and Retention
~~~~~~~~~~~~~~~~~~~~~~~~

Expiration is optional. When ``expires_at`` is set, the notification becomes
unavailable to recipients at that exact instant. The rule is applied to direct
recipients and group recipients alike, and affects inboxes, activities,
summary/preview queries, and normal unsent-delivery queries. Expired items
cannot be marked as seen or unseen.

Expiration is not deletion. Raw ``all_notifications()`` queries and deleted
history can still be used for audit purposes. Permanent cleanup is an explicit
staff-only operation, and the caller chooses the retention cutoff:

.. code-block:: python

   from datetime import datetime, timedelta, timezone

   cutoff = datetime.now(timezone.utc) - timedelta(days=30)
   purged = await dal.purge_expired(
       expired_before=cutoff,
       limit=500,
       actor=staff_user,
   )
   await session.commit()

Only notifications whose ``expires_at`` is at or before ``cutoff`` are
permanently removed. Related recipient, group, seen and soft-delete association
rows are removed with them. The DAL does not commit the caller's transaction.
The package does not start a scheduler; call this method from your application's
scheduled task if you want recurring retention cleanup.

The nullable ``notification.expires_at`` column is a pre-release schema addition.
``Base.metadata.create_all()`` does not alter an existing table; add the nullable column and its index
through your migration process or recreate development tables before upgrading.

``update_notification()`` can change ``expires_at`` or clear it explicitly:

.. code-block:: python

   await dal.update_notification(notification.id, expires_at=new_expiry)
   await dal.update_notification(notification.id, clear_expires_at=True)

Generated descriptions
~~~~~~~~~~~~~~~~~~~~~~

When ``description`` is omitted, one is generated from the notification's
generic relations, using each object's string representation:

- actor, verb, action object and target: ``"alice commented on comment-7 on my-first-post"``
- actor, verb and target: ``"alice liked my-first-post"``
- actor, verb and action object: ``"alice posted comment-7"``
- actor and verb only: ``"alice signed up"``

Generic relations
~~~~~~~~~~~~~~~~~

``actor``, ``target`` and ``action_object`` are generic: they can be an
instance of *any* model, not just the packaged ``User``. The model must be
registered so the stored content type can be resolved back into a class:

.. code-block:: python

   from sqlalchemy.orm import DeclarativeBase
   from fastapi_notification import register_content_model


   class HostBase(DeclarativeBase):
       pass


   @register_content_model
   class Post(HostBase):
       __tablename__ = "posts"
       ...

Each relation is stored as a content type plus an object ID. Generic object
IDs use a text representation so the same columns can store integer, UUID and
string primary keys. When a relation is resolved, the package reads the
registered SQLAlchemy model's primary-key type and converts the stored value
back before querying. Integer IDs therefore remain integers in Python,
UUID IDs are returned as ``uuid.UUID`` objects, and string IDs are preserved
exactly.

The referenced model must have a single-column primary key. Composite primary
keys are not supported by generic relations.

Because generic relations cannot be loaded eagerly by the ORM, they are
resolved on demand when a notification is read back:

.. code-block:: python

   await notification.resolve_generic_relations(session)

   notification.actor
   notification.target
   notification.action_object

An object whose model is not registered in the current process resolves to
``None``. Invalid stored identifiers also resolve to ``None`` rather than
being passed to SQLAlchemy with the wrong Python type.

For example, a model may use any of these primary-key declarations:

.. code-block:: python

   from uuid import UUID
   from sqlalchemy import String, Uuid
   from sqlalchemy.orm import Mapped, mapped_column

   class UUIDPost(HostBase):
       __tablename__ = "uuid_posts"
       id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)

   class ExternalRecord(HostBase):
       __tablename__ = "external_records"
       id: Mapped[str] = mapped_column(String(200), primary_key=True)

The ``actor_object_id``, ``target_object_id`` and
``action_object_object_id`` database columns are now text columns. This is a
pre-release schema change: recreate local development tables or migrate those
columns before upgrading an existing database.

Querying Notifications
----------------------

Six read methods cover the common questions. All of them are coroutines.

.. code-block:: python

   rows = await dal.all_notifications(recipients=[bob])
   rows = await dal.sent(recipients=[bob], exclude_deleted_by=bob)
   rows = await dal.unsent(groups=[moderators])
   rows = await dal.seen(seen_by=bob)
   rows = await dal.unseen(unseen_by=bob)
   rows = await dal.deleted(deleted_by=bob)

``all_notifications(recipients=None, groups=None, display_detail=False)``
    Every notification, regardless of delivery state.

``sent(recipients=None, exclude_deleted_by=None, groups=None, display_detail=False, conditions=None)``
    Notifications whose ``is_sent`` flag is true.

``unsent(...)``
    The same, for notifications not yet marked as sent. Takes the same
    parameters as ``sent``.

``seen(seen_by, recipients=None, groups=None, display_detail=False, conditions=None)``
    Sent notifications the given user has already seen. ``seen_by`` is
    required, and doubles as the user whose soft deletions are excluded.

``unseen(unseen_by, ...)``
    Sent notifications the given user has not seen yet. Same parameters as
    ``seen``.

``deleted(deleted_by=None, display_detail=True)``
    Notifications that have been soft deleted, optionally restricted to
    deletions performed by one user. Note that this method defaults
    ``display_detail`` to ``True``, unlike the others.

Filters
~~~~~~~

``recipients``
    A user or a sequence of users. Restricts results to notifications addressed
    to any of them.

``groups``
    A group or a sequence of groups. Restricts results to notifications
    addressed to any of them. When both ``recipients`` and ``groups`` are given
    to ``sent``, ``unsent``, ``seen`` or ``unseen``, they are combined with OR:
    a notification matches if it reached either audience.

``exclude_deleted_by``
    A user whose soft-deleted notifications are left out of the results. On
    ``sent`` and ``unsent``, when no explicit recipient filter is supplied,
    this also adds that user's direct recipient identity to the audience. If
    ``groups`` is supplied, direct-recipient and group conditions are combined
    with OR. Staff and superuser flags never bypass this audience restriction.

``conditions``
    A sequence of SQLAlchemy boolean expressions applied to the statement, for
    anything the named filters do not cover.

.. code-block:: python

   from fastapi_notification import Notification

   rows = await dal.sent(
       recipients=[bob],
       exclude_deleted_by=bob,
       conditions=[Notification.status == "CRITICAL", Notification.public.is_(True)],
   )

display_detail
~~~~~~~~~~~~~~

Every read method takes ``display_detail``, which decides what comes back:

- ``False`` (the default, except on ``deleted``) selects only the summary
  columns and returns a list of plain dictionaries — ``id``, ``description``,
  ``status``, ``category``, ``priority``, ``link``, ``timestamp`` and
  ``expires_at``.
- ``True`` selects whole rows and returns a list of ``Notification`` instances,
  with their relationships and generic relations available.

.. code-block:: python

   compact = await dal.unseen(unseen_by=bob)
   # [{"id": 1, "description": "...", "status": "INFO", "category": "general",
   #   "priority": "normal", "link": None, "timestamp": ...}]

   full = await dal.unseen(unseen_by=bob, display_detail=True)
   # [<Notification ...>]

Results are always ordered newest first, by ``timestamp`` descending.

Single Notifications and Counts
-------------------------------

``get()`` fetches one notification through a statement, which is how a route
enforces visibility: a notification the statement does not select comes back as
``None`` rather than being returned to someone who should not see it.

.. code-block:: python

   statement = dal.unseen_statement(unseen_by=bob, display_detail=True)

   notification = await dal.get(statement, notification_id=42)
   if notification is None:
       ...

``count()`` returns how many rows a statement would produce, without fetching
them:

.. code-block:: python

   total = await dal.count(dal.unseen_statement(unseen_by=bob))

Marking and Clearing
--------------------

``mark_all_as_seen(user)`` records every notification the user has not yet seen
as seen, and returns how many were marked. Marking the same notification twice
is avoided, so it is safe to call repeatedly.

.. code-block:: python

   marked = await dal.mark_all_as_seen(bob)
   await session.commit()

``Notification.mark_as_unseen(session, user)`` removes only that user's seen
record from a notification and returns ``True`` when a record was removed.
Calling it when the notification is already unseen returns ``False``. The user
must still be a direct recipient or a current member of a targeted group, the
notification must have been sent, and the user must not have cleared it.

.. code-block:: python

   notification = await session.get(Notification, 42)
   if notification is not None:
       changed = await notification.mark_as_unseen(session, bob)
       await session.commit()

``mark_all_as_sent(recipients=None, groups=None)`` flips every matching unsent
notification to sent and returns how many were updated. With no filters, it
marks every unsent notification.

.. code-block:: python

   delivered = await dal.mark_all_as_sent(recipients=[bob], groups=[moderators])
   await session.commit()

``clear_all(user)`` soft deletes every notification the user has already seen,
which is the "clear my inbox" operation. Nothing is removed from the database:
the notifications stay in place for their other recipients and remain visible
through ``deleted()``.

.. code-block:: python

   await dal.clear_all(bob)
   await session.commit()

Updating and Deleting
---------------------

``update_notification(notification_id, is_sent=None, public=None, data=None)``
updates only the fields you pass; a parameter left as ``None`` leaves the
stored value untouched. It raises ``LookupError`` when no notification has that
ID.

.. code-block:: python

   notification = await dal.update_notification(
       notification_id=42,
       is_sent=True,
       data={"delivered_via": "email"},
   )
   await session.commit()

``delete_notification(notification_id, recipient=None, soft_delete=True, actor=None)``
deletes one notification in either of two ways:

- **Soft delete** (the default) records the deletion against ``recipient`` and
  leaves the notification in place for everyone else. A ``recipient`` is
  **required**; without one, ``ValueError`` is raised. The recipient must be
  permitted to delete the notification, or ``PermissionError`` is raised.
- **Hard delete** (``soft_delete=False``) removes the row outright, for every
  recipient. It requires a staff identity passed as ``actor``. A ``recipient``
  may still be given, in which case the notification must also be visible to
  them.

Either way, ``LookupError`` is raised when the notification does not exist or is
not visible to the given recipient. When a recipient is supplied, access is
limited to notifications addressed directly to that identity or to one of its
groups, regardless of staff or superuser status. A hard delete requires a staff
``actor`` even when ``recipient`` is omitted; the DAL enforces the same
staff-only administrative policy as the HTTP endpoints.

.. code-block:: python

   # Hide it from Bob, leave it for everyone else.
   await dal.delete_notification(notification_id=42, recipient=bob)

   # Remove it entirely; the actor must be staff.
   await dal.delete_notification(
       notification_id=42, soft_delete=False, actor=staff_user
   )

   await session.commit()

``delete_many(statement, actor=staff_user)`` permanently deletes every
notification a statement selects, and returns how many rows were removed. A
staff actor is mandatory. The statement must select whole notifications, so
build it with ``display_detail=True``.

.. code-block:: python

   statement = dal.deleted_statement(deleted_by=bob, display_detail=True)

   removed = await dal.delete_many(statement, actor=staff_user)
   await session.commit()

Statement Builders
------------------

Every read method has a ``*_statement`` counterpart that builds the SQLAlchemy
``Select`` and returns it instead of executing it:

- ``all_notifications_statement``
- ``sent_statement``
- ``unsent_statement``
- ``seen_statement``
- ``unseen_statement``
- ``deleted_statement``

They take the same arguments as the methods they mirror, and are synchronous —
nothing has touched the database yet.

They exist because a statement can still be added to. The packaged routes use
them to layer filtering, searching, ordering and pagination on top of a
statement before it runs, which is the role Django's lazy ``QuerySet`` played
in the original package. Your own code can do the same:

.. code-block:: python

   from fastapi_notification import Notification
   from fastapi_notification.repository.queryset import notification as queryset

   statement = dal.unseen_statement(unseen_by=bob, display_detail=True)

   total = await dal.count(statement)

   statement = statement.where(Notification.status == "CRITICAL")
   statement = statement.limit(20).offset(40)

   rows = await queryset.fetch(session, statement, display_detail=True)

Counting before paging, as above, is the usual pattern: ``count()`` reports the
full size of the result set while the paged statement fetches one page of it.

The same statements are what ``get()`` and ``delete_many()`` accept, so a
statement built once can serve as both the visibility rule and the deletion
scope.

Models
------

The package ships its own SQLAlchemy models on a declarative ``Base``:

``Notification``
    The notification itself: ``verb``, ``description``, ``status``, ``link``,
    ``is_sent``, ``public``, ``data`` and ``timestamp``, plus the content type
    and object ID pairs backing the ``actor``, ``target`` and ``action_object``
    generic relations. Its ``recipient``, ``group`` and ``seen_by``
    relationships expose the users and groups involved.

``NotificationRecipient``
    The association between a notification and one of its recipients. A
    notification cannot be addressed to the same user twice.

``NotificationSeen``
    A record that a user has seen a notification, with the time it happened.
    Created through ``NotificationSeen.create()`` or
    ``Notification.mark_as_seen()``, both of which check the user's permission
    first. ``Notification.mark_as_unseen()`` removes only the current user's
    record after checking audience access and per-user soft-deletion state.

``DeletedNotification``
    A record that a user has soft deleted a notification, with the time it
    happened. Soft deletions are stored rather than applied, so the
    notification stays available to its other recipients and remains auditable
    or restorable.

``ContentType``
    Identifies a model taking part in a generic relation, by an ``app_label``
    and a lowercased ``model`` name. Created on demand the first time a model is
    used as an actor, target or action object.

``User``
    An optional example user model: ``username``, ``email``, ``is_active``,
    ``is_staff``, ``is_superuser`` and a ``groups`` collection. It lives on
    ``AuthBase`` rather than the core notification metadata. Applications with
    their own identity models should configure an ``IdentityAdapter``; the
    current-user dependency alone does not select or map a host user table.

``Group``
    A named collection of users that notifications can be addressed to, with
    the permissions it grants.

``Permission``
    A named capability, identified by a ``codename``, that can be attached to a
    group.

Notification statuses
~~~~~~~~~~~~~~~~~~~~~

``NotificationStatus`` is a string enum, so its members can be used
interchangeably with their values:

.. code-block:: python

   from fastapi_notification import NotificationStatus

   await dal.create_notification(
       verb="failed to deploy",
       actor=service,
       status=NotificationStatus.CRITICAL,
   )

The available values are:

``ERROR``
    Critical errors that require immediate attention.

``SUCCESS``
    Successful completion of an operation.

``WARNING``
    Potential issues or concerns that should be addressed.

``INFO``
    General informational messages. This is the default.

``CRITICAL``
    Critical issues that may impact functionality.

``SENSITIVE``
    Notifications related to sensitive data.

``INFRASTRUCTURE``
    Notifications related to system infrastructure.

``NotificationStatus.values()`` returns every value, and
``NotificationStatus.choices()`` returns ``(value, label)`` pairs with the
human readable description of each.

Notification categories and priorities
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``NotificationCategory`` exposes the built-in category keys, while custom
category keys are accepted without requiring a central registry. Keys are
trimmed, lowercased and validated. ``NotificationPriority`` provides the four
supported urgency levels. Both enums are importable from
``fastapi_notification``. See :doc:`taxonomy` for filtering, ordering and summary
breakdowns.
