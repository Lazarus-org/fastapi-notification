# Reproducing Issue 17 validation

Run from the repository root. No commands publish or create commits.

## Development installation and complete suite

```powershell
poetry install --with dev
poetry check --lock
poetry run pytest --junitxml=validation/reproduced.xml
poetry run black --check fastapi_notification
poetry run isort --check-only fastapi_notification
poetry run pylint fastapi_notification --rcfile=pyproject.toml
poetry run mypy fastapi_notification
poetry run bandit -c pyproject.toml -r fastapi_notification
```

The source of dependencies is `pyproject.toml` and `poetry.lock`. The old
`packages/requirements-dev.txt` is for documentation dependencies only.
`dev-requirements.txt` is a generated equivalent of the declared dependency
ranges used for the isolated interpreter matrix; Poetry remains authoritative.
`aiosqlite` is a development dependency, and applications select their own DB
driver. `tzdata` is a runtime dependency, including on Windows.

## Real PostgreSQL and MySQL

These commands require a running Docker daemon. The credentials below are
only for the disposable services defined in this directory. The harness
creates and drops package/auth tables for every shared-engine or state-
concurrency test. Use a dedicated disposable database. Run one test process
per database, without pytest-xdist.

```powershell
docker compose -f validation/compose.yaml up -d --wait
poetry run pip install asyncpg aiomysql
poetry run pytest --database-url="postgresql+asyncpg://notification:notification@localhost:55432/notification_test" --junitxml=validation/postgresql.xml
poetry run pytest --database-url="mysql+aiomysql://notification:notification@localhost:53306/notification_test?charset=utf8mb4" --junitxml=validation/mysql.xml
```

Record server versions with `SELECT version()` / `SELECT VERSION()`. Image
versions in the compose file are proposed reproduction environments, not
executed compatibility evidence. PostgreSQL/MySQL test runs include the
independent-session tests in `repository/test_state_concurrency.py` (including
digest generation/claiming). SQLite-specific file-backed deduplication tests
continue to use SQLite; pure SQL compilation tests never count as server
integration evidence. `inventory.json` records fixture usage for honest grouping.

SQLite state concurrency uses WAL, independent sessions, and `BEGIN IMMEDIATE`
to serialize writer transactions. It validates idempotency and committed state
under SQLite's write serialization, but does not establish MVCC behavior,
InnoDB repeatable-read behavior, or PostgreSQL locking semantics.

## Python and framework matrix

CI and tox include Python 3.9 through 3.15; the task's executed matrix is
3.11 through 3.15. Run `tox` on a machine with the interpreters installed.
The Python support declaration remains unchanged (`>=3.9,<4.0`).

The minimum dependency run used FastAPI 0.110.0, SQLAlchemy 2.0.30,
Pydantic 2.7.0, and pydantic-settings 2.3.0. The other runs use the versions
recorded in the environment evidence. These are tested combinations, not a
claim that every intermediate combination has been exercised.

## Distribution checks

```powershell
poetry build
# Install Twine in a separate tools environment: its docutils requirement
# conflicts with this project's Sphinx 6 development pin.
python -m twine check dist/*
```

Install the wheel in a new environment with an application-selected DB driver.
`wheel_smoke.py` verifies all public exports, absence of bundled tests/development
packages, core schema creation without built-in auth tables, custom actor
persistence, OpenAPI and an HTTP authentication boundary. Execute it with
`python -I` from a temporary directory outside the checkout.

`run_quality.py` preserves check commands, exit codes and logs. Collection logs
are inventories, not PASS evidence. All release decisions must use the actual
execution XML, coverage JSON and tool results in `REPORT.md`.


## Local PostgreSQL with hidden credential entry

The follow-up run used a local PostgreSQL 17.5 server. From the repository root:

```powershell
poetry run python validation/run_postgresql.py
# Reuse only the dedicated validation database recorded by the first run:
poetry run python validation/run_postgresql.py --reuse
```

The runner prompts for the local postgres user's password without echoing it,
creates a unique database named fastapi_notification_validation_*, and passes
the connection URL to pytest in memory. No password is stored in a command,
configuration file or report. Server/version/database identification is saved
in postgresql-server.json. The database is retained for inspection; no existing
application database is used. The runner requires asyncpg (see the optional
requirements-databases.txt file).
