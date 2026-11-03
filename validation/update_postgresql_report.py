"""Refresh the validation report only after all follow-up executions finish."""
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET

out = Path('validation')
labels = ['311', '312', '313', '314', 'min']
for name in ['postgresql.xml', 'sqlite-followup.xml', *[f'followup-{label}.xml' for label in labels]]:
    suite = ET.parse(out / name).getroot()[0]
    assert suite.attrib['tests'] == '706', (name, suite.attrib)
    assert all(suite.attrib[key] == '0' for key in ['failures', 'errors', 'skipped']), (name, suite.attrib)
cov = json.loads((out / 'coverage-followup.json').read_text())
assert cov['totals']['percent_covered'] == 100
inventory = json.loads((out / 'inventory.json').read_text())
assert len(inventory) == 706
server = json.loads((out / 'postgresql-server.json').read_text())
rows = {name: [0, 0, 0, 0, 0] for name in ['Unit', 'API', 'SQLite integration', 'PostgreSQL integration', 'MySQL integration', 'Concurrency']}
pg_fixture_tests = 0
for test in ET.parse(out / 'sqlite-followup.xml').iter('testcase'):
    key = test.attrib['classname'] + '.' + test.attrib['name']
    fixtures = inventory[key]['fixtures']
    if 'engine' in fixtures or 'concurrency_store' in fixtures:
        pg_fixture_tests += 1
    if any(part in key for part in ['test_state_concurrency', 'test_notification_deduplication_concurrency']):
        group = 'Concurrency'
    elif '.tests.api.' in key:
        group = 'API'
    elif 'engine' in fixtures:
        group = 'SQLite integration'
    else:
        group = 'Unit'
    rows[group][0] += 1
    rows[group][1] += 1
assert sum(row[0] for row in rows.values()) == 706
rows['PostgreSQL integration'] = rows['SQLite integration'].copy()
(out / 'suite-counts.json').write_text(json.dumps({'rows': rows, 'distinct_test_identities': 706, 'full_campaigns': {'sqlite': 706, 'postgresql': 706}, 'postgresql_fixture_tests': pg_fixture_tests, 'note': 'PostgreSQL integration repeats the SQLite integration test identities; never sum repeated backend rows into the unique total.'}, indent=2))
(out / 'coverage-exclusions.json').write_text(json.dumps({name: data['excluded_lines'] for name, data in cov['files'].items() if data['excluded_lines']}, indent=2))

p = out / 'REPORT.md'
s = p.read_text(encoding='utf-8')
s = s.replace('The recovered suite passes 700 tests', 'The recovered suite passes 706 tests')
s = s.replace('Real PostgreSQL/MySQL validation and configured static-quality failures remain blocking.', 'The complete PostgreSQL 17.5 campaign also passes 706 tests. MySQL runtime validation and configured static-quality failures remain blocking.')
start = s.index('PostgreSQL: localhost:5432')
end = s.index('## B. Test results', start)
s = s[:start] + f"PostgreSQL 17.5 is now validated using asyncpg 0.32.0 against the isolated database `{server['database']}` on localhost:5432. Server default isolation is `{server['default_transaction_isolation']}`. User-supplied credentials were entered through a hidden prompt and were not saved. The database is retained for inspection. MySQL remains unreachable and Docker's daemon pipe remains unavailable. Details: [PostgreSQL follow-up](POSTGRESQL.md).\n\n" + s[end:]
start = s.index('## B. Test results')
end = s.index('## C. Coverage', start)
section = ['## B. Test results', '', 'Both complete campaigns executed **706 tests: 706 passed, 0 failed, 0 skipped, 0 errors**. The initial PostgreSQL run also passed the preceding 700-test suite before six new regression cases were added.', '', 'The table groups the SQLite coverage campaign by test location/fixtures and shows the repeated PostgreSQL integration group separately. PostgreSQL and SQLite integration rows execute the same test identities on different backends. **Do not add these backend rows: the distinct test total remains 706.** API and concurrency cases using shared fixtures also execute against PostgreSQL; they are not relabeled as extra unique tests.', '', '| Test suite | Collected | Passed | Failed | Skipped | Errors |', '|---|---:|---:|---:|---:|---:|']
for name, counts in rows.items():
    section.append('| ' + name + ' | ' + ' | '.join(map(str, counts)) + ' |')
