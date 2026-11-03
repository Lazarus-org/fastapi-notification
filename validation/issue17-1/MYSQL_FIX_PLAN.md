# Narrow MySQL release-hardening change plan

The first broad implementation was rejected by automatic approval review because it lacked a migration/rollback plan. It did not execute. This proposal is narrowed to actual failures recorded in mysql-initial-runtime.xml and mysql-precision-initial.xml.

## Demonstrated defects

1. On the isolated MySQL 8.4.13 server, default case/accent-insensitive collation lets HostUser read hostuser's inbox and merges distinct opaque deduplication scopes/keys and preferences. Exact identity semantics are part of the existing recipient-isolation contract.
2. Concurrent duplicate seen/deletion records deadlock while upgrading duplicate-key shared locks to FOR UPDATE. The current savepoint fallback cannot restore an outer transaction after a database deadlock.
3. UTCDateTime and local TIME persistence drops accepted microseconds. UTC expiration round-trip loss is reproduced in mysql-precision-initial.xml.

## Exact implementation scope

- Use a MySQL-only binary, NO PAD VARCHAR variant for the ten proven opaque identity/key columns listed in mysql-migration-plan.json. Keep SQLite/PostgreSQL column types and public normalization behavior unchanged. Do not change auth example names, generic relation text fields, notification content, category/channel keys or unrelated timestamps.
- Add DATETIME(6) only to the existing shared UTCDateTime implementation and TIME(6) to quiet-hour/digest local-time columns. Preserve existing non-UTC timestamp behavior.
- Use a native MySQL no-op duplicate update only for single auto-increment integer PK models; derive insertion from the actual cursor lastrowid (not CLIENT_FOUND_ROWS rowcount). Retain portable savepoints for other models. Retrieve duplicates using a shared current read, avoiding stale snapshots and lock upgrades. Validate that the conflicting row matches the requested natural key and raise IntegrityError otherwise.
- Add unit compilation/edge-case tests and real MySQL races. Keep default REPEATABLE READ, caller-owned commits/rollbacks, existing assertions and real integration sessions.

## Migration and rollback

Provide a standalone Alembic reference revision for the pre-release package schema. No migration runs automatically at import/install. Its only DDL targets are the exact package tables/columns in mysql-migration-plan.json. Host applications attach the revision to their own chain.

Upgrade verifies the baseline/target MySQL collations and current column shapes before altering, preserves nullability/defaults/comments and widens precision without rewriting values. Existing truncated microseconds cannot be recovered.

Downgrade performs all safety checks BEFORE any DDL: reject case/accent/space-distinct values that would become identical under the original collation, and reject nonzero microseconds that DATETIME(0)/TIME(0) would lose. It never merges, deletes or truncates data to make rollback pass. Once preflight is safe, it restores the standard MySQL 8.4 baseline collation and precision. Customized application schemas/collations require an explicit application migration rather than an assumed conversion.

MySQL DDL is not transactionally reversible, so the revision requires maintenance-mode execution and a backup for application use. This campaign executes upgrade/downgrade and rejection cases only against the verified fresh workspace-owned MySQL data directory on localhost:33306. No existing production/application database is used or altered. SQLite and PostgreSQL migration paths are explicit no-ops and will be verified as such.

## Validation before delivery

- Real MySQL schema/index/constraint, identifier-isolation, microsecond, independent-session state/dedup/digest and savepoint tests.
- Migration upgrade/downgrade on an empty legacy-shaped schema; rollback rejection on precision-loss/collation-collision data; verify no partial DDL for rejected rollback.
- Complete SQLite/PostgreSQL/MySQL suites, unchanged 100% statement coverage, all configured static checks and interpreter matrix.
- Distribution rebuild and clean wheel checks. Full new evidence remains under validation/issue17-1; original evidence is retained.
