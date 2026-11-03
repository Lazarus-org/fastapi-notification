# Issue 17 — Complete test-suite recovery and runtime validation

Date: 2026-11-02 (Asia/Tehran). Package: fastapi-notification 1.0.0.

**NOT READY — BLOCKING ISSUES REMAIN**

The recovered suite passes 706 tests on each target interpreter from Python 3.11 through 3.15. The complete Python 3.15 coverage run passes the unchanged 100% statement gate. The complete PostgreSQL 17.5 campaign also passes 706 tests. MySQL runtime validation and configured static-quality failures remain blocking. No release, commit, tag or push was performed.

## A. Environment

Windows 10 build 19045, AMD64. Poetry 2.5.1 / poetry-core 2.5.0. See [the initial report](BASELINE.md) and `env-*.json` for exact inventories.

| Environment | Python | SQLite | FastAPI | SQLAlchemy | Pydantic |
|---|---|---|---|---|---|
| 311 | 3.11.18 | 3.53.1 | 0.162.0 | 2.1.6 | 2.14.2 |
| 312 | 3.12.16 | 3.53.1 | 0.162.0 | 2.1.6 | 2.14.2 |
| 313 | 3.13.14 | 3.50.4 | 0.162.0 | 2.1.6 | 2.14.2 |
| 314 | 3.14.10 | 3.53.1 | 0.162.0 | 2.1.6 | 2.14.2 |
| 315 | 3.15.1 | 3.53.4 | 0.162.0 | 2.1.6 | 2.14.2 |
| min | 3.11.18 | 3.53.1 | 0.110.0 | 2.0.30 | 2.7.0 |

Other tested dependencies: pytest 8.4.2, pytest-asyncio 0.24.0, pytest-cov 5.0.0, aiosqlite 0.20.0, tzdata 2026.6. Optional server drivers installed on Python 3.15: asyncpg 0.32.0, aiomysql 0.3.2 / PyMySQL 1.2.3. Driver installation alone is not server validation.

Development installation: `poetry install --with dev`. The first fresh attempt rejected a stale lock. Refreshing the lock added the already-declared tzdata dependency; fresh Python 3.15 installation and repaired Python 3.13 installation succeeded. `aiosqlite` was already correctly declared. Python 3.11/3.12/3.14 used isolated downloaded interpreters and equivalent declared dependency ranges. Installation logs and exact environment inventories are retained.

PostgreSQL 17.5 is now validated using asyncpg 0.32.0 against the isolated database `fastapi_notification_validation_b60f7139feeb` on localhost:5432. Server default isolation is `read committed`. User-supplied credentials were entered through a hidden prompt and were not saved. The database is retained for inspection. MySQL remains unreachable and Docker's daemon pipe remains unavailable. Details: [PostgreSQL follow-up](POSTGRESQL.md).

## B. Test results

Both complete campaigns executed **706 tests: 706 passed, 0 failed, 0 skipped, 0 errors**. The initial PostgreSQL run also passed the preceding 700-test suite before six new regression cases were added.

The table groups the SQLite coverage campaign by test location/fixtures and shows the repeated PostgreSQL integration group separately. PostgreSQL and SQLite integration rows execute the same test identities on different backends. **Do not add these backend rows: the distinct test total remains 706.** API and concurrency cases using shared fixtures also execute against PostgreSQL; they are not relabeled as extra unique tests.

| Test suite | Collected | Passed | Failed | Skipped | Errors |
|---|---:|---:|---:|---:|---:|
| Unit | 300 | 300 | 0 | 0 | 0 |
| API | 206 | 206 | 0 | 0 | 0 |
| SQLite integration | 186 | 186 | 0 | 0 | 0 |
| PostgreSQL integration | 186 | 186 | 0 | 0 | 0 |
| MySQL integration | 0 | 0 | 0 | 0 | 0 |
| Concurrency | 14 | 14 | 0 | 0 | 0 |
| **Distinct identities (backend repetitions excluded)** | **706** | **706** | **0** | **0** | **0** |

PostgreSQL execution used actual server fixtures for **317** cases (including API and concurrency). Other cases are unit tests or intentionally SQLite-specific. The PostgreSQL integration row above is the non-API, non-concurrency shared-engine group; it is not the entire server-backed count. MySQL executed zero tests and remains BLOCKED. Collection, SQL compilation and unit fault injection do not count as server runtime evidence.

