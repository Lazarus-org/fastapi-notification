API Guide
=========

The package exposes two groups of endpoints. **Notifications** are the things
you have not seen yet; **Activities** are the history of everything you have.
Explicitly marking a notification as seen moves it from the first group to the
second. Retrieval requests are read-only and never change notification state.

Both groups are mounted by ``create_router()``:

.. code-block:: python

   from fastapi_notification import create_router

   app.include_router(
       create_router(
           session_dependency=get_session,
           current_user_dependency=get_current_user,
       )
   )

Each group can also be mounted on its own, with its own prefix:

.. code-block:: python

   from fastapi_notification import create_activity_router, create_notification_router

   app.include_router(create_notification_router(prefix="/inbox"))
   app.include_router(create_activity_router(prefix="/history"))


Conditional Routes
------------------

Routes are registered only when their setting allows it. A route you switch off
is not registered at all: it returns ``404``, and it does not appear in the
OpenAPI schema or on the ``/docs`` page. Nothing is registered merely to reject
every request.

.. list-table::
   :header-rows: 1

   * - Setting
     - Routes it controls
   * - ``FASTAPI_NOTIFICATION_API_ALLOW_LIST``
     - Notification inbox, summary and preview, plus the activity listing.
   * - ``FASTAPI_NOTIFICATION_API_ALLOW_RETRIEVE``
     - Both retrieval routes and the per-notification seen action.
   * - ``FASTAPI_NOTIFICATION_API_INCLUDE_SOFT_DELETE``
     - Both soft-delete routes.
   * - ``FASTAPI_NOTIFICATION_API_INCLUDE_HARD_DELETE``
     - Both permanent-deletion routes.

Because settings are read when the router is built, call ``configure()`` before
including the router.


Notifications API
-----------------

.. list-table:: Notifications API
   :header-rows: 1

   * - Method
     - Path
     - Description
   * - GET
     - ``/notifications/``
     - List the notifications you have not seen.
   * - GET
     - ``/notifications/summary/``
     - Return total, unread and read counts for the current user's visible notifications.
   * - GET
     - ``/notifications/preview/``
     - Return the most recent visible notifications, including read-state flags.
   * - POST
     - ``/notifications/mark_all_as_seen/``
     - Mark every unseen notification as seen.
   * - GET
     - ``/notifications/{notification_id}/``
     - Retrieve one unseen notification (read-only).
   * - POST
     - ``/notifications/{notification_id}/mark_as_seen/``
     - Mark one notification as seen.
   * - POST
     - ``/notifications/{notification_id}/mark_as_unseen/``
     - Return one notification to the current user's unseen inbox.

Retrieving a notification is read-only. Use the explicit POST action to mark
one notification as seen. Repeating that POST is harmless and returns
``204 No Content``. The bulk mark-as-seen endpoint also uses POST.

Summary and preview
~~~~~~~~~~~~~~~~~~~

The summary count calculation uses one aggregate query and returns counts for
sent notifications addressed directly to the authenticated user or to one of
their groups. Notifications cleared by that user are excluded. The response is:

.. code-block:: json

   {
     "total": 12,
     "unread": 8,
     "read": 4,
     "by_category": {
       "orders": {"total": 8, "unread": 6, "read": 2},
       "security": {"total": 4, "unread": 2, "read": 2}
     },
     "by_priority": {
       "normal": {"total": 8, "unread": 5, "read": 3},
       "urgent": {"total": 4, "unread": 3, "read": 1}
     }
   }

The preview endpoint returns up to 20 recent notifications (5 by default),
including both read and unread items. Each item includes an ``is_seen`` flag,
``status``, ``category``, ``priority`` and nullable ``expires_at`` timestamp.
Expired notifications are excluded from inbox, activity, summary and preview
responses, including group-addressed items.
It selects only the fields needed for the preview, does not hydrate generic
relations, and uses the same audience restrictions and filter conditions as
the inbox. Preview order is always newest first, regardless of an ``ordering``
query parameter. Both endpoints exclude unsent notifications and notifications
the current user has cleared. The ``limit`` query parameter must be between 1
and 20. A preview response looks like this:

