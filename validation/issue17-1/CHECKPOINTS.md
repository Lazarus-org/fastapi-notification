# Issue 17.1 checkpoints

Previous Issue 17 evidence is retained in validation/; this campaign writes new evidence under issue17-1/.

## 1. Baseline audit

Read REPORT.md, CHANGES.md, FILES_CHANGED.txt, complete pyproject.toml, previous diagnostics and runtime evidence. Saved baseline git status, full binary diff and tracked source checksums. Existing source/user changes retained.

## 2–4. Formatting, Pylint and mypy

| Command/check | Exit | Tool version |
|---|---:|---|
| quality-black | 0 | 24.10.0 |
| quality-isort | 0 | 5.13.2 |
| quality-docformatter | 0 | 1.7.8 |
| quality-pylint | 0 | 4.1.3 |
| quality-mypy | 0 | 1.20.2 |

Complete commands, separate stdout/stderr, UTC timestamps and interpreter/dependency versions are retained in quality-results.json and each check log. Pylint reports 10.00/10; mypy reports no issues in 163 source files. STATIC_ANALYSIS.md documents the narrowly scoped API/framework exceptions and typing boundaries. No configured threshold or checked production module was removed.

Changed groups: formatting/docstrings across package and tests; typed config/result/model/read interfaces; concrete pytest fixture annotations; queued unit-double boundaries; focused query/router/identity refactors. Exact source changes will be listed in FILES_CHANGED.txt.

## 5. Complete regression

707 passed, 0 failures/skips/errors in post-static-regression.xml. Includes all 706 prior tests and the new real SQLite compound-SELECT upsert regression. The defect was a .where() call on a CompoundSelect in SQLite conflict-safe bulk insertion; it now wraps the source before adding the SQLite parser disambiguation condition.

The 100% coverage configuration remains unchanged; a fresh final coverage execution is still required after remaining workstreams. No current campaign coverage PASS is inferred from previous evidence.

## Remaining work

Isolated MySQL 8.4 runtime, Python 3.9/3.10 execution, metadata/CI reconciliation, complete final matrix, distribution rebuild and final source archive. Remote hosted GitHub Actions remains NOT TESTED.

## 6. Real MySQL hardening checkpoint

An isolated official MySQL 8.4.13 Windows server is running from the ignored workspace data directory on loopback port 33306, using InnoDB/default REPEATABLE READ and aiomysql. Docker diagnostics, vendor ZIP hashes and server metadata are retained. Initial real runs reproduced identity collation collisions, lost microseconds and duplicate-state deadlocks. The narrowed fixes and reference migration are described in MYSQL_FIX_PLAN.md, migrations/README.md and regression tests. No application database is migrated.

mysql-narrow-runtime: 24 passed, including independent-session races and migration upgrade/downgrade/data-loss preflight rejection. mysql-fix-sqlite: 719 passed, 2 MySQL-only skips; 2,965 statements, zero missing (100%). mysql-fix-pylint: 10.00/10, exit 0. mysql-fix-mypy: no issues in 165 files, exit 0. Full MySQL execution is still pending; no full-database PASS is inferred from this checkpoint.

## 7. Older interpreter checkpoint (in progress)

Python 3.10.22 installed a compatible dependency set and completed 719 passed/2 expected MySQL-only skips. Python 3.9.25 installed a compatible set and completed 718 passed/2 skips/1 failed: the test harness used built-in anext, introduced in Python 3.10. Replaced that call with the equivalent async-generator __anext__ protocol, retaining its exception assertion. Production source did not require a minimum-version change. Coverage, build, clean-install and integration checks remain to be completed before final compatibility claims.

## Final completion

Maintainer-directed support range: Python >=3.11,<4.0, explicitly validated through 3.15. Each final Python 3.11–3.15 and minimum-framework run: 720 passed, 2 MySQL-only skips. PostgreSQL: 720 passed/2 skips. MySQL 8.4.13 InnoDB REPEATABLE READ with ONLY_FULL_GROUP_BY: 722 passed, no skips. All 706 original cases retained; 16 added. Fresh final coverage: 2,963 statements, zero missing (100%). Five quality gates, configured Bandit, dependency check, Poetry lock, tox config and wheel/sdist/clean-wheel checks pass. Full server schema snapshot verifies all affected types, precision, engines and constraints. Hosted GitHub Actions remains NOT TESTED.

The isolated MySQL process was shut down after verification; its ignored data directory is retained. The existing PostgreSQL service was not stopped. REPORT.md, CHANGES.md and ISSUES_AND_COMMITS.md contain the final assessment, individual fixes and local review drafts. No commits/tags/push/publishing.
