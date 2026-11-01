Roles
=====

The API serves the same endpoints to everyone, but what those endpoints return
depends on who is asking. Three roles matter: the ordinary authenticated user,
the staff user, and the superuser.

A role is resolved by the configured :class:`~fastapi_notification.identity.IdentityAdapter`
from the user object returned by your current-user dependency. The default
adapter reads ``is_staff``, ``is_superuser`` and ``groups``. Configure a custom
adapter when your application uses different attribute names or stores group
membership separately. The optional packaged
:class:`~fastapi_notification.models.auth.User` model provides the conventional
attributes.


Authenticated User
------------------

The default role: someone who is signed in but has neither flag set.

**What they see.** Only notifications that were sent *and* are addressed to
them, either as a named recipient or through a group they belong to. A
notification addressed to someone else is invisible — it is absent from
listings, and requesting it by identifier returns ``404`` rather than ``403``,
so the API does not reveal that it exists.

Notifications they have cleared are excluded as well, even though those
notifications still exist for their other recipients.

**What they receive.** The compact representation, carrying a generated
``title`` alongside ``id``, ``description``, ``status``, ``link`` and
``timestamp``. This is read with a narrower query, so listing notifications
does not load recipients, groups and content types that will not be shown.

**What they may do.**

- List and retrieve their own notifications and activities.
- Mark their notifications as seen, one at a time or all at once.
- Clear their own activities, individually or all at once, when
  ``API_INCLUDE_SOFT_DELETE`` is on.

They may **not** permanently delete anything: the two hard-delete routes
return ``403``.

**Rate limit.** ``AUTHENTICATED_USER_THROTTLE_RATE``, 30 requests a minute by
default.


Staff User
----------

A user with ``is_staff`` set. This is the moderator or administrator role.

**What they see.** Every sent notification in the system, not just the ones
addressed to them. Their listings are not narrowed by recipient or group.

**What they receive.** Always the detailed representation, including the
recipients, the groups, everyone who has seen the notification, the content
types behind the actor, target and action object, and the ``data`` payload.
Staff receive this regardless of the ``SERIALIZER_INCLUDE_FULL_DETAILS``
setting.

**What they may do.** Everything an authenticated user may do, and in addition:

- Permanently delete a single notification, when ``API_INCLUDE_HARD_DELETE``
  is on.
- Permanently delete every activity they can see, when
  ``API_INCLUDE_HARD_DELETE`` is on.

Staff also pass the model-level permission checks: they may mark any
notification as seen, or soft-delete any notification, even one that was never
addressed to them.

**Rate limit.** ``STAFF_USER_THROTTLE_RATE``, 100 requests a minute by
default.


Superuser
---------

A user with ``is_superuser`` set. In practice a superuser is also staff, and
the two roles behave alike through the API.

The flag matters in the data access layer: like ``is_staff``, it prevents a
query from being narrowed to the user's own notifications. A superuser who is
*not* also staff therefore sees every sent notification, but is still subject
to the ordinary user throttle rate and is still refused by the hard-delete
routes, which check ``is_staff`` alone.

If you intend someone to have full access, set both flags.


Comparison
----------

===============================  =================  =================  =================
Capability                       Authenticated      Staff              Superuser
===============================  =================  =================  =================
Sees own notifications           Yes                Yes                Yes
Sees others' notifications       No                 Yes                Yes
Detailed representation          Only if configured Always             Only if staff
Mark as seen                     Own only           Any                Any
Soft delete                      Own only           Any                Any
Hard delete routes               No (403)           Yes                Only if staff
Throttle rate                    30/minute          100/minute         30/minute
===============================  =================  =================  =================

The rates shown are the defaults; both are configurable.


Choosing a Representation
-------------------------

Which serializer a request gets is decided by role first and settings second:

1. Staff always receive ``NotificationSerializer``, the detailed one.
2. With ``SERIALIZER_INCLUDE_FULL_DETAILS`` on, everyone receives it.
3. A serializer named in ``SERIALIZER_CLASS`` is used for everyone else.
4. Otherwise ``NotificationDynamicSerializer`` is used, serving the fields in
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
to the built-in checks, so it can narrow access but not widen it.
