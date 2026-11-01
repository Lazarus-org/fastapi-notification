Settings
========

Every setting has a working default, so the package runs without any
configuration at all. When you do need to change something, you can register
values from Python or supply them through the process environment.

How Settings Are Resolved
-------------------------

Settings are resolved in this order, and the first source that has a value
wins:

1. Values registered through ``configure(**settings)``.
2. Environment variables prefixed with ``FASTAPI_NOTIFICATION_``.
3. The packaged defaults.

Registering values from Python is the more convenient option for applications
that already centralise their configuration in code. The prefix is optional
here: ``configure()`` adds it for you, so ``API_ALLOW_LIST`` and
``FASTAPI_NOTIFICATION_API_ALLOW_LIST`` are the same setting.

.. code-block:: python

   from fastapi_notification import configure

   configure(
       API_INCLUDE_HARD_DELETE=True,
       API_ORDERING_FIELDS=["id", "timestamp"],
   )

The same settings through the environment, where the prefix is required:

.. code-block:: bash

   export FASTAPI_NOTIFICATION_API_INCLUDE_HARD_DELETE=true
   export FASTAPI_NOTIFICATION_API_ORDERING_FIELDS='["id", "timestamp"]'

``configure()`` rebuilds the active configuration and returns it. To discard
every value you registered and fall back to the environment and the defaults,
call ``reset_config()``:

.. code-block:: python

   from fastapi_notification import reset_config

   reset_config()

Configure the package **before** building a router. A router reads its settings
when it is created, and a route disabled in settings is never registered.

Environment Value Coercion
~~~~~~~~~~~~~~~~~~~~~~~~~~

Environment variables are strings, so their values are coerced based on the
type of the setting's default:

- **Boolean settings** accept ``1``, ``true``, ``yes`` or ``on`` for true, and
  ``0``, ``false``, ``no`` or ``off`` for false. Matching is case insensitive
  and surrounding whitespace is ignored. A value that matches neither list is
  left as the raw string, which then fails startup validation.
- **List settings**, and settings whose default is ``None``, are parsed as
  JSON. A value that is not valid JSON is left as the raw string.
- **Everything else**, including throttle rates and class paths, is used as the
  raw string.

Values registered through ``configure()`` are never coerced; pass them as the
Python types you want.

Class settings accept either an importable dotted path or the class object
itself. A path that cannot be imported resolves to ``None`` at runtime and is
reported by the startup checks.

Example Configuration
---------------------

.. code-block:: python

   from fastapi_notification import configure

   configure(
       IDENTITY_ADAPTER="myapp.identity.AppIdentityAdapter",
       API_INCLUDE_SOFT_DELETE=True,
       API_INCLUDE_HARD_DELETE=True,
       API_ALLOW_LIST=True,
       API_ALLOW_RETRIEVE=True,
       SERIALIZER_INCLUDE_FULL_DETAILS=False,
       SERIALIZER_EXCLUDE_NULL_FIELDS=True,
       SERIALIZER_FIELDS=["id", "description", "status", "timestamp"],
       USER_SERIALIZER_FIELDS=["username", "email"],
       USER_SERIALIZER_CLASS="myapp.serializers.CompactUserSerializer",
       AUTHENTICATED_USER_THROTTLE_RATE="60/minute",
       STAFF_USER_THROTTLE_RATE="200/minute",
       API_ORDERING_FIELDS=["id", "timestamp"],
       API_SEARCH_FIELDS=["verb", "description"],
       API_EXTRA_PERMISSION_CLASS="myapp.permissions.IsNotificationAdmin",
   )

Settings Reference
------------------

IDENTITY_ADAPTER
~~~~~~~~~~~~~~~~

**Type:** ``IdentityAdapter`` (class, instance, or dotted path) — **Default:**
``fastapi_notification.identity.IdentityAdapter``

The adapter is the integration boundary between notification persistence and
the host application's authentication and group-membership models. It supplies
normalized user and group identifiers, membership lookups, staff/superuser
flags, and optional user/group resolution for API serialization.