.. code-block:: json

   {
     "results": [
       {
         "id": 42,
         "title": "alice commented on your post 2 minutes ago",
         "description": "alice commented on your post",
         "status": "INFO",
         "category": "orders",
         "priority": "high",
         "link": "https://example.com/posts/42",
         "timestamp": "2026-11-01T12:00:00Z",
         "expires_at": null,
         "is_seen": false
       }
     ]
   }

.. code-block:: bash

   $ curl \
     -H "Authorization: Bearer <token>" \
     "http://localhost:8000/notifications/summary/"

   $ curl \
     -H "Authorization: Bearer <token>" \
     "http://localhost:8000/notifications/preview/?limit=5"


Activities API
--------------

.. list-table:: Activities API
   :header-rows: 1

   * - Method
     - Path
     - Description
   * - GET
     - ``/activities/``
     - List the notifications you have seen.
   * - DELETE
     - ``/activities/clear_activities/``
     - Soft-delete every activity.
   * - DELETE
     - ``/activities/delete_activities/``
     - Staff-only global hard delete.
   * - GET
     - ``/activities/{notification_id}/``
     - Retrieve one activity (read-only).
   * - DELETE
     - ``/activities/{notification_id}/clear_notification/``
     - Soft-delete one activity.
   * - DELETE
     - ``/activities/{notification_id}/delete_notification/``
     - Permanently delete one activity.

The clearing and deletion operations use DELETE; GET requests never change
notification state. Soft deletion records that *this* user cleared the
notification. The row stays in the database and stays visible to its other
recipients. Permanent deletion destroys the row for everyone, which is why it
is restricted to staff and switched off by default. The bulk administrative
route is intentionally global and does not use the staff user's personal
activity listing.

Example Responses
-----------------

List notifications with full details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When ``SERIALIZER_INCLUDE_FULL_DETAILS`` is on, everyone receives the detailed
representation. Staff and superuser roles do not reveal additional fields:

.. code-block:: bash

   $ curl -H "Authorization: Bearer <token>" http://localhost:8000/notifications/

.. code-block:: json

   {
     "count": 1,
     "next": null,
     "previous": null,
     "results": [
       {
         "id": 1,
         "title": "alice liked your post my-first-post 2 minutes ago",
         "recipient": [
           {
             "username": "bob",
             "email": "bob@example.com"
           }
         ],
         "group": [
           {
             "id": 1,
             "name": "moderators",
             "permissions": []
           }
         ],
         "verb": "liked your post",
         "status": "INFO",
         "actor_content_type": "auth.user",
         "target_content_type": "myapp.post",
         "action_object_content_type": null,
         "link": "https://example.com/posts/123",
         "is_sent": true,
         "seen_by": [],
         "public": true,
         "data": {"post_id": 123},
         "timestamp": "2026-07-20T12:00:00Z",
         "expires_at": null
       }
     ]
   }

List notifications with the default summary fields
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ordinary users receive a compact representation, which is read from the
database with a narrower query:

.. code-block:: json

   {
     "count": 1,
     "next": null,
     "previous": null,
     "results": [
       {
         "title": "alice liked your post my-first-post 2 minutes ago",
         "id": 1,
         "description": "alice liked your post my-first-post",
         "status": "INFO",
         "link": "https://example.com/posts/123",
         "timestamp": "2026-07-20T12:00:00Z",
         "expires_at": null
       }
     ]
   }

Setting ``SERIALIZER_FIELDS`` replaces this list with exactly the fields you
name.

Mark all as seen
~~~~~~~~~~~~~~~~

.. code-block:: bash

   $ curl -X POST -H "Authorization: Bearer <token>" \
       http://localhost:8000/notifications/mark_all_as_seen/

.. code-block:: json

   {"detail": "3 Notifications marked as seen."}

Mark one notification as seen
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Retrieval does not mark a notification as seen. Use the explicit POST action:

