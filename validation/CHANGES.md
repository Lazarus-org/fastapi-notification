# Changes suitable for GitHub issues and Conventional Commits

No commits were created. Suggested commit subjects, grouped by concern:

- `fix(filters): support direct construction with optional query defaults`
- `fix(identity): load async group relationships before descriptor access`
- `fix(relations): surface unsupported generic primary key configuration`
- `fix(audiences): merge overlapping snapshot recipients by identity`
- `fix(scheduling): preserve the current DST fold for quiet-hour endings`
- `fix(repository): clean all associations during permanent deletion without FK cascades`
- `test(postgresql): validate schema async races and savepoints against PostgreSQL 17.5`
- `build: refresh timezone data lock and exclude packaged tests`
- `test: recover regression fixtures and enforce complete statement coverage`
- `test: cover scheduling APIs DST transitions and digest worker races`
- `ci: extend Python validation through 3.15`
- `docs: record reproducible release validation and remaining blockers`

Follow-up GitHub issues:

1. Extend the PostgreSQL isolation/interleaving matrix with concurrent membership
   changes and provider crash/idempotency scenarios. The complete 706-case
   PostgreSQL 17.5 campaign already passes at default read-committed isolation.
2. Execute MySQL 8.4 runtime coverage, including repeatable-read current reads,
   savepoint duplicate recovery and worker claiming. No server was reachable.
3. Recover the remaining Black/isort/docformatter/pylint/mypy quality baseline.
   Full commands, exit codes and unabridged diagnostics are attached locally.
   Keep all configured checks and the 100% statement coverage gate unchanged.
4. Extend beyond the executed SQLite/PostgreSQL concurrency scenarios with
   membership changes during authorization and provider crash/retry behavior.
   Mixed seen/delete races and asynchronous expired-key reclamation now pass.
5. Complete MySQL schema, index and foreign-key validation. SQLite/PostgreSQL
   introspection and dedicated FK-enforcement tests now pass; shared SQLite
   fixtures otherwise retain their earlier FK configuration.
6. Validate Python 3.9/3.10 if keeping the unchanged advertised >=3.9 range,
   then execute the updated CI/tox jobs. Local 3.11–3.15 runs are not remote CI.

Release recommendation: NOT READY — BLOCKING ISSUES REMAIN.
