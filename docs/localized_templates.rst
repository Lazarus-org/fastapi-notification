Localized notification templates
================================

``fastapi-notification`` can render notification text from database-backed event
templates. A template is identified by a stable event key and a locale. For
example, ``orders.payment_received`` may have English and Persian translations.

Design guarantees
-----------------

- Templates are application-managed records, not hardcoded package strings.
- The unique key is ``(key, locale)``; registering an existing pair updates it.
- Locale lookup tries the requested locale, its base language, then the configured
  ``default_locale`` passed to the rendering call (``en`` by default).
- Inactive translations are skipped during fallback.
- Interpolation supports simple ``{variable}`` names only. Attribute access,
  indexing, conversions and format expressions are rejected.
- Missing variables and ``None`` values raise ``ValueError`` rather than silently
  producing incomplete notification text.
- The rendered ``verb`` and ``description`` are stored on the notification. Later
  edits to a template do not change historical notification content.
- Template registration and notification creation flush but never commit. The
  application owns the transaction.

Register translations
---------------------

.. code-block:: python

   from fastapi_notification import NotificationTemplateDataAccessLayer

   templates = NotificationTemplateDataAccessLayer(session)
   await templates.register(
       key="orders.payment_received",
       locale="en",
       verb_template="payment received",
       description_template="Order {order_number} has been paid.",
       category="orders",
   )
   await templates.register(
       key="orders.payment_received",
       locale="fa",
       verb_template="پرداخت دریافت شد",
       description_template="پرداخت سفارش {order_number} با موفقیت انجام شد.",
       category="orders",
   )
   await session.commit()

Create a notification from a template
-------------------------------------

.. code-block:: python

   from fastapi_notification import NotificationDataAccessLayer

   dal = NotificationDataAccessLayer(session)
   notification = await dal.create_notification(
       actor=payment,
       recipients=[customer],
       template_key="orders.payment_received",
       locale="fa-IR",
       template_context={"order_number": "ORD-1024"},
       is_sent=True,
   )
   await session.commit()

If ``fa-IR`` is not registered, the resolver tries ``fa`` and then the default
locale. The selected locale is stored on ``notification.locale`` and the event
key on ``notification.template_key``. The text itself is stored in the existing
``verb`` and ``description`` columns.

The ``verb`` argument may be omitted (or set to ``None``) when ``template_key``
is supplied. When no template key is supplied, ``verb`` remains required and
manual notification creation behaves as before.

Template management API
-----------------------

Templates are managed through the Python DAL rather than recipient-facing HTTP
routes. This keeps template authoring under application control and avoids
allowing ordinary notification recipients to modify shared message content.

The DAL exposes:

- ``register(...)``: create or update a key/locale translation.
- ``get(key, locale)``: retrieve one active exact-locale translation.
- ``resolve(key, locale, default_locale="en")``: resolve fallback order.
- ``render(key, locale="en", context=None, default_locale="en")``: render an
  immutable result containing ``verb``, ``description``, ``category``, ``key``
  and the resolved ``locale``.
- ``delete(key, locale)``: delete one translation; returns whether it existed.

Database migration
------------------

The feature adds a ``notification_template`` table and nullable ``template_key``
and ``locale`` columns to ``notification``. Add these changes through the host
application's migration system. ``Base.metadata.create_all()`` creates missing
tables on a new database but does not alter an existing notification table.

No template foreign key is stored on a notification by design: deleting or
updating a template must not invalidate historical notifications.