section += ['| **Distinct identities (backend repetitions excluded)** | **706** | **706** | **0** | **0** | **0** |', '', f"PostgreSQL execution used actual server fixtures for **{pg_fixture_tests}** cases (including API and concurrency). Other cases are unit tests or intentionally SQLite-specific. The PostgreSQL integration row above is the non-API, non-concurrency shared-engine group; it is not the entire server-backed count. MySQL executed zero tests and remains BLOCKED. Collection, SQL compilation and unit fault injection do not count as server runtime evidence.", '', 'Evidence: `postgresql.xml` / `postgresql.log` and `sqlite-followup.xml` / `sqlite-followup.log`. Earlier baseline: 644 tests, 583 passed and 61 failed. Interpreter repetitions and targeted reruns are not added to the distinct total.', '', 'Executed scenarios include independent-session seen/unseen and soft-delete writes, mixed seen/delete requests, bulk writes, asynchronous scoped-key creation and expired-key reclamation, key release after permanent deletion, savepoint rollback, digest batch generation/claiming, stale lease recovery and retries. Schema tests introspect table/primary-key/unique/check/foreign-key/index definitions and execute a failing foreign-key insert inside a savepoint. SQLite explicitly enables FK enforcement in that dedicated test; shared fixtures otherwise retain their earlier behavior.', '', 'The concurrency group has 14 cases per campaign. Eleven use the portable state-concurrency fixture and therefore run on PostgreSQL; three existing deduplication tests intentionally retain SQLite-specific engines (two use synchronous adapters). SQLite WAL/BEGIN IMMEDIATE serialization is not used for PostgreSQL sessions. Actual committed state is asserted after competing transactions finish.', '']
s = s[:start] + '\n'.join(section) + '\n' + s[end:]
s = s.replace('2856/2856', f"{cov['totals']['covered_lines']}/{cov['totals']['num_statements']}")
s = s.replace('coverage-release.json', 'coverage-followup.json').replace('release-315.log', 'sqlite-followup.log').replace('release-315.xml', 'sqlite-followup.xml')
s = s.replace('htmlcov-release/', '../htmlcov/')
for label in labels:
    s = s.replace(f'release-{label}.xml', f'followup-{label}.xml')
s = s.replace('700 passed, 0 skipped/errors', '706 passed, 0 skipped/errors')
s = s.replace('| PostgreSQL runtime | BLOCKED | Authentication unavailable; no server version established |', '| PostgreSQL 17.5 / asyncpg 0.32.0 | PASS for executed suite | 706 passed; `postgresql.xml` (server fixture count explained above) |')
s = s.replace('build-release.log', 'build-postgresql-followup.log').replace('twine-release.log', 'twine-postgresql-followup.log').replace('wheel-smoke-final.log', 'wheel-postgresql-followup.log')
s = s.replace('`distribution-contents.json`: bundled tests/caches absent', '`distribution-contents.json`: bundled tests/caches absent (contents rechecked after follow-up rebuild)')
quality_mypy = (out / 'quality-mypy.log').read_text(errors='replace')
match = re.search(r'Found (\d+) errors in (\d+) files', quality_mypy)
if match:
    s = s.replace('212 errors in 38 files', f'{match[1]} errors in {match[2]} files')
