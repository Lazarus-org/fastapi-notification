"""Assemble release assessment only from completed validation evidence."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
out = root / "validation/issue17-1"
read = lambda name: json.loads((out / name).read_text(encoding="utf-8"))
results = read("quality-results.json")
for path in out.glob("*.result.json"):
    results[path.name[:-len(".result.json")]] = json.loads(path.read_text(encoding="utf-8"))
(out / "quality-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
required = ["quality-black", "quality-isort", "quality-docformatter", "quality-pylint", "quality-mypy", "bandit", "dependency-check", "poetry-final-check", "tox-final-config", "tox-final-detail", "distribution", "wheel-validation", "test-inventory", "mysql-schema-inspection", "mysql", "format-regression"]
for name in required:
    assert results[name]["exit_code"] == 0, (name, results[name]["exit_code"])


def suite(name):
    entries = list(ET.parse(out / (name + ".xml")).iter("testsuite"))
    summary = {key: sum(int(entry.attrib.get(key, 0)) for entry in entries) for key in ("tests", "failures", "errors", "skipped")}
    summary["passed"] = summary["tests"] - summary["failures"] - summary["errors"] - summary["skipped"]
    assert summary["tests"] == 722 and summary["errors"] == summary["failures"] == 0, (name, summary)
    return summary


matrix = {name: suite("python" + name.replace(".", "")) for name in ("3.11", "3.12", "3.13", "3.14", "3.15")}
for version in matrix:
    key = "python" + version.replace(".", "")
    assert results[key]["exit_code"] == 0
    matrix[version]["environment"] = results[key]["target_environment"]
minimum = suite("pythonmin")
assert results["pythonmin"]["exit_code"] == 0
minimum["environment"] = results["pythonmin"]["target_environment"]
postgresql, mysql = suite("postgresql"), suite("mysql")
assert read("postgresql-result.json")["exit_code"] == 0
coverage = read("coverage.json")["totals"]
assert coverage["missing_lines"] == 0 and coverage["percent_covered"] == 100
inventory = read("inventory-summary.json")
assert inventory["previous_cases_retained"] == 706 and not inventory["missing_previous_cases"]
assert read("configuration-check.json")["status"] == "PASS"
assert read("mysql-schema-snapshot.json")["identifier_and_precision_assertions"] == "PASS"
compatibility = {"requires_python": ">=3.11,<4.0", "supported_validated_python": matrix, "minimum_frameworks": minimum, "sqlite_coverage": coverage, "postgresql": postgresql, "mysql": mysql, "database_fixture_inventory": inventory, "support_decision": read("python-compatibility-decision.json"), "hosted_github_actions": "NOT TESTED", "assessment": "READY FOR RELEASE VALIDATION"}
(out / "compatibility-matrix.json").write_text(json.dumps(compatibility, indent=2), encoding="utf-8")

baseline = read("baseline-source-checksums.json")
modified, deleted = [], []
for name, digest in baseline.items():
    path = root / name
    if not path.exists():
        deleted.append(name)
    elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        modified.append(name)
assert not deleted, deleted
status = subprocess.check_output(["git", "status", "--short", "--untracked-files=all"], cwd=root, text=True, encoding="utf-8")
(out / "final-git-status.log").write_text(status, encoding="utf-8")
new_evidence = sorted(path.relative_to(root).as_posix() for path in out.rglob("*") if path.is_file() and path.suffix not in {".zip", ".pyc", ".pyo"} and "__pycache__" not in path.parts and path.name != "SOURCE_ARCHIVE.sha256")
listing = "Issue 17.1 tracked-file changes versus entry checksums (pre-existing changes preserved):\n" + "\n".join(sorted(modified)) + "\n\nCurrent Git status (includes retained Issue 17 work and untracked source):\n" + status + "\nEvidence files, including logs ignored by Git:\n" + "\n".join(new_evidence) + "\n"
(out / "FILES_CHANGED.txt").write_text(listing, encoding="utf-8")

rows = "\n".join(f"| Python {version} | {item['passed']} passed, {item['skipped']} skipped | PASS |" for version, item in matrix.items())
tools = "\n".join(f"| {name.removeprefix('quality-')} | {results[name]['exit_code']} | [full output]({name}.log) |" for name in required if name.startswith("quality-"))
mysql_server, pg_server = read("mysql-server.json"), read("postgresql-server.json")
statement_count = coverage["num_statements"]
report = f"""# Issue 17.1 final validation report

**READY FOR RELEASE VALIDATION**

Generated {datetime.now(timezone.utc).isoformat()}. Intended first public version:
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
{rows}
| Minimum framework combination / Python 3.11 | {minimum['passed']} passed, {minimum['skipped']} skipped | PASS |
| PostgreSQL 17.5 / asyncpg | {postgresql['passed']} passed, {postgresql['skipped']} skipped | PASS |
| MySQL {mysql_server['version']} / aiomysql | {mysql['passed']} passed, {mysql['skipped']} skipped | PASS |

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
**{statement_count} statements, zero missing**. The configured 100% threshold and
production source list were preserved. See [coverage.json](coverage.json) and
[the full coverage run](python315.log). This is a fresh execution after the final
production fix, not a reused Issue 17 percentage.

| Configured check | Exit code | Diagnostics |
|---|---:|---|
{tools}

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
**ONLY_FULL_GROUP_BY remained enabled**. aiomysql {mysql_server['driver_versions']['aiomysql']}
and PyMySQL {mysql_server['driver_versions']['PyMySQL']} were exercised.

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

Actual server identity: `{pg_server['version']}`.
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
"""
cleanup = read("mysql-cleanup.json")
assert cleanup["stopped"]
report += "\n## Environment cleanup\n\nThe verified workspace-owned MySQL server on port 33306 was shut down after the final schema inspection; see [mysql-cleanup.json](mysql-cleanup.json). Its ignored data directory is retained. Package/auth tables were dropped by the fixtures. The existing PostgreSQL service was left running, with the dedicated validation database retained for reproduction. No application database was migrated.\n"
(out / "REPORT.md").write_text(report, encoding="utf-8")
print("Report generated from completed checks: READY FOR RELEASE VALIDATION")
