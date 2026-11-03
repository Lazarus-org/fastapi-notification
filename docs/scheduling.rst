Quiet Hours and Scheduled Digests
=================================

``fastapi-notification`` provides scheduling primitives but deliberately does
not run a background worker or depend on Celery, APScheduler, or a task queue.
The host application owns the scheduler and delivery provider.

Management API
--------------

The authenticated notification router exposes these user-scoped endpoints:

.. code-block:: text

   GET    /notifications/quiet-hours/
   PUT    /notifications/quiet-hours/
   DELETE /notifications/quiet-hours/?channel=email

   GET    /notifications/digest-schedules/
   PUT    /notifications/digest-schedules/
   DELETE /notifications/digest-schedules/?channel=email

The ``PUT`` quiet-hours body accepts ``channel``, ``start_time``, ``end_time``,
``timezone``, ``enabled`` and ``allow_urgent``. The digest-schedule body accepts
``channel``, ``frequency`` (``daily`` or ``weekly``), ``local_time``,
``timezone``, ``weekday`` (Monday=0 for weekly schedules), and ``enabled``.
The API derives the user identity from authentication; clients cannot supply a
``user_id`` to read or modify another user's schedule.

Quiet hours
-----------

Quiet-hour rules are stored per user and channel. ``*`` is a channel wildcard;
a channel-specific rule takes precedence over the wildcard rule. Times are
local wall-clock times interpreted in an IANA timezone. Overnight windows are
supported (for example, 22:00 through 07:00). Start and end must differ.

.. code-block:: python

   from datetime import time
   from fastapi_notification import NotificationSchedulingDataAccessLayer

   scheduling = NotificationSchedulingDataAccessLayer(session)
   await scheduling.set_quiet_hours(
       user,
       channel="email",
       start_time=time(22, 0),
       end_time=time(7, 0),
       timezone_name="America/Los_Angeles",
       allow_urgent=True,
   )

   quiet = await scheduling.is_quiet(
       user, channel="email", priority="normal"
   )
   release_at = await scheduling.next_allowed_at(user, channel="email")
   await session.commit()

An exact-channel rule overrides the wildcard rule even when that exact rule is
disabled. Urgent notifications bypass quiet hours when ``allow_urgent`` is
true. Quiet hours are a delivery policy; they do not hide or delete inbox
records. Applications should check notification preferences separately.

Digest schedules
----------------

Users can configure one recurring digest schedule per delivery channel. Daily
and weekly schedules use local wall-clock time and an IANA timezone. Weekly
``weekday`` uses Python's convention: Monday is 0 and Sunday is 6.

.. code-block:: python

   from datetime import time

   schedule = await scheduling.set_digest_schedule(
       user,
       channel="email",
       frequency="daily",
       local_time=time(8, 30),
       timezone_name="America/Los_Angeles",
   )
   await session.commit()

The returned ``next_run_at`` is UTC-aware. The next occurrence is computed in
the configured timezone, so the local send time is maintained across daylight
saving changes. For ambiguous or nonexistent local wall-clock times at a DST
transition, Python ``zoneinfo`` fold-0 behavior is used; applications with
stricter DST policies should adjust schedules explicitly.

Scheduler integration
---------------------

A cron job, Celery task, APScheduler job, or application worker can poll due
schedules and create digest batches:

.. code-block:: python

   due_batches = await scheduling.create_due_batches(limit=100)
   await session.commit()

Each batch contains ``user_id``, ``channel``, ``period_start``, ``period_end``,
``scheduled_for`` and a stable database ``id``. If the scheduler was offline,
``create_due_batches`` catches up missed periods in fair rounds, bounded by the
requested batch limit. The worker resolves the host
identity from ``user_id``, queries that user's visible notifications in the
period using the half-open timestamp range ``period_start <= timestamp <
period_end``, applies channel/category preferences and quiet hours, then renders
and sends the digest using the application's provider. For group-addressed
notifications, resolve current memberships for dynamic audiences; snapshot
audiences have already been expanded into individual recipients.

Before sending, claim the batch atomically:

.. code-block:: python

   batch = await scheduling.claim_batch(batch_id)
   if batch is None or batch.claim_token is None:
       return  # another worker owns it, or it is not due

   claim_token = batch.claim_token
   release_at = await scheduling.next_allowed_at(user, channel=batch.channel)
   if release_at is not None:
       await scheduling.defer_batch(
           batch.id, until=release_at, claim_token=claim_token
       )
       await session.commit()
       return

   try:
       # Pass str(batch.id) as the provider's idempotency key when supported.
       await provider.send_digest(user, batch, idempotency_key=str(batch.id))
   except Exception:
       # Persist a stable code, never raw provider exception text or secrets.
       await scheduling.mark_batch_failed(
           batch.id, "provider_delivery_failed", claim_token=claim_token
       )
   else:
       await scheduling.mark_batch_sent(batch.id, claim_token=claim_token)
   await session.commit()

Batch states are ``pending``, ``processing``, ``sent`` and ``failed``. Each
successful claim returns a fresh UUID ``claim_token``. Every completion operation
(``mark_batch_sent``, ``mark_batch_failed`` and ``defer_batch``) requires that
token; stale workers cannot finalize a batch after another worker reclaims it.
The token is cleared when the claim is completed, failed or deferred. A processing
lease older than the default 15 minutes can be reclaimed by another worker.
Failure handling stores a validated, non-sensitive ``error_code`` rather than raw
provider exception text. This is an at-least-once delivery contract:
a worker may crash after a provider accepts a message but before the database
records success. Use the stable batch ID as a provider idempotency key where
the provider supports it. The package cannot guarantee exactly-once delivery
across an external provider and the application's database transaction.

``create_due_batches`` and all state transitions participate in the caller's
transaction. The package never commits on behalf of the host application.


Daylight-saving policy
----------------------

Recurring schedules select the first occurrence (``fold=0``) of an ambiguous
local wall-clock time. A nonexistent local time is interpreted with the offset
before the transition, moving delivery forward by the size of the gap. Each
local calendar date is scheduled once; advancing after the first occurrence
does not create a second batch for the repeated hour. The next normal period
returns to the configured local wall-clock time.

Quiet-hour checks use the actual occurrence of the current local time. When
a quiet window ends in an ambiguous hour, its end uses that occurrence's fold,
so a second-fold delivery is never deferred to an instant already in the past.
