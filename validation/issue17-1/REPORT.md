# Issue 17.1 final validation report

**READY FOR RELEASE VALIDATION**

Generated 2026-11-03T03:16:36.027610+00:00. Intended first public version:
**1.0.0**, unchanged. No commits, tags, pushes, publishing, remote issue creation
or hosted workflow runs were performed.

## Support decision

At the maintainer's explicit request, Python 3.9/3.10 are no longer supported.
The package requires **>=3.11,<4.0**, with explicit classifiers, CI/tox and actual
validation for **3.11–3.15**. Historical 3.9/3.10 exploration is retained and is
not a support claim. See [the decision record](python-compatibility-decision.json).
Package, Commitizen and semantic-release stay aligned on intended version 1.0.0.

## Final complete suites

| Target | Actual result | Assessment |
|---|---|---|
| Python 3.11 | 720 passed, 2 skipped | PASS |
| Python 3.12 | 720 passed, 2 skipped | PASS |
| Python 3.13 | 720 passed, 2 skipped | PASS |
| Python 3.14 | 720 passed, 2 skipped | PASS |
| Python 3.15 | 720 passed, 2 skipped | PASS |
| Minimum framework combination / Python 3.11 | 720 passed, 2 skipped | PASS |
| PostgreSQL 17.5 / asyncpg | 720 passed, 2 skipped | PASS |
| MySQL 8.4.13 / aiomysql | 722 passed, 0 skipped | PASS |

All **706 original cases are retained**, with **16 new cases**, totaling **722**.
The two skips outside MySQL are the explicitly MySQL-only rollback safety cases;
MySQL ran both. Collection retention and fixture routing are recorded in
[inventory-summary.json](inventory-summary.json) and [inventory.json](inventory.json).
Of 722 cases, **329 select the configured backend** (327 actually run there on
PostgreSQL after its two MySQL-only skips). Remaining cases include unit tests
and explicitly SQLite-backed fixtures; they are not represented as server queries.

The final minimum combination uses FastAPI 0.110.0, SQLAlchemy 2.0.30,
Pydantic 2.7.0 and pydantic-settings 2.3.0. Actual interpreter and dependency
versions for every run are in [compatibility-matrix.json](compatibility-matrix.json)
and per-command `*.result.json` files. Tests use independent real sessions for
state, deduplication and digest races and assert final committed state.

## Coverage and quality

Final SQLite/Python 3.15 coverage: **100% statement coverage**,
**2963 statements, zero missing**. The configured 100% threshold and
production source list were preserved. See [coverage.json](coverage.json) and
[the full coverage run](python315.log). This is a fresh execution after the final
production fix, not a reused Issue 17 percentage.

| Configured check | Exit code | Diagnostics |
|---|---:|---|
| black | 0 | [full output](quality-black.log) |
| isort | 0 | [full output](quality-isort.log) |
| docformatter | 0 | [full output](quality-docformatter.log) |
| pylint | 0 | [full output](quality-pylint.log) |
| mypy | 0 | [full output](quality-mypy.log) |

Pylint reports **10.00/10**; mypy reports no issues in 165 source files. Black,
isort and docformatter use the existing configuration/flags. The locked Pylint
4.1.3/Astroid 4.3.4 combination matches the executed gate. No global disabled
message, mypy check or production coverage exclusion was added. Narrow source
waivers and typed external-library boundaries are explained in
[STATIC_ANALYSIS.md](STATIC_ANALYSIS.md).

Configured [Bandit](bandit.log), [dependency consistency](dependency-check.log),
[Poetry lock validation](poetry-final-check.log), [tox enumeration](tox-final-config.log),
[tox configuration](tox-final-detail.log), and
[workflow/metadata parsing](configuration-check.json) pass. Poetry emits existing
legacy metadata deprecation warnings; they are retained, with exit code 0.
Python 3.14/3.15 runs retain upstream asyncio/pytest-asyncio deprecation warnings.
Coverage is statement coverage; no branch-coverage claim is made.

Final LF normalization is documented in [line-ending-normalization.json](line-ending-normalization.json): Python ASTs are identical. The five static checks, targeted real SQLite state/runtime regressions and distribution/clean-wheel checks were rerun afterward. Git diff whitespace validation is clean. The full interpreter/database results and statement coverage therefore apply to the same runtime semantics.

## Real MySQL 8.4

Docker client diagnostics showed an unavailable daemon. Validation instead used
the [official MySQL Windows ZIP](https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-8.4.13-winx64.zip),
isolated in the workspace on loopback port **33306**, not an application database.
[Download hashes/diagnostics](mysql-download.json) and
[server identity](mysql-server.json) record the actual binary and data directory.
Storage engine is **InnoDB**, isolation **REPEATABLE-READ**. Default
**ONLY_FULL_GROUP_BY remained enabled**. aiomysql 0.3.2
and PyMySQL 1.2.3 were exercised.