needle = '| Stale tests and fixture setup errors |'
position = s.index(needle)
s = s[:position] + '| Permanent deletion relied on DB cascades with SQLite foreign keys disabled | repository/queryset/notification.py: shared explicit association cleanup in single deletion, bulk deletion and retention purge; no commit added | Single/bulk association cleanup, ID/key reuse, mixed seen/delete and rollback tests PASS on SQLite and PostgreSQL |\n' + s[position:]
s = s.replace('Complete 700-test suite PASS', 'Complete 706-test suite PASS')
s = s.replace('snapshot recipient merge, DST quiet-hour end handling.', 'snapshot recipient merge, DST quiet-hour end handling, and explicit permanent-deletion association cleanup.')
start = s.index('## G. Remaining issues and limitations')
end = s.index('## H. Release recommendation', start)
s = s[:start] + '''## G. Remaining issues and limitations

1. MySQL runtime validation remains BLOCKED on server availability. InnoDB repeatable-read, current reads, duplicate-key/savepoint recovery and real MySQL races remain unvalidated.
2. Configured Black, isort, pylint, mypy and docformatter checks still fail. Their requirements were not reduced. Full final diagnostics are retained.
3. PostgreSQL runtime is now executed, including schema/constraints, async CRUD, API, independent-session state/dedup/digest operations, savepoints, expiration/timezone behavior and snapshot audiences. This does not exhaust all isolation levels or interleavings: concurrent membership changes, provider crash/idempotency behavior and broader worker failure injection remain follow-up work.
4. Digest delivery remains at-least-once. Provider idempotency is still required for duplicate delivery protection.
5. SQLite and PostgreSQL schema/index introspection and negative FK enforcement now pass. SQLite shared fixtures do not globally enable foreign_keys; the dedicated schema/FK test enables enforcement explicitly. MySQL schema validation remains outstanding.
6. Branch coverage was not configured or measured. 100% statements is not proof of every race/branch combination.
7. Python 3.9/3.10 remain advertised but unexecuted; updated remote CI/tox jobs have not been run. No support range was silently removed.
8. No schema change was required and no migration environment exists, so no migration upgrade/rollback campaign was introduced.

PostgreSQL credentials are no longer a blocker. The dedicated database is identified in postgresql-server.json and retained for inspection. No existing application database was used.

''' + s[end:]
s = s.replace('Server runtime validation and configured quality failures remain release blockers.', 'MySQL runtime validation and configured quality failures remain release blockers.')
s = s.replace('| Recover existing tests and fix regressions | Complete; final suite has 700 passing tests |', '| Recover existing tests and fix regressions | Complete; final suite has 706 passing tests |')
s = s.replace('| PostgreSQL integration | BLOCKED on credentials |', '| PostgreSQL integration | Executed: PostgreSQL 17.5, full 706-test campaign PASS |')
s = s.replace('| Concurrency | Executed SQLite scenarios; full server matrix remains |', '| Concurrency | Executed SQLite/PostgreSQL state, deduplication and digest scenarios; broader membership/provider matrix remains |')
s += '\nPostgreSQL follow-up details and the newly fixed association-cleanup defect: [POSTGRESQL.md](POSTGRESQL.md).\n'
p.write_text(s, encoding='utf-8')

supplement = f'''# PostgreSQL runtime follow-up

Server: {server['version']}. Driver: asyncpg 0.32.0; Python 3.15.1; SQLAlchemy 2.1.6.
Server default isolation: {server['default_transaction_isolation']}.
Dedicated database: {server['database']} (retained for inspection).

The first real PostgreSQL run passed all 700 existing tests. The expanded final
campaign passes all 706 cases, with no skips, failures or errors. {pg_fixture_tests}
cases use PostgreSQL engine/session fixtures; other cases are unit tests or
intentionally SQLite-specific. SQLite and the Python/minimum-framework matrix
also pass all 706 cases. Full XML/log files are retained.

The follow-up adds a schema/constraint/index parity and FK-enforcement test,
single/bulk permanent-deletion association cleanup checks, concurrent mixed
seen/delete requests, independent asynchronous scoped-key creation and expired
key reclamation, permanent deletion/key release, and partial-work savepoint
rollback. Existing tests execute native upserts/insert-select conflict handling,
notification APIs, preferences, localization, snapshot audiences, digest
claiming/recovery, expiration and UTC round-tripping on the actual server.

The new SQLite race uncovered a real defect: permanent deletion relied on FK
cascades while SQLite FK enforcement is optional. Orphan recipient/state rows
could collide with or attach to a later notification reusing the old integer
ID. The fix explicitly deletes recipient, group, seen, soft-delete and dedup
associations in single deletion, bulk deletion and retention purge. It leaves
commit/rollback ownership with the caller. No schema migration is required.

Evidence: postgresql.xml, postgresql.log, postgresql-server.json,
sqlite-followup.xml, coverage-followup.json, followup-*.xml,
portable-runtime-fixed.log. The original 700-case PG campaign is preserved as
postgresql-initial.xml/log. Build, Twine and clean-wheel smoke checks were
repeated after the implementation fix.

Credentials were entered through getpass without echoing or saving them.
run_postgresql.py passes the URL to pytest in memory and redacts log output.
The source archive contains no saved database password.

MySQL remains BLOCKED and static-quality failures remain. Recommendation:
NOT READY — BLOCKING ISSUES REMAIN.
'''
(out / 'POSTGRESQL.md').write_text(supplement, encoding='utf-8')
print('Reports refreshed:', pg_fixture_tests, 'actual PostgreSQL fixture cases; 706 distinct tests.')