Evidence: `postgresql.xml` / `postgresql.log` and `sqlite-followup.xml` / `sqlite-followup.log`. Earlier baseline: 644 tests, 583 passed and 61 failed. Interpreter repetitions and targeted reruns are not added to the distinct total.

Executed scenarios include independent-session seen/unseen and soft-delete writes, mixed seen/delete requests, bulk writes, asynchronous scoped-key creation and expired-key reclamation, key release after permanent deletion, savepoint rollback, digest batch generation/claiming, stale lease recovery and retries. Schema tests introspect table/primary-key/unique/check/foreign-key/index definitions and execute a failing foreign-key insert inside a savepoint. SQLite explicitly enables FK enforcement in that dedicated test; shared fixtures otherwise retain their earlier behavior.

The concurrency group has 14 cases per campaign. Eleven use the portable state-concurrency fixture and therefore run on PostgreSQL; three existing deduplication tests intentionally retain SQLite-specific engines (two use synchronous adapters). SQLite WAL/BEGIN IMMEDIATE serialization is not used for PostgreSQL sessions. Actual committed state is asserted after competing transactions finish.

## C. Coverage

- Statement coverage: **100.00%**, 2856/2856 statements.
- Requirement: **100%**, unchanged and enforced by the complete pytest command.
- Uncovered statements: **0**. No modules below target within the configured scope.
- Branch measurement: not configured; branch coverage and remaining unexecuted branches are NOT MEASURED.
- Scope: fastapi_notification; tests and migrations omitted by existing configuration.
- Existing report exclusions account for 13 lines. No coverage source, omit, exclusion or threshold setting was weakened.
- Existing exclusions cover explicit no-cover pragmas, repr/debug/type-checking/overload and script-only branches. Exact affected locations are in `coverage-exclusions.json`; the full configuration remains in pyproject.toml.

Evidence: `coverage-followup.json`, `sqlite-followup.log`, `sqlite-followup.xml`. The HTML report is generated locally under `../htmlcov/` and excluded from the source ZIP as a generated artifact. Statement coverage does not establish backend compatibility or exhaustive race interleavings.

## D. Compatibility

| Combination | Result | Executed evidence |
|---|---|---|
| Python 3.11.18 | PASS | 706 passed, 0 skipped/errors; `followup-311.xml` |
| Python 3.12.16 | PASS | 706 passed, 0 skipped/errors; `followup-312.xml` |
| Python 3.13.14 | PASS | 706 passed, 0 skipped/errors; `followup-313.xml` |
| Python 3.14.10 | PASS | 706 passed, 0 skipped/errors; `followup-314.xml` |
| Python 3.15.1 | PASS | 706 passed, 0 skipped/errors; `sqlite-followup.xml` |
| Minimum frameworks on Python 3.11 | PASS | 706 passed, 0 skipped/errors; `followup-min.xml` |
| SQLite 3.50.4 / 3.53.1 / 3.53.4 | PASS for executed suite | Exact versions per interpreter above |
| PostgreSQL 17.5 / asyncpg 0.32.0 | PASS for executed suite | 706 passed; `postgresql.xml` (server fixture count explained above) |
| MySQL runtime | BLOCKED | No reachable server; no version established |
| Python 3.9 / 3.10 | NOT TESTED | Advertised range retained; outside requested executed matrix |
| Updated remote CI / complete tox matrix | NOT TESTED | Configuration updated locally; no push or remote run |

The minimum run uses FastAPI 0.110.0, SQLAlchemy 2.0.30, Pydantic 2.7.0 and pydantic-settings 2.3.0. The other runs use FastAPI 0.162.0, SQLAlchemy 2.1.6, Pydantic 2.14.2 and pydantic-settings 2.16.2. This validates these combinations, not all combinations allowed by the dependency ranges. The declared Python range remains >=3.9,<4.0.

Timezone tests execute real tzdata-backed UTC, Asia/Tehran, America/New_York and Europe/Berlin calculations. Spring gaps move scheduled time forward by the gap using the pre-transition offset; ambiguous schedules use fold=0 once per local date. Quiet-hour endings use the current fold to avoid returning a past instant during the repeated hour. The policy and recurrence behavior are documented in docs/scheduling.rst. Aware UTC persistence and rejection of naive timestamps are exercised.

