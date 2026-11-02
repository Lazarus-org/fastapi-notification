Notification Categories and Priorities
======================================

Notification ``status``, ``category`` and ``priority`` are separate concepts.
They are stored independently and can be filtered independently.

Status
------

``status`` describes the notification's nature or state. Existing status values
remain unchanged for backward compatibility, including ``INFO``, ``SUCCESS``,
``WARNING``, ``ERROR``, ``CRITICAL``, ``SENSITIVE`` and ``INFRASTRUCTURE``.

Category
--------

``category`` groups notifications by application domain. The built-in keys are:

- ``general`` (the default)
- ``system``
- ``security``
- ``social``
- ``financial``
- ``orders``
- ``marketing``

Applications may use custom keys, including
namespaced keys such as ``com.example.billing``. Keys are stripped, normalized
to lowercase and must contain 1–64 lowercase letters, digits, dots, underscores
or hyphens; the first character must be a letter or digit.

Priority
--------

``priority`` describes urgency, not the type of event. The supported values are:

+------------+-------+
| Value      | Rank  |
+============+=======+
| ``low``    | 1     |
+------------+-------+
| ``normal`` | 2     |
+------------+-------+
| ``high``   | 3     |
+------------+-------+
| ``urgent`` | 4     |
+------------+-------+

The default is ``normal``. Priority is not inferred from status or category.

Creating and updating
---------------------

.. code-block:: python

   notification = await dal.create_notification(
       verb="payment failed",
       actor=payment,
       recipients=[customer],
       status="ERROR",
       category="financial",
       priority="high",
       is_sent=True,
   )

   await dal.update_notification(
       notification.id,
       category="orders",
       priority="urgent",
   )

Filtering and ordering
---------------------

The notification filter accepts ``category`` and ``priority`` query parameters:

.. code-block:: text

   GET /notifications/?category=orders&priority=urgent

Priority ordering uses the explicit rank. ``ordering=-priority`` sorts urgent
notifications first; notifications with equal priority are ordered newest first.
Both fields are included in standard notification and preview representations.

Summary breakdowns
------------------

``GET /notifications/summary/`` retains its top-level ``total``, ``unread`` and
``read`` counts and adds ``by_category`` and ``by_priority`` mappings. Each key
maps to a ``total``/``unread``/``read`` breakdown. The breakdowns are calculated
from the same recipient-scoped, expiration-aware query as the top-level counts.
