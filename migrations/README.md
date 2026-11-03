# MySQL 8.4 schema hardening

`versions/20261103_mysql_identity_precision.py` is a reference Alembic revision
for applications with the package's pre-release schema. It is never run during
import or installation. Fresh schemas created from current metadata already use
these types.

The revision changes only opaque identity/deduplication columns to
`VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin`, the shared
`UTCDateTime` columns to `DATETIME(6)`, and quiet-hour/digest wall times to
`TIME(6)`. Binary NO PAD comparison preserves case, accents and trailing spaces;
these are significant in host-owned identifiers. Existing truncated precision
cannot be recovered. SQLite and PostgreSQL operations are explicit no-ops.

Copy the revision into the host application's Alembic environment and attach its
`down_revision` to the application's actual revision chain. Inspect the DDL on a
restored copy of the application's database first. The reference revision accepts
MySQL 8.4 and the standard `utf8mb4_0900_ai_ci` baseline; customized schemas require
an application-specific migration. Run during maintenance with writers stopped
and a verified backup: MySQL DDL implicitly commits, and an operational failure
during DDL can leave a partially applied migration that must be inspected before
resuming. The revision does not create an Alembic environment for the host.

Upgrade preflights every affected column before DDL. Downgrade additionally
refuses to run when any affected timestamp/time contains nonzero microseconds or
distinct identifiers would collapse under the old collation. Resolve the
application's rollback strategy explicitly; the revision never deletes, merges
or truncates data to force rollback. Nullability, server defaults and comments
are carried through each alteration.

The tests in `test_mysql_migration.py` execute upgrade/downgrade and both rollback
rejections against the disposable database selected with `--database-url`.
Never point that test option at an application database: fixtures drop tables.

## Digest claim ownership hardening

`versions/20261103_digest_claim_ownership.py` is a reference Alembic revision
for existing Issue 16/17 digest-batch tables. Attach it to the host application's
revision chain and inspect the resulting DDL before applying it. Stop all digest
workers before upgrading. The revision adds a nullable UUID claim token and a
bounded error-code column, maps existing non-empty raw error messages to the
non-sensitive code `delivery_failed`, resets in-flight `processing` batches to
`pending`, and removes the raw error-text column. The reset ensures workers using
the old protocol cannot finalize batches after the schema transition. The
migration is not run automatically by package installation.

Downgrade recreates the legacy error-text column from the sanitized code and
removes claim-token support. It cannot restore raw provider exception messages
that were intentionally discarded during upgrade. Do not run the downgrade
while workers using the claim-token protocol are active.