### Configured quality and distribution checks

| Check | Result | Evidence |
|---|---|---|
| black | FAIL (exit 1) | `quality-black.log` |
| isort | FAIL (exit 1) | `quality-isort.log` |
| pylint | FAIL (exit 30) | `quality-pylint.log` |
| mypy | FAIL (exit 1) | `quality-mypy.log` |
| bandit | PASS (exit 0) | `quality-bandit.log` |
| docformatter | FAIL (exit 3) | `quality-docformatter.log` |
| dependencies | PASS (exit 0) | `quality-dependencies.log` |
| poetry | PASS (exit 0) | `quality-poetry.log` |
| Wheel + sdist build | PASS | `build-postgresql-followup.log` |
| Twine metadata | PASS | `twine-postgresql-followup.log` |
| Distribution contents | PASS | `distribution-contents.json`: bundled tests/caches absent (contents rechecked after follow-up rebuild) |
| Clean wheel runtime | PASS | `wheel-postgresql-followup.log` |
| Clean runtime dependency compatibility | PASS | `wheel-pip-check.log` |

Remaining quality baseline: Black reports 29 files needing formatting; isort reports unsorted imports; pylint rates 9.02/10 with configured violations; mypy reports 212 errors in 38 files; docformatter reports violations. Full diagnostics are retained without disabling checks. Ruff is not configured. Bandit reports zero issues; this is a static scan, not a dependency vulnerability audit. Poetry metadata deprecation warnings remain. Python 3.14/3.15 runs also emit pytest-asyncio deprecation warnings; these did not skip or fail tests.

Packaging tools were isolated from project dependencies after Twine/readme-renderer conflicted with the development Sphinx/docutils pin. Final project pip check passes. The clean wheel environment contains runtime dependencies and an application-selected SQLite driver, without pytest, Black, mypy, HTTPX or Alembic. Smoke testing runs with python -I from a temporary directory outside the source checkout and checks 35 public exports, 14 OpenAPI paths, an HTTP 401 authentication boundary, core metadata creation, host-owned actor persistence and notification round-trip.

## E. Bugs fixed

| Root cause | Files / fix | Regression and result |
|---|---|---|
| Query objects became direct constructor values | api/filters/notification_filter.py: Annotated Query metadata with plain None defaults | Direct/partial construction plus full API filtering tests PASS |
| hasattr triggered synchronous lazy database I/O | identity.py: await relationship loading before descriptor access | Unloaded group relationship and API activity tests PASS |
| Configuration TypeError swallowed for generic relations | models/content_type.py: retain invalid-ID recovery while propagating unsupported model/key TypeError | Composite/unmapped/unsupported-type tests PASS |
| Snapshot and direct audiences inserted duplicate recipient associations | repository/manager/notification.py: merge snapshot recipients by normalized identity ID | Real database overlapping group/direct audience and membership-removal test PASS |
| Quiet-hour end in repeated DST hour could be in the past | repository/manager/scheduling.py: preserve local fold at window end | New York second-fold test and schedule transition tests PASS |
| Lockfile omitted declared timezone data and rejected fresh installation | poetry.lock: add tzdata and update dependency hash | Fresh Poetry installation and timezone suite PASS |
| Wheel bundled 72 test modules | pyproject.toml: exclude test tree from distributions | Rebuilt wheel/sdist inspection and clean installation PASS |
| Permanent deletion relied on DB cascades with SQLite foreign keys disabled | repository/queryset/notification.py: shared explicit association cleanup in single deletion, bulk deletion and retention purge; no commit added | Single/bulk association cleanup, ID/key reuse, mixed seen/delete and rollback tests PASS on SQLite and PostgreSQL |
| Stale tests and fixture setup errors | tests: explicit commits before cross-session API reads; correct identity representation and fixture injection; current taxonomy/template fields; real queryset SQL; refresh rollback-expired state; deterministic ordering timestamps | Complete 706-test suite PASS |

No public API redesign or database schema change was required. Unsupported composite relation errors now follow the already-documented contract. No migrations were added; the repository has no Alembic environment or migration tree to upgrade/downgrade. Caller-owned DAL transactions and optional host identity integration remain intact.

