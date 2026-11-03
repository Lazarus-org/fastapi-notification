# Prepared issue and commit drafts

These are local drafts. No issues or commits were created remotely.

| Issue title / suggested commit | Scope and acceptance evidence |
|---|---|
| `style: format package and normalize imports` | Configured Black/isort/docformatter pass; meaning-preserving formatting. |
| `fix(types): resolve package-wide mypy errors` | Precise read overloads/projections/config/result boundaries and typed tests; mypy clean, existing tests retained. |
| `fix(quality): resolve pylint and documentation violations` | Responsibility/cache/control-flow fixes, documented narrow waivers, compatible Pylint/Astroid lock; score 10.00/10. |
| `fix(state): support compound SELECT bulk insert defaults` | Wrap compound sources for native SQLite/PostgreSQL insertion; actual union-source regression and no lost defaults. |
| `fix(mysql): preserve opaque identity isolation and temporal precision` | Exact identity/key comparison, six-digit UTC/local precision, guarded reference migration and rollback data-loss checks. |
| `fix(mysql): serialize duplicate state writes at repeatable read` | Native no-op duplicate update, correct inserted counts, current reads and independent-session race/rollback tests. |
| `fix(query): support strict grouped summaries and stable inbox ordering` | Derived read-state projection, timestamp/ID order, real MySQL ONLY_FULL_GROUP_BY regressions. |
| `test(mysql): add MySQL 8.4 runtime validation` | Portable isolated server, actual schema/constraints/CRUD/concurrency/migration execution and retained diagnostics. |
| `build: require Python 3.11 and declare Python 3.15 support` | Maintainer support decision; metadata/lock/classifier/README/tox/CI alignment and complete supported matrix. |
| `ci: enforce the full validation and distribution matrix` | Locked dev tooling, static gates, minimum frameworks, PostgreSQL/MySQL services, clean wheel checks; hosted execution pending. |
| `docs: align first-release metadata and publish validation evidence` | Intended 1.0.0 remains unchanged; product README, migration guidance, detailed report, logs, hashes and complete source archive. |

For each independent issue, use the corresponding root-cause, affected-files,
resolution and regression section of `CHANGES.md` as the issue body. The full
file manifest and validation report provide review context. Keep schema migration
and concurrency changes separately reviewable even if applied together locally.

Follow-up before publishing: run the committed CI workflows on hosted GitHub
Actions and review application-specific migration integration. No release is
authorized by these local validation results.