.. code-block:: bash

   $ curl -i -X POST -H "Authorization: Bearer <token>" \
       http://localhost:8000/notifications/1/mark_as_seen/

Mark one notification as unseen
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use the explicit POST action to remove only the authenticated user's seen
record. Other recipients' read state is unchanged. Repeating the request is
harmless and returns ``204 No Content``. A notification cleared by the current
user is not restored by this action.

.. code-block:: bash

   $ curl -i -X POST -H "Authorization: Bearer <token>" \
       http://localhost:8000/notifications/1/mark_as_unseen/

Clear and delete
~~~~~~~~~~~~~~~~

The four clearing and deletion routes return ``204 No Content`` with an empty
body. Use DELETE for these state-changing operations:

.. code-block:: bash

   $ curl -i -X DELETE -H "Authorization: Bearer <token>" \
       http://localhost:8000/activities/1/clear_notification/

.. code-block:: text

   HTTP/1.1 204 No Content

Not found
~~~~~~~~~

Asking for a notification that does not exist, or that you are not allowed to
see, gives the same answer either way, so the API never reveals that a
notification exists:

.. code-block:: json

   {"detail": "Not found."}


Pagination
----------

Listings are wrapped in an envelope carrying the total count and links to the
neighbouring pages:

.. code-block:: json

   {
     "count": 42,
     "next": "http://localhost:8000/notifications/?limit=10&offset=10",
     "previous": null,
     "results": []
   }

============  ==========================================================
Parameter     Behaviour
============  ==========================================================
``limit``     Page size. Defaults to 10, minimum 1, maximum 100.
``offset``    How many items to skip. Defaults to 0.
============  ==========================================================

A limit above the maximum is capped rather than rejected, and a limit that is
missing, negative or not a number falls back to the default. Page links
preserve your other query parameters, so filtering and ordering survive a move
between pages.

Setting ``API_PAGINATION_CLASS`` to ``None`` switches pagination off, and
listings then return a bare JSON array.


Filtering, Ordering and Search
------------------------------

====================  ==============================================================
Parameter             Effect
====================  ==============================================================
``group__id``         Only notifications addressed to this group.
``recipient__id``     Only notifications addressed to this recipient.
``status``            Only notifications with this status.
``category``          Only notifications with this built-in or custom category key.
``priority``          Only notifications with this priority (``low``, ``normal``,
                      ``high`` or ``urgent``).
``public``            Only public, or only private, notifications.
``timestamp_after``   Only notifications at or after this time.
``timestamp_before``  Only notifications at or before this time.
``search``            Case-insensitive match across ``API_SEARCH_FIELDS``.
``ordering``          Order by a field in ``API_ORDERING_FIELDS``.
====================  ==============================================================

.. code-block:: bash

   $ curl -H "Authorization: Bearer <token>" \
       "http://localhost:8000/notifications/?category=orders&priority=urgent&ordering=-priority&limit=20"

Prefix the ordering field with ``-`` to sort descending. Only fields listed in
``API_ORDERING_FIELDS`` are honoured — anything else is ignored rather than
raising — so a client cannot sort by an arbitrary column. Listings are ordered
newest first when no ordering is given. Priority ordering uses the explicit
``low < normal < high < urgent`` rank; ``ordering=-priority`` puts urgent items
first and uses newest-first ordering as the tie-breaker.

The ``search`` term is matched case-insensitively against every field named in
``API_SEARCH_FIELDS``, which defaults to ``verb`` and ``description``.

A different filter set can be supplied through ``API_FILTERSET_CLASS``.


Throttling
----------

Requests are rate limited per user over a sliding window:

=================  ==================================================  ==============
Role               Setting                                             Default
=================  ==================================================  ==============
Authenticated      ``FASTAPI_NOTIFICATION_AUTHENTICATED_USER_THROTTLE_RATE``  30/minute
Staff              ``FASTAPI_NOTIFICATION_STAFF_USER_THROTTLE_RATE``          100/minute
=================  ==================================================  ==============