The default adapter uses conventional identity attributes and returns ID-only
references without querying user or group tables. Applications using the
optional package ``User`` and ``Group`` models can opt into
``BuiltInIdentityAdapter``. Applications with custom identity models can
subclass ``IdentityAdapter`` and configure that class here (or with
``configure(IDENTITY_ADAPTER=...)``). See :doc:`identity` for examples.

The core notification metadata does not include the optional authentication
tables. Those models use the separate ``AuthBase`` metadata and are not required
when a host adapter is configured.


Every name below is written without its prefix. In the environment, prepend
``FASTAPI_NOTIFICATION_``.

API_INCLUDE_SOFT_DELETE
~~~~~~~~~~~~~~~~~~~~~~~

**Type:** ``bool`` — **Default:** ``True``

Whether the activity router registers its soft delete routes. A soft delete
records the deletion against the user who performed it, hiding the notification
from them while leaving it intact for its other recipients. When this is
``False`` the routes are never registered, so they are absent from the
application and from its OpenAPI schema.

API_INCLUDE_HARD_DELETE
~~~~~~~~~~~~~~~~~~~~~~~

**Type:** ``bool`` — **Default:** ``False``

Whether the activity router registers its hard delete routes, which remove the
notification row outright for everyone. Off by default because the deletion
cannot be undone.

SERIALIZER_INCLUDE_FULL_DETAILS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** ``bool`` — **Default:** ``False``

Whether every response carries the full notification representation, including
the resolved actor, target, action object, recipients and groups, rather than
the summary fields. Turning this on also forces queries to select whole
notification instances instead of summary columns. Staff and superuser status
does not override this setting.

SERIALIZER_EXCLUDE_NULL_FIELDS
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** ``bool`` — **Default:** ``False``

Whether fields with empty values are stripped from serialized responses instead
of being emitted as ``null``.

API_ALLOW_LIST
~~~~~~~~~~~~~~

**Type:** ``bool`` — **Default:** ``True``

Whether the read/list routes are registered. Setting this to ``False`` disables
the notification inbox, notification summary and preview, and the activity list.

API_ALLOW_RETRIEVE
~~~~~~~~~~~~~~~~~~

**Type:** ``bool`` — **Default:** ``True``

Whether the retrieve-by-ID routes and the per-notification mark-as-seen action
are registered. Setting this to ``False`` disables single-notification
retrieval and the individual seen action on both routers.

SERIALIZER_FIELDS
~~~~~~~~~~~~~~~~~

**Type:** ``Optional[List[str]]`` — **Default:** ``None``

The exact fields the dynamic notification serializer emits. When left unset,
the serializer emits a generated ``title`` alongside the packaged summary
fields ``id``, ``description``, ``status``, ``link`` and ``timestamp``. When
set, exactly the listed fields are returned, and setting it also forces queries
to select whole notification instances.

Valid entries are ``title`` plus any serializable field of the ``Notification``
model; anything else is reported by the startup checks.

SERIALIZER_CLASS
~~~~~~~~~~~~~~~~

**Type:** ``Optional[Type[Any]]`` (class or dotted path) — **Default:** ``None``

A serializer class used for notifications in place of the packaged dynamic
serializer. When unset, ``NotificationDynamicSerializer`` is used unless
``SERIALIZER_INCLUDE_FULL_DETAILS`` is enabled, in which case
``NotificationSerializer`` is used. Role flags do not affect serializer choice.
Setting it also forces queries to select whole notification instances.

USER_SERIALIZER_FIELDS
~~~~~~~~~~~~~~~~~~~~~~

**Type:** ``List[str]`` — **Default:** ``["id"]``

The user fields included when a notification's related users are serialized.
The default is the normalized identity identifier, so serialization does not
assume that the host user model exposes a username or email field. Configure
this list to expose host-specific fields when ``resolve_users`` returns host
user objects. The list must not be empty.

USER_SERIALIZER_CLASS
~~~~~~~~~~~~~~~~~~~~~

**Type:** ``Optional[Type[Any]]`` (class or dotted path) — **Default:** ``None``

A serializer class used for users in place of the packaged ``UserSerializer``.

GROUP_SERIALIZER_CLASS
~~~~~~~~~~~~~~~~~~~~~~

**Type:** ``Optional[Type[Any]]`` (class or dotted path) — **Default:** ``None``

