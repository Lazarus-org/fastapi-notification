# Issue 17.2 — Digest worker ownership hardening

## Assessment

**Implementation completed; full database-backed validation remains pending.**

This checkpoint fixes a correctness and data-minimization defect in the digest batch worker protocol. It is based on the Issue 17.1 source archive and does not add a new product feature.

## Baseline

- Source archive: `fastapi-notification-issue17-1-source.zip`
- Baseline SHA-256: `a292b7544bc5f0d4881c68699bffe256261adb6f29811ac8a5d950e5d1d66070`
- Baseline package version: `1.0.0`
- Python used for this checkpoint: CPython 3.13.5

## Changes

1. Added nullable UUID `claim_token` to `NotificationDigestBatch`.
2. Every successful `claim_batch()` generates and persists a fresh token.
3. `mark_batch_sent()`, `mark_batch_failed()` and `defer_batch()` now require the current token and include it in the conditional update.
4. The token and claim timestamp are cleared when a batch is sent, failed or deferred.
5. `claim_batch()` refreshes the ORM instance after the conditional update so the returned token is the current database value.
6. Replaced raw `last_error` text persistence with a bounded `last_error_code` identifier. Raw provider exception messages are rejected by validation and are not stored.
7. Added a reference Alembic migration. It maps existing non-empty raw error values to `delivery_failed`, resets in-flight `processing` batches to `pending`, and removes the raw text column. Workers must be stopped during migration.
8. Updated scheduling documentation and changelog.
9. Added same-session stale-token checks and an independent-session stale-worker regression test.

## Validation actually executed

| Check | Result | Evidence |
|---|---|---|
| Test discovery | PASS — 726 tests collected | `collection.log` |
| Targeted non-database pytest checks | PASS — 19 tests | `pytest-targeted.log` |
| Python compilation | PASS | `compileall.log` |
| SQLite table DDL compilation | PASS | `ddl-compile.log` |
| PostgreSQL table DDL compilation | PASS | `ddl-compile.log` |
| MySQL table DDL compilation | PASS | `ddl-compile.log` |
| Claim-token validation | PASS | `ddl-compile.log` |
| Error-code validation | PASS | `ddl-compile.log` |
| Alembic reference migration upgrade/downgrade on SQLite | PASS | `migration-smoke.log` |

The complete suite now collects 726 tests (the Issue 17.1 baseline had 722). The 19 passing pytest tests comprise the scheduling calculation tests, a model registration/column test, a pure claim-token/error-code validation test, and the synchronous SQLite migration test.

## Validation not executed

- The database-backed async scheduling tests were not executed in this environment because `aiosqlite` is not installed.
- Installing `aiosqlite` was attempted, but the package index was unreachable (DNS resolution failure).
- The independent-session stale-worker regression test was added but not executed here.
- Full SQLite/PostgreSQL/MySQL test suites were not rerun.
- Black, isort, Pylint, mypy and docformatter were unavailable in this execution environment and were not rerun after these changes.
- Hosted GitHub Actions were not run.

SQL DDL compilation is not represented as database runtime testing. The SQLite migration smoke test is a synchronous SQLite execution and is not a substitute for the full async database suite.

## Migration instructions

For existing Issue 16/17 schemas, attach `migrations/versions/20261103_digest_claim_ownership.py` to the host application's Alembic revision chain. Stop digest workers before upgrading. The migration resets in-flight batches to `pending`, discards raw provider error messages after mapping them to a generic safe code, and adds token ownership. Fresh schemas created from current metadata already contain the new columns and should not run this migration.

## Release recommendation

**NOT READY — BLOCKING VALIDATION REMAINS.**

The stale-worker defect is addressed in source and regression tests. Before release, run the complete 1.0.0 validation suite with `aiosqlite`, PostgreSQL and MySQL, rerun all static quality tools, and execute hosted GitHub Actions. Confirm the migration against disposable copies of supported databases.