Rates are written as ``number/time_unit``, where the unit is ``second``,
``minute``, ``hour`` or ``day``. Exceeding the limit returns ``429`` with a
``Retry-After`` header:

.. code-block:: json

   {"detail": "Request was throttled. Expected available in 42 seconds."}

The default throttle records request times in memory, which is enough for a
single process. If you run several workers, subclass
``RoleBasedUserRateThrottle``, override ``get_history()`` to use a shared store
such as Redis, and point ``API_THROTTLE_CLASS`` at your subclass. Setting
``API_THROTTLE_CLASS`` to ``None`` turns throttling off.


Permissions
-----------

Every route requires an authenticated user. If your current-user dependency
returns ``None``, the response is ``401``:

.. code-block:: json

   {"detail": "Authentication credentials were not provided."}

The two permanent-deletion routes additionally require the user to be staff,
and return ``403`` otherwise. This administrative permission is separate from
personal notification visibility: staff and superusers still see only their
own notifications and those addressed to their groups. A superuser who is not
also staff does not satisfy the hard-delete guard.

.. code-block:: json

   {"detail": "You do not have permission to perform this action."}

An extra permission can be applied to every route through
``API_EXTRA_PERMISSION_CLASS``. The class is instantiated and called with the
request and the user; returning a falsy value rejects the request with ``403``.
Both synchronous and asynchronous implementations work:

.. code-block:: python

   class OnlyVerifiedUsers:
       async def __call__(self, request, user) -> bool:
           return user.is_verified


   configure(API_EXTRA_PERMISSION_CLASS="myapp.permissions.OnlyVerifiedUsers")

Beyond these route-level checks, the data itself is scoped to the caller: a
listing only ever contains notifications addressed to that user or to a group
they belong to, so one user cannot read another's notifications by guessing an
identifier. See :doc:`roles` for how this differs by role.

Notification creation idempotency
---------------------------------

Applications create notifications through ``NotificationDataAccessLayer``.
For retryable event sources, use a stable ``deduplication_key`` and a scope
that represents the key's uniqueness boundary. Reusing an active scoped key
returns the original notification without changing its recipients or content.
See :ref:`idempotent-notification-creation` in the usage guide for the full
contract and expiration behavior.


Notification preferences
-------------------------

Users can manage their own delivery preferences through three authenticated
endpoints:

.. code-block:: http

   GET    /notifications/preferences/
   PUT    /notifications/preferences/
   DELETE /notifications/preferences/?category=orders&channel=email

``GET`` returns the caller's stored rules. ``PUT`` creates or replaces one rule
using a JSON body:

.. code-block:: json

   {"category": "orders", "channel": "email", "enabled": false}

Use ``"*"`` for a wildcard category or channel. For example,
``{"category":"*","channel":"email","enabled":false}`` disables email
for all categories unless a more-specific rule overrides it. ``DELETE`` removes
the specified rule; omitting both query parameters resets the global wildcard
rule. A missing rule defaults to enabled.

Rule precedence is, in order: exact category and channel; exact category and
wildcard channel; wildcard category and exact channel; global wildcard. Category
and channel keys are normalized to lowercase and may contain lowercase letters,
digits, dots, underscores and hyphens. Custom channel names are supported.

Preferences are delivery policy, not inbox visibility. They do not delete,
hide, or change notifications already persisted for the user. A delivery
integration should consult ``NotificationPreferenceDataAccessLayer.is_enabled``
before dispatching a channel message:

.. code-block:: python

   from fastapi_notification import NotificationPreferenceDataAccessLayer

   preferences = NotificationPreferenceDataAccessLayer(session)
   if await preferences.is_enabled(
       user, category=notification.category, channel="email"
   ):
       await email_provider.send(notification)

The package currently provides the preference store and policy resolver; it
does not itself send email, SMS, push or webhook messages. Delivery adapters
introduced by later integrations can use the same resolver. The in-app inbox
remains available independently of a channel preference unless the host
application explicitly chooses otherwise in its delivery workflow.
