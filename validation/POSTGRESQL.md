# PostgreSQL runtime follow-up

Server: PostgreSQL 17.5 on x86_64-windows, compiled by msvc-19.43.34808, 64-bit. Driver: asyncpg 0.32.0; Python 3.15.1; SQLAlchemy 2.1.6.
Server default isolation: read committed.
Dedicated database: fastapi_notification_validation_b60f7139feeb (retained for inspection).

The first real PostgreSQL run passed all 700 existing tests. The expanded final
campaign passes all 706 cases, with no skips, failures or errors. 317
cases use PostgreSQL engine/session fixtures; other cases are unit tests or
intentionally SQLite-specific. SQLite and the Python/minimum-framework matrix
also pass all 706 cases. Full XML/log files are retained.

The follow-up adds a schema/constraint/index parity and FK-enforcement test,
single/bulk permanent-deletion association cleanup checks, concurrent mixed
seen/delete requests, independent asynchronous scoped-key creation and expired
key reclamation, permanent deletion/key release, and partial-work savepoint
rollback. Existing tests execute native upserts/insert-select conflict handling,
notification APIs, preferences, localization, snapshot audiences, digest
claiming/recovery, expiration and UTC round-tripping on the actual server.

The new SQLite race uncovered a real defect: permanent deletion relied on FK
cascades while SQLite FK enforcement is optional. Orphan recipient/state rows
could collide with or attach to a later notification reusing the old integer
ID. The fix explicitly deletes recipient, group, seen, soft-delete and dedup
associations in single deletion, bulk deletion and retention purge. It leaves
commit/rollback ownership with the caller. No schema migration is required.

Evidence: postgresql.xml, postgresql.log, postgresql-server.json,
sqlite-followup.xml, coverage-followup.json, followup-*.xml,
portable-runtime-fixed.log. The original 700-case PG campaign is preserved as
postgresql-initial.xml/log. Build, Twine and clean-wheel smoke checks were
repeated after the implementation fix.

Credentials were entered through getpass without echoing or saving them.
run_postgresql.py passes the URL to pytest in memory and redacts log output.
The source archive contains no saved database password.

MySQL remains BLOCKED and static-quality failures remain. Recommendation:
NOT READY — BLOCKING ISSUES REMAIN.
