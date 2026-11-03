# Initial environment and repository baseline

Date: 2026-11-02 (Asia/Tehran). Initial `git status --short` showed only a
pre-existing modification to `CHANGELOG.md`. That content was retained.
No commits, tags, pushes or publications were made.

- Windows 10 build 19045, AMD64.
- Default Python: CPython 3.15.1. Existing venv: CPython 3.13.14.
- Existing venv dependencies: FastAPI 0.162.0, SQLAlchemy 2.1.6,
  Pydantic 2.14.2, pydantic-settings 2.16.2, pytest 8.4.2,
  pytest-asyncio 0.24.0, pytest-cov 5.0.0, aiosqlite 0.20.0,
  greenlet 3.5.6. Full package inventory: `environment-313.json`.
- The Windows Store interpreter was inaccessible within the sandbox; it ran
  successfully using approved execution outside the sandbox.
- `aiosqlite` was already installed and correctly declared in Poetry dev
  dependencies. Missing SQLite driver setup was not the initial failure here.
- `tzdata` was declared in pyproject but absent from the stale lock and existing
  environment. Windows had no usable IANA zone data in that environment.
- First fresh `poetry install --with dev` failed because the lock was stale.
  `poetry lock` added tzdata and refreshed the content hash. Fresh installation
  then succeeded on Python 3.15; repaired installation succeeded on Python 3.13.
- Baseline executed 644 tests: 583 passed, 61 failed, 0 skipped, 0 errors.
  Evidence: `baseline.xml` and `baseline.log`. Initial coverage: 89.94%.
- Configured coverage scope is package statements, excluding tests/migrations
  and the existing report exclusions. Branch measurement is not enabled.
- Poetry/poetry-core is the build and dependency manager. No Alembic config or
  migration tree is present; schema lifecycle belongs to host applications.
- Package persistence uses SQLAlchemy async DAL/queryset modules and separate
  core `Base` and optional authentication `AuthBase` metadata. Host identities
  are mediated by configurable identity adapters, with opaque string storage.
  FastAPI router factories expose notifications, activities and user settings.
- CI and tox initially named Python 3.9 through 3.13. Quality tools are Black,
  isort, pylint, mypy, Bandit and docformatter/pre-commit; Ruff is not configured.

The initial full run had imported the baseline modules before fixes were made;
subsequent recovery/final runs are separately identified. Interrupted or
superseded exploratory runs never count toward final PASS totals.
