# Issue 17.2 runtime validation

Completed 2026-11-03T06:58:01.337751+00:00 using CPython 3.15.1 on Windows.

The requested 726-test source is the extracted `fastapi-notification/` tree.
The committed root is the earlier 722-test Issue 17.1 source and was left unchanged.
No new commits, pushes or publication were performed.

| Requested check | Actual result |
|---|---|
| Locked development installation | PASS — `poetry check --lock` and `poetry sync --with dev,database --no-interaction`; 110 locked dependencies plus the editable project, 111 installed distributions. Every non-project version matches the unchanged lockfile. |
| Complete SQLite suite | PASS — **726 collected: 724 passed, 2 skipped**. The skips are the explicitly MySQL-only downgrade refusal cases. |
| Statement coverage | PASS — **100%, 2984 statements, zero missing**; no coverage rule/exclusion changed. |
| PostgreSQL independent-session and scheduling tests | PASS — **29 passed**, including stale-worker ownership rejection and committed final-state checks. |
| MySQL independent-session and scheduling tests | PASS — **29 passed**, with InnoDB, REPEATABLE READ and default strict/ONLY_FULL_GROUP_BY modes retained. |
| Black / isort / docformatter / Pylint / mypy | PASS — all five exited 0; Pylint **10.00/10**, mypy clean in **166 files**. |
| New Alembic revision on PostgreSQL | PASS — actual upgrade and downgrade with normal version stamping against a fresh copy of the complete committed Issue 17.1 Base/AuthBase schema. |
| New Alembic revision on MySQL 8.4.13 | PASS — same full legacy-schema scenario, actual upgrade/downgrade and version table. |

## Corrections found by execution

The first SQLite run already passed 724 cases with the same two skips and 100% coverage. Initial Black/isort and mypy runs failed; real Alembic loading failed on **both** servers. Initial results remain alongside the final evidence.

1. The revision ID and branch label were both `notification_digest_claim_ownership`, causing Alembic to reject its revision map before executing DDL. The 35-character ID also exceeded the default VARCHAR(32) version column. The revision ID is now **`notification_digest_ownership`** (29 characters), distinct from the preserved branch label. The filename is unchanged.
2. The migration regression previously called upgrade/downgrade functions directly, which bypassed revision-map and version-table handling. It now uses real `alembic.command.upgrade`/`downgrade`, loads both reference revisions, checks the stored version and validates the identifier against the real version-column width. All original data/schema assertions remain.
3. Private token/error validators now accept `object` and narrow to `str`, accurately describing their input-validation boundary. This fixes two intentional-invalid-input mypy errors without casts, ignores or weakened checks. Public worker method signatures are unchanged.
4. Applied configured import ordering and Black formatting to the changed scheduling source/tests.

Only four extracted-source files changed; hashes are in [source-corrections.json](source-corrections.json):

- `migrations/versions/20261103_digest_claim_ownership.py`
- `fastapi_notification/repository/manager/scheduling.py`
- `fastapi_notification/tests/repository/test_digest_claim_migration.py`
- `fastapi_notification/tests/scheduling/test_scheduling_dal.py`

## Migration coverage

The seeded tests verified claim-token/error-code column types, processing-to-pending lease reset, cleared claim timestamps, generic replacement of non-null legacy error values, discarded raw error text, preserved unrelated payload/index/check constraints, a correct Alembic version record, and downgrade back to the legacy shape with sanitized error text. The full-schema scenarios created the actual old metadata from the untouched committed root in fresh disposable databases; they did not operate on application data.

The migration is a reference revision: host applications still attach it to their own chain and stop workers for the schema transition. No application database was migrated. Historical error text cannot be restored by downgrade.

## Evidence

- [Full SQLite output](sqlite.log), [XML](sqlite.xml), [coverage JSON](coverage.json).
- [PostgreSQL tests](postgresql-independent.log), [XML](postgresql-independent.xml).
- [MySQL tests](mysql-independent.log), [XML](mysql-independent.xml).
- [PostgreSQL full-schema migration](postgresql-migration-full.json), [log](postgresql-migration-full.log).
- [MySQL full-schema migration](mysql-migration-full.json), [log](mysql-migration-full.log).
- [Black](black.log), [isort](isort.log), [docformatter](docformatter.log), [Pylint](pylint.log), [mypy](mypy.log).
- [Locked install output](locked-install.log), [lock proof](lock-install-proof.json), [installed environment](installed-environment.json).
- [Dependency consistency](dependency-consistency-final.log). The clean uv-created environment intentionally has no pip; uv checked the installed dependency graph without adding an unlocked bootstrap package.
- [Commands, versions, timestamps and exit codes](command-results.json); [machine-readable summary](summary.json).
- [Reproduction controllers](tools/). Copies adjust only their directory-relative paths; original invocations are recorded in the command metadata.

Both PostgreSQL 17.5 and MySQL 8.4.13 used fresh UUID-named disposable databases. All six databases created for initial/final/full-schema scenarios were verified empty and removed. The workspace-owned MySQL instance was shut down; the existing PostgreSQL service was left running. Earlier Issue 17/17.1 evidence was not overwritten. No hosted CI run or additional Python-version matrix is claimed by this checkpoint.