A serializer class used for groups in place of the packaged
``GroupSerializer``.

AUTHENTICATED_USER_THROTTLE_RATE
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** ``str`` — **Default:** ``"30/minute"``

The request rate allowed for ordinary authenticated users. The format is
``number/time_unit``, where the time unit is one of ``second``, ``minute``,
``hour`` or ``day``.

STAFF_USER_THROTTLE_RATE
~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** ``str`` — **Default:** ``"100/minute"``

The request rate allowed for users whose ``is_staff`` flag is set. Same format
as above.

API_THROTTLE_CLASS
~~~~~~~~~~~~~~~~~~

**Type:** ``Optional[Type[Any]]`` (class or dotted path) — **Default:**
``"fastapi_notification.api.throttlings.role_base_throttle.RoleBasedUserRateThrottle"``

The class enforcing the two rates above. The default picks the rate to apply
from the caller's role. Setting this to ``None`` removes the throttling
dependency from the routers entirely.

API_PAGINATION_CLASS
~~~~~~~~~~~~~~~~~~~~

**Type:** ``Optional[Type[Any]]`` (class or dotted path) — **Default:**
``"fastapi_notification.api.paginations.limit_offset_pagination.DefaultLimitOffSetPagination"``

The class applying limit and offset to listings and wrapping the results in a
paginated envelope. Setting this to ``None`` switches pagination off: listings
then return the bare list of results.

API_EXTRA_PERMISSION_CLASS
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** ``Optional[Type[Any]]`` (class or dotted path) — **Default:**
``None``

An additional permission check applied to every route in both routers, on top
of the authentication requirement. The configured class must have a
no-argument constructor and a callable ``__call__(request, user)`` method; the
method may be synchronous or asynchronous. A falsy result rejects the request
with ``403``. When unset, no extra check is added.

API_FILTERSET_CLASS
~~~~~~~~~~~~~~~~~~~

**Type:** ``Optional[Type[Any]]`` (class or dotted path) — **Default:**
``None``

The filter set backing the query parameters of the listing routes. When unset,
the packaged ``NotificationFilter`` is used.

API_ORDERING_FIELDS
~~~~~~~~~~~~~~~~~~~

**Type:** ``List[str]`` — **Default:** ``["id", "timestamp", "public"]``

The notification fields a client may order listings by. An ordering request
naming a field outside this list is ignored. The list must not be empty.

API_SEARCH_FIELDS
~~~~~~~~~~~~~~~~~

**Type:** ``List[str]`` — **Default:** ``["verb", "description"]``

The notification fields a search query is matched against. The list must not be
empty.

Startup Validation
------------------

The settings are validated when a router is built, so a misconfiguration
surfaces at startup rather than on the first request.

``run_checks()`` runs the validation and raises ``ImproperlyConfigured`` if
anything is wrong. The exception lists every problem it found at once, rather
than stopping at the first, so a broken configuration can be fixed in a single
pass. The individual errors are also available on the exception's ``errors``
attribute.

.. code-block:: python

   from fastapi_notification.settings.checks import ImproperlyConfigured, run_checks

   try:
       run_checks()
   except ImproperlyConfigured as exc:
       for error in exc.errors:
           print(error)

``check_notification_settings()`` performs the same validation but returns the
list of errors instead of raising, which is useful for a health check or a
management command:

.. code-block:: python

   from fastapi_notification.settings.checks import check_notification_settings

   errors = check_notification_settings()
   if errors:
       ...

Each error carries a message, a stable identifier and usually a hint on how to
fix it. The checks cover:

- Every boolean setting actually holds a boolean.
- ``SERIALIZER_FIELDS``, ``USER_SERIALIZER_FIELDS``, ``API_ORDERING_FIELDS``
  and ``API_SEARCH_FIELDS`` are non-empty lists of strings.
  ``SERIALIZER_FIELDS`` may also be ``None``, and its entries are checked
  against ``title`` plus the serializable fields of the ``Notification`` model.
- ``AUTHENTICATED_USER_THROTTLE_RATE`` and ``STAFF_USER_THROTTLE_RATE`` read as
  ``number/time_unit`` with a recognised time unit.
- Every class setting is either ``None``, a class, or a string naming an
  importable class.
