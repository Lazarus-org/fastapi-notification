"""Run server validation without storing credentials or putting them in argv."""
import asyncio
from contextlib import redirect_stderr, redirect_stdout
from getpass import getpass
import json
from pathlib import Path
import sys
import uuid

import asyncpg
import pytest
from sqlalchemy.engine import URL

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
password = getpass('PostgreSQL password: ')
reuse = '--reuse' in sys.argv
database = json.loads((root/'validation/postgresql-server.json').read_text())['database'] if reuse else 'fastapi_notification_validation_' + uuid.uuid4().hex[:12]
assert database.startswith('fastapi_notification_validation_') and all(c.isalnum() or c == '_' for c in database)

async def provision():
    connection = await asyncpg.connect(host='127.0.0.1', port=5432, user='postgres', password=password, database='postgres', timeout=10)
    try:
        version = await connection.fetchval('SELECT version()')
        if not reuse:
            await connection.execute(f'CREATE DATABASE "{database}" TEMPLATE template0 ENCODING \'UTF8\'')
        isolation = await connection.fetchval('SHOW default_transaction_isolation')
        return version, isolation
    finally:
        await connection.close()

version, isolation = asyncio.run(provision())
(root/'validation/postgresql-server.json').write_text(json.dumps({'database': database, 'version': version, 'host': '127.0.0.1', 'port': 5432, 'driver': 'asyncpg', 'default_transaction_isolation': isolation}, indent=2), encoding='utf-8')
print('Using isolated PostgreSQL validation database; starting full suite.', flush=True)
url = URL.create('postgresql+asyncpg', username='postgres', password=password, host='127.0.0.1', port=5432, database=database).render_as_string(hide_password=False)

class DatabaseConfiguration:
    def pytest_configure(self, config):
        config.option.database_url = url

class RedactingLog:
    def __init__(self, stream):
        self.stream = stream
    def write(self, value):
        return self.stream.write(value.replace(password, '<redacted>').replace(url, '<redacted database URL>'))
    def flush(self):
        self.stream.flush()
    def isatty(self):
        return False

with (root/'validation/postgresql.log').open('w', encoding='utf-8') as stream:
    log = RedactingLog(stream)
    with redirect_stdout(log), redirect_stderr(log):
        result = pytest.main(['--no-cov', '-q', '--junitxml=validation/postgresql.xml'], plugins=[DatabaseConfiguration()])
(root/'validation/postgresql-result.json').write_text(json.dumps({'exit_code': int(result), 'database': database}, indent=2), encoding='utf-8')
print('PostgreSQL test execution finished. Exit code:', int(result), flush=True)
