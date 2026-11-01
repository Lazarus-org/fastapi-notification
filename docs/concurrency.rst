Concurrency and transaction behavior
====================================

Notification state is stored per user. The package enforces one seen record and
one soft-deletion record for each ``(notification_id, user_id)`` pair through
database unique constraints.

Idempotent state transitions
----------------------------

``Notification.mark_as_seen()``, ``NotificationSeen.create()`` and
``DeletedNotification.create()`` are idempotent. Repeating an operation returns
or preserves the existing state record rather than raising a duplicate-key
error. The original ``seen_at`` or ``deleted_at`` timestamp is retained.

Bulk ``mark_all_as_seen()`` and ``clear_all()`` operations use an atomic
``INSERT ... SELECT ... ON CONFLICT DO NOTHING`` statement on SQLite and
PostgreSQL. Other SQLAlchemy dialects use savepoints and the same unique
constraints as the concurrency arbiter. MySQL/MariaDB duplicate recovery uses a
locking ``SELECT ... FOR UPDATE`` so a concurrent insert is visible even under
InnoDB's default repeatable-read isolation.

Transaction ownership
---------------------

The package flushes state changes but never commits the host application's
session. The application remains responsible for committing or rolling back
the surrounding transaction. A rollback by the caller also rolls back the
notification state changes. Bulk fallback operations are enclosed in a
savepoint so a failed batch does not leave a partially inserted batch in the
outer transaction.

Database requirements
---------------------

SQLite and PostgreSQL are the native upsert paths. Other SQLAlchemy dialects
use the savepoint fallback, must support savepoints, and must enforce the
declared unique constraints. Concurrency guarantees ultimately depend on the
database correctly enforcing those constraints. Applications should run their
schema migrations before using these operations.
