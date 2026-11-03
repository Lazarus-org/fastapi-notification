# Issue 17.1 change report

This continues the existing Issue 17 working tree. No commit, tag, push, publication,
or hosted workflow execution was performed. Original `validation/` reports and
logs are retained. `baseline.patch`, `baseline-git-status.log` and
`baseline-source-checksums.json` record the entry state.

## Formatting and static analysis

- **Root cause:** accumulated formatting/docstring/import differences, dynamic ORM
  result types, inaccurate projections, incompatible overrides, and several
  functions combining too many responsibilities. Pylint 3/Astroid 3 also produced
  incorrect SQLAlchemy generic/aggregate inference on the validation environment.
- **Resolution:** apply configured formatters; make public read APIs use precise
  overloads; type projections, validators, DML results, identity caches and config
  class loading; retain assertions while annotating tests. Split audience
  hydration, read operations, deduplication validation and route registration into
  focused helpers. Upgrade the development Pylint minimum to the actually tested
  4.1.3/Astroid 4 combination and refresh the lockfile. Remove the obsolete
  `suggestion-mode` option rejected by Pylint 4.
- **Files:** package Python files, `pyproject.toml`, `poetry.lock`; new
  `repository/manager/read.py`, `repository/queryset/audience.py`,
  `utils/sqlalchemy.py`, and test-only `tests/typing_helpers.py`.
- **Verification:** five `quality-*.log` files and full regression matrix. No mypy
  check, production coverage source, coverage threshold or global disabled-message
  list was weakened. Narrow inline framework/public-signature waivers and external
  typing boundaries are explained in `STATIC_ANALYSIS.md`. Test doubles remain
  confined to existing unit-test boundaries; integration fixtures use real sessions.

## Compound SELECT bulk insertion

- **Root cause:** a `CompoundSelect` has no `.where()` for SQLite's ON CONFLICT
  parser disambiguation. PostgreSQL additionally cannot append Python-side default
  columns directly to a compound INSERT source.
- **Resolution:** project compound sources through a plain SELECT before native
  insertion. Preserve Python defaults; add SQLite's WHERE only on SQLite.
- **Files:** `models/state.py`, `tests/models/test_state.py`.
- **Regression:** `test_native_bulk_insert_accepts_union_sources` uses actual
  sessions, duplicate sources and repeated insertion, verifying exactly one state
  row. PostgreSQL's initial compile failure is retained in
  `postgresql-compound-initial.*`.

## MySQL opaque identifier isolation

- **Root cause:** MySQL's default case/accent-insensitive collation let distinct
  opaque host identities share inbox results/preferences and merged distinct
  deduplication scopes/keys.
- **Resolution:** a MySQL-only `VARCHAR(255)` variant with utf8mb4_0900_bin NO PAD
  comparison on the ten affected user/group/scope/key columns. SQLite/PostgreSQL
  types and normalization behavior are preserved. Other text columns are unchanged.
- **Files:** `models/column_types.py`, associations, recipient/seen/deletion,
  preference/quiet-hour/digest and deduplication models; guarded reference migration.
- **Regression:** case, accent, trailing-space recipient tests; distinct scope/key,
  preference, quiet-hour and group tests in `test_database_runtime.py`.

## MySQL temporal precision

- **Root cause:** MySQL's default DATETIME/TIME precision discarded accepted
  microseconds, including notification expiration.
- **Resolution:** MySQL DATETIME(6) for the shared UTCDateTime implementation and
  TIME(6) for quiet-hour/digest wall times. Unrelated legacy timestamps retain their
  types. Previously lost microseconds cannot be recovered by migration.
- **Files:** `models/base.py`, `models/column_types.py`, quiet-hour/digest models,
  reference migration.
- **Regression:** exact UTC expiration and local-time round trips on real backends.

## MySQL duplicate-state races

- **Root cause:** competing duplicate INSERTs held shared duplicate-key locks and
  upgraded them to exclusive locks during FOR UPDATE recovery. Deadlocks rolled
  back InnoDB's outer transaction and invalidated savepoints at REPEATABLE READ.
- **Resolution:** native no-op duplicate updates for auto-increment integer keys,
  acquiring the exclusive lock during INSERT. Use cursor lastrowid rather than
  CLIENT_FOUND_ROWS rowcount for insertion counts. Look up duplicates with a shared
  current read. Retain savepoints for other models; reject conflicts that do not
  match the requested natural key. Do not commit/roll back the caller's transaction.
