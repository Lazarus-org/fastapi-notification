Roles and Permissions
=====================

The package distinguishes notification audience membership from administrative
capabilities. An authenticated user's staff or superuser flag does **not** grant
access to another user's personal notifications.

A role is resolved by the configured
:class:`~fastapi_notification.identity.IdentityAdapter` from the user object
returned by your current-user dependency. The default adapter reads
``is_staff``, ``is_superuser`` and ``groups``. Configure a custom adapter when
your application uses different attribute names or stores group membership
separately. The optional packaged
:class:`~fastapi_notification.models.auth.User` model provides the conventional
attributes.


Notification Audience
---------------------

Every authenticated user, regardless of role, can see only notifications that
were sent and addressed to them directly or through a group they belong to.
The audience rules apply consistently to:

- Notification listings and retrieval.
- Activity listings and retrieval.
- Mark-as-seen operations.
- Soft deletion and clearing operations.
- Model-level permission checks.

A notification addressed to someone else is invisible: it is absent from
listings, and requesting it by identifier returns ``404`` rather than ``403``.
This avoids revealing whether another user's notification exists. A legacy
``seen`` association does not bypass the audience check.

Notifications a user has cleared are excluded from that user's views even though
they remain available to other recipients.


Authenticated User
------------------

An authenticated user can:

- List and retrieve notifications addressed to them directly or through their
groups.
- Mark those notifications as seen, individually or in bulk.
- List, retrieve and clear their own activities, individually or in bulk, when
  ``API_INCLUDE_SOFT_DELETE`` is on.

They cannot permanently delete notifications through the API. The hard-delete
routes return ``403`` unless the caller satisfies the explicit administrative
guard.

**Representation.** The compact representation is used by default. Full details
are available only when ``SERIALIZER_INCLUDE_FULL_DETAILS`` is enabled or a
custom serializer/field configuration requires them. Staff and superuser flags
do not change the representation.

**Rate limit.** ``AUTHENTICATED_USER_THROTTLE_RATE``, 30 requests a minute by
default.


Staff User
----------

A user with ``is_staff`` set.

**What they see.** The same personal notification audience as every other
user: direct recipients and groups they belong to. Staff status does not widen
list, retrieve, activity, seen, or soft-delete access.

**What they may do.** In addition to ordinary personal notification operations,
staff users may use the two permanent-deletion routes when
``API_INCLUDE_HARD_DELETE`` is enabled. These routes are separately guarded by
staff authorization:

- Permanently delete a single notification by ID.
- Permanently delete sent notifications through the administrative bulk-delete
  route, optionally narrowed by the configured filters.

The bulk administrative operation is intentionally global; it does not use
the administrator's personal activity listing. It is destructive and is
therefore disabled by default.

Staff status alone does not grant model-level permission to mark or soft-delete
another user's notification.

**Rate limit.** ``STAFF_USER_THROTTLE_RATE``, 100 requests a minute by
default.


Superuser
---------

A user with ``is_superuser`` set.

**What they see and may do.** A superuser has the same personal notification
audience and model-level permissions as every other authenticated user.
Superuser status alone does not grant access to another user's notifications
and does not satisfy the staff-only permanent-deletion guard.

An application may set both ``is_superuser`` and ``is_staff`` when it intends a
superuser to use the package's staff-only administrative deletion routes.

**Rate limit.** A superuser who is not staff uses the ordinary authenticated
user rate. A superuser who is also staff uses the staff rate.


Comparison
----------

====================================  ========================  ========================  ========================
 Capability                            Authenticated             Staff                     Superuser
====================================  ========================  ========================  ========================
 Sees own notifications                Yes                       Yes                       Yes
------------------------------------  ------------------------  ------------------------  ------------------------
 Sees group notifications              Yes                       Yes                       Yes
------------------------------------  ------------------------  ------------------------  ------------------------
 Sees others' notifications            No                        No                        No
------------------------------------  ------------------------  ------------------------  ------------------------
 Detailed representation               Only if configured        Only if configured        Only if configured
------------------------------------  ------------------------  ------------------------  ------------------------
 Mark as seen                          Own/groups only           Own/groups only           Own/groups only
------------------------------------  ------------------------  ------------------------  ------------------------
 Soft delete                           Own/groups only           Own/groups only           Own/groups only
------------------------------------  ------------------------  ------------------------  ------------------------
 Single hard-delete route              No (403)                  Yes                       Only if staff
------------------------------------  ------------------------  ------------------------  ------------------------
 Bulk administrative deletion          No (403)                  Yes                       Only if staff
------------------------------------  ------------------------  ------------------------  ------------------------
 Throttle rate                         30/minute                 100/minute                30/minute*
------------------------------------  ------------------------  ------------------------  ------------------------

* A superuser who is also staff receives the staff rate. The rates shown are
the defaults; both are configurable.


Choosing a Representation
-------------------------

The representation is decided by explicit serializer settings, never by role:

1. With ``SERIALIZER_INCLUDE_FULL_DETAILS`` on, ``NotificationSerializer`` is
   used for everyone.
2. A serializer named in ``SERIALIZER_CLASS`` is used when configured.
3. Otherwise ``NotificationDynamicSerializer`` is used, serving the fields in
   ``SERIALIZER_FIELDS`` if that is set, and the compact defaults if not.


Beyond These Roles
------------------

If your application has a notion of access that these three flags do not
capture, add it with ``API_EXTRA_PERMISSION_CLASS``. The class you name is
applied to every route in both groups, and receives the request and the user:

.. code-block:: python

   class OnlyVerifiedUsers:
       async def __call__(self, request, user) -> bool:
           return user.is_verified


   configure(API_EXTRA_PERMISSION_CLASS="myapp.permissions.OnlyVerifiedUsers")

Returning a falsy value rejects the request with ``403``. This runs in addition
to the built-in checks, so it can narrow access but not widen it. The dedicated
staff guard for hard deletion remains separate.
