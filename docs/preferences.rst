Notification delivery preferences
=================================

The package stores per-user delivery preferences as category/channel rules.
Rules are private to the user identified by the configured identity adapter.
The default when no rule matches is enabled.

API
---

The notification router exposes these authenticated endpoints:

.. code-block:: http

   GET    /notifications/preferences/
   PUT    /notifications/preferences/
   DELETE /notifications/preferences/?category=orders&channel=email

``GET`` lists the current user's stored rules. ``PUT`` creates or updates one
rule:

.. code-block:: json

   {"category": "orders", "channel": "email", "enabled": false}

Use ``"*"`` as a wildcard for category, channel, or both. For example, a rule
with category ``"*"`` and channel ``"email"`` disables email across categories.
A more-specific category rule can override it. ``DELETE`` removes the exact
rule; omitting the query parameters removes the global wildcard rule.

Precedence
----------

Rules are resolved in this order:

#. Exact category and exact channel.
#. Exact category and wildcard channel.
#. Wildcard category and exact channel.
#. Wildcard category and wildcard channel.

A missing rule returns ``True`` by default. Category and channel names are
trimmed, lowercased, and validated. Names may contain letters, digits, dots,
underscores and hyphens and must start with a letter or digit. Custom categories and
channels are supported. Common channel names include ``in_app``, ``email``,
``sms``, ``push`` and ``webhook``.

Data access layer
-----------------

Use ``NotificationPreferenceDataAccessLayer`` when managing preferences from
application code:

.. code-block:: python

   from fastapi_notification import NotificationPreferenceDataAccessLayer

   preferences = NotificationPreferenceDataAccessLayer(session)
   await preferences.set_preference(
       user, category="*", channel="email", enabled=False
   )
   await preferences.set_preference(
       user, category="security", channel="email", enabled=True
   )

   should_send = await preferences.is_enabled(
       user, category="security", channel="email"
   )  # True
   await session.commit()

Use ``list_for_user`` to retrieve rules and ``reset_preference`` to remove an
override. The data access layer does not commit; the host application owns the
transaction boundary.

Delivery semantics
------------------

Preferences are delivery policy, not inbox visibility. They do not delete,
hide, or mutate notifications already persisted in the inbox. A delivery
integration should call ``is_enabled`` before dispatching a channel message.
The package currently provides the preference store and resolver, not email,
SMS, push or webhook transport implementations. A future delivery adapter can
use the same policy resolver. The host application decides whether a preference
for ``in_app`` suppresses a separate in-app transport event; stored inbox
records remain available.