- **Files:** `models/state.py`, `tests/models/test_state.py`, concurrency guide.
- **Regression:** independent-session seen/unseen/soft-delete/bulk/mixed races,
  caller rollback, deduplication reclaim, digest generation/claim/recovery and
  savepoint tests; narrow unit checks for driver results and unsupported PK shapes.

## Strict SQL summaries and deterministic ordering

- **Root cause:** MySQL ONLY_FULL_GROUP_BY did not recognize repeated IN-subqueries
  in SELECT/GROUP BY as equivalent expressions. Equal timestamps had unspecified
  inbox order, visible on MySQL's second-resolution legacy timestamp column.
- **Resolution:** project read state once in a derived table, group projected
  columns, and break default timestamp ties by descending notification ID.
- **Files:** `repository/queryset/notification.py`, `tests/repository/test_database_runtime.py`.
- **Regression:** existing summary/expiration/read-state API cases and
  `test_timestamp_ties_and_grouped_read_state_are_portable`. Preserve strict SQL
  mode and existing timestamp storage. The first full MySQL failures are retained
  as `mysql-strict-mode-initial.*`; the focused repair run passed all 59 cases.

## Guarded schema migration

- **Root cause:** type corrections need an explicit application upgrade path.
- **Resolution:** standalone Alembic reference revision, never automatically run
  at import/install. Preflight every affected column; preserve nullability/defaults/
  comments. Downgrade rejects identifier collisions and nonzero microseconds before
  any DDL. MySQL DDL implicitly commits, so application use requires maintenance,
  a backup and attachment to the host revision chain. Customized schemas require
  a tailored application migration. SQLite/PostgreSQL paths are no-ops.
- **Files:** `migrations/README.md`, `migrations/versions/20261103_mysql_identity_precision.py`.
- **Regression:** real empty legacy/new round trips; rollback refusal for precision
  loss and collation collisions, with no partial DDL. Tests use the disposable
  database, never an application database.
- **Approval history:** automatic review rejected an earlier broad schema proposal
  lacking migration safeguards. That proposal did not execute. The narrowed scope,
  migration/rollback plan and disposable-database tests were accepted; details are
  in `MYSQL_FIX_PLAN.md` and `mysql-migration-plan.json`.

## Python support and release metadata

- **Decision:** the maintainer explicitly dropped Python 3.9/3.10. Support now starts
  at 3.11, with explicit classifiers/validation through 3.15; package range is
  >=3.11,<4.0. Historical exploration is not a support commitment.
- **Evidence:** 3.10 initially passed 719 cases with two MySQL-only skips. 3.9 passed
  718, with one test-only use of the Python-3.10 `anext` built-in; use the equivalent
  async-generator protocol and preserve its exception assertion. Additional old
  interpreter coverage runs were canceled following the maintainer's decision.
- **Files:** `pyproject.toml`, lockfile, README, changelog, contributing guide, tox,
  CI; `tests/api/dependencies/test_dependencies.py`.
- **Consistency:** intended first release stays 1.0.0, with matching Commitizen and
  semantic-release metadata. Stable classifier describes the intended public
  release; it does not authorize publication. README is product-facing.

## CI, distribution and reproducible evidence

- Locked Poetry installation; Python 3.11–3.15 matrix; explicit minimum framework
  job; unchanged 100% gate; all five static checks and configured Bandit; real
  PostgreSQL/MySQL service jobs; build and isolated clean-wheel smoke checks.
- Optional database development group keeps server drivers/RSA auth tooling out
  of mandatory runtime dependencies. Release workflow is manually dispatched
  validation only, with read-only permissions and no publishing steps.
- Source/wheel/sdist inspection excludes tests from distributions, includes the
  reference migration in sdist, checks Python metadata and compares every packaged
  production Python file with the checkout. Clean-wheel tests run with `-I` outside
  the checkout, verify all public exports/OpenAPI/auth and persist a notification.
- Full stdout/stderr, actual commands/versions/exit codes/timestamps, test XML,
  coverage JSON, checksums and a source archive are stored here. Archive construction
  explicitly includes ignored validation logs; git-ignore is not used to omit them.
- Hosted GitHub Actions remains NOT TESTED until an actual hosted run occurs.
