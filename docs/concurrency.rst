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

``Notification.mark_as_unseen()`` performs a user-scoped atomic ``DELETE`` of
the matching seen row. Concurrent retries are safe: at most one request removes
the row, while subsequent requests are successful no-ops. The operation never
deletes another recipient's seen row and does not restore notifications that
the user has soft-deleted.

Bulk ``mark_all_as_seen()`` and ``clear_all()`` operations use an atomic
``INSERT ... SELECT ... ON CONFLICT DO NOTHING`` statement on SQLite and
PostgreSQL. MySQL 8.4 uses ``INSERT ... ON DUPLICATE KEY UPDATE id=id``
for models with an auto-increment integer primary key. This acquires a duplicate
row's exclusive lock during insertion and avoids shared-to-exclusive lock
upgrade deadlocks. Its insertion flag uses cursor ``lastrowid``, since affected
row counts can include unchanged duplicates with CLIENT_FOUND_ROWS enabled.
Other models/dialects use savepoints. MySQL-family duplicate lookup uses a
shared current read so concurrent inserts remain visible at REPEATABLE READ
without upgrading the portable fallback's shared duplicate-key lock.

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

SQLite, PostgreSQL and MySQL 8.4 have native upsert paths. Other models/dialects
use the savepoint fallback, must support savepoints, and must enforce the
declared unique constraints. Concurrency guarantees ultimately depend on the
database correctly enforcing those constraints. Applications should run their
schema migrations before using these operations.


Permanent deletion without database cascades
-------------------------------------------

Single and bulk permanent deletion explicitly remove recipient, group,
read-state, soft-deletion and deduplication rows in the caller's transaction.
This keeps SQLite databases without foreign-key enforcement from retaining
orphan state when a deleted integer notification identifier is reused.
The data access layer does not commit these changes; rollback remains owned
by the host application.

MySQL schema types
------------------

Opaque user/group identifiers and deduplication scopes/keys use MySQL 8.4's
``utf8mb4_0900_bin`` NO PAD collation. Case, accents and trailing spaces remain
significant, matching application identity semantics. UTCDateTime and local
wall times retain six fractional digits. Existing schemas require the guarded
reference revision in ``migrations/``; no migration runs automatically.