The full [MySQL XML](mysql.xml) and [log](mysql.log) cover schema/integrity,
notification CRUD/audiences, read/deletion/expiration, preferences/templates,
quiet hours/digests, duplicate-key/savepoint recovery and concurrent transitions.
[The fresh schema snapshot](mysql-schema-snapshot.json) independently verifies all
ten identifier column types/collations, UTC/local precision, InnoDB engines,
indexes, uniqueness, foreign keys and declared checks.

Initial failures were real and retained: identity collation collisions, lost
microseconds, lock-upgrade deadlocks, strict grouped-summary rejection and
timestamp ties. See [CHANGES.md](CHANGES.md) for each root cause, resolution,
affected files and regression. No isolation level or SQL mode was relaxed.

The guarded [reference migration](../../migrations/README.md) performs no automatic
application migration. Real tests exercised empty legacy/new upgrade/downgrade
and pre-DDL rollback refusal for precision loss and identifier collisions. Only
the verified disposable database was altered. MySQL DDL implicitly commits;
host applications must integrate and review their own migration chain.

Reproduce locally after provisioning an isolated MySQL 8.4 server:

```powershell
poetry sync --with dev,database --no-interaction
poetry run pytest fastapi_notification/tests --database-url 'mysql+aiomysql://notification:notification@127.0.0.1:33306/notification_issue17_1?charset=utf8mb4' --no-cov
```

`download_mysql.py` reproduces the vendor download/extraction. The campaign used
`mysqld --no-defaults --initialize-insecure` on a new workspace data directory,
then a hidden standalone process with `--port=33306 --bind-address=127.0.0.1
--mysqlx=0 --innodb-buffer-pool-size=64M --max-connections=50
--default-time-zone=+00:00`. The database was utf8mb4; the public fixture account
has privileges only on the disposable database. Fresh schema creation starts
from the server's normal case-insensitive default; only specified identity
columns override it. CI supplies equivalent PostgreSQL/MySQL service containers.

## PostgreSQL and transaction ownership

Actual server identity: `PostgreSQL 17.5 on x86_64-windows, compiled by msvc-19.43.34808, 64-bit`.
The newly created disposable database is recorded in `postgresql-server.json`;
the supplied password was read with a hidden prompt and omitted from files/argv.
[Final XML](postgresql.xml), [log](postgresql.log), and
[result/timestamps](postgresql-result.json) record the complete execution.
The first compound-SELECT default compilation failure is retained separately.
Package helpers flush but never commit/roll back the caller's outer transaction;
real rollback/savepoint and independent-session tests remain in all database runs.

## Distributions and clean installation

Final wheel and sdist are in [dist/](dist/), with
[SHA-256 checksums](distribution-checksums.json). [Inspection](distribution-inspection.json)
confirms version 1.0.0, Python metadata/classifiers, no bundled tests, the reference
migration in sdist, and an exact byte comparison of every packaged production
Python file with the final checkout. [Build/Twine output](distribution.log) is retained.

[Clean-wheel validation](wheel-validation.log) uses a separate runtime-only
environment and runs with `-I` from a temporary directory outside the checkout.
It verifies public exports, 14 OpenAPI paths, authentication, a custom actor model,
schema creation and notification persistence. The runtime dependency graph passes
and pytest/Black/Alembic/mypy/httpx are absent. Actual clean environment versions
and working-directory proof are in [wheel-environment.json](wheel-environment.json).

## CI, limitations and deliverables

CI covers Python 3.11–3.15, the minimum framework combination, all configured
quality gates, coverage, real PostgreSQL/MySQL services, distribution build and
clean-wheel smoke. Tox lists the corresponding interpreter/framework factors,
minimum, quality and opt-in database environments. Release workflow is manual
validation-only, with no publish/release steps.

**Hosted GitHub Actions: NOT TESTED.** Local execution was on Windows; hosted
Ubuntu and other operating systems are not claimed as executed. This assessment
means ready for the release-validation stage, not permission to publish.

[CHANGES.md](CHANGES.md) lists independent fixes; [FILES_CHANGED.txt](FILES_CHANGED.txt)
distinguishes entry-snapshot changes from the pre-existing working tree and lists
actual evidence files, including logs ignored by Git. [ISSUES_AND_COMMITS.md](ISSUES_AND_COMMITS.md)
contains local issue/commit drafts. The complete source ZIP and SHA-256 sidecar
are delivered alongside this report, with an explicit archive manifest. Environments,
downloaded interpreters/server binaries, Git internals, caches, generated HTML
and nested source ZIPs are excluded; original validation reports/logs remain.

## Environment cleanup

The verified workspace-owned MySQL server on port 33306 was shut down after the final schema inspection; see [mysql-cleanup.json](mysql-cleanup.json). Its ignored data directory is retained. Package/auth tables were dropped by the fixtures. The existing PostgreSQL service was left running, with the dedicated validation database retained for reproduction. No application database was migrated.