## F. Files changed

The exhaustive categorized manifest is [FILES_CHANGED.txt](FILES_CHANGED.txt). It lists modified tracked files, added tests, documentation, CI and generated evidence separately. No tracked files were deleted. CHANGELOG.md contained user changes before this task; those were preserved and the validation entry was added.

Implementation: filter defaults, async identity loading, generic relation error handling, snapshot recipient merge, DST quiet-hour end handling, and explicit permanent-deletion association cleanup. Tests: recovered API/model/repository/settings fixtures, portable database fixture option, expanded timezone/API/concurrency/error contracts. Packaging: lock refresh and distribution exclusion. CI: Python 3.14/3.15 in CI/tox. Documentation: README, changelog, scheduling policy and validation evidence. Migration changes: none.

## G. Remaining issues and limitations

1. MySQL runtime validation remains BLOCKED on server availability. InnoDB repeatable-read, current reads, duplicate-key/savepoint recovery and real MySQL races remain unvalidated.
2. Configured Black, isort, pylint, mypy and docformatter checks still fail. Their requirements were not reduced. Full final diagnostics are retained.
3. PostgreSQL runtime is now executed, including schema/constraints, async CRUD, API, independent-session state/dedup/digest operations, savepoints, expiration/timezone behavior and snapshot audiences. This does not exhaust all isolation levels or interleavings: concurrent membership changes, provider crash/idempotency behavior and broader worker failure injection remain follow-up work.
4. Digest delivery remains at-least-once. Provider idempotency is still required for duplicate delivery protection.
5. SQLite and PostgreSQL schema/index introspection and negative FK enforcement now pass. SQLite shared fixtures do not globally enable foreign_keys; the dedicated schema/FK test enables enforcement explicitly. MySQL schema validation remains outstanding.
6. Branch coverage was not configured or measured. 100% statements is not proof of every race/branch combination.
7. Python 3.9/3.10 remain advertised but unexecuted; updated remote CI/tox jobs have not been run. No support range was silently removed.
8. No schema change was required and no migration environment exists, so no migration upgrade/rollback campaign was introduced.

PostgreSQL credentials are no longer a blocker. The dedicated database is identified in postgresql-server.json and retained for inspection. No existing application database was used.

## H. Release recommendation

**NOT READY — BLOCKING ISSUES REMAIN**

The recovered tests, interpreter matrix, 100% statement coverage and clean distributions establish a reproducible local baseline. MySQL runtime validation and configured quality failures remain release blockers. Local passing tests do not authorize publication.

## I. Final source archive

Archive: `fastapi-notification-issue17-source.zip`, with SHA-256 in `SOURCE_ARCHIVE.sha256`. It contains tracked source, new tests, docs, lock/configuration files and validation evidence. Git internals, virtual environments, downloaded interpreters, caches, HTML coverage output and build artifacts are excluded. Tests remain in this source ZIP even though they are excluded from installable distributions.

Separate issue/Conventional Commit list: [CHANGES.md](CHANGES.md). No commits were created.

### Checkpoint outcomes

| Checkpoint | Outcome |
|---|---|
| Repository/dependency audit | Complete; initial state and 644-test baseline recorded |
| Restore development environment | Complete; fresh and repaired installations succeeded |
| Recover existing tests and fix regressions | Complete; final suite has 706 passing tests |
| SQLite integration | Executed; limitations on FK enforcement recorded |
| PostgreSQL integration | Executed: PostgreSQL 17.5, full 706-test campaign PASS |
| MySQL integration | BLOCKED on server availability |
| Concurrency | Executed SQLite/PostgreSQL state, deduplication and digest scenarios; broader membership/provider matrix remains |
| API/OpenAPI | Executed including scheduling settings and isolation |
| Python compatibility | 3.11–3.15 and minimum frameworks executed |
| Coverage/quality | 100% statements PASS; static-quality failures remain |
| Distribution | Build, metadata, contents and clean wheel runtime PASS |
| Final report/archive | Supplied with reproducible commands and evidence |

PostgreSQL follow-up details and the newly fixed association-cleanup defect: [POSTGRESQL.md](POSTGRESQL.md).
