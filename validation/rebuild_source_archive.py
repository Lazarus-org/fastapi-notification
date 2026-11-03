"""Create a source archive and verify that supplied credentials are absent."""
from getpass import getpass
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import quote
import zipfile

root = Path.cwd()
out = root / 'validation'
password = getpass('PostgreSQL password for artifact leak check: ')
assert password
needles = {password.encode(), quote(password, safe='').encode()}

def allowed(name):
    path = root / name
    return bool(name) and path.is_file() and not (
        name.startswith('validation/htmlcov')
        or name.startswith('validation/.coverage')
        or name.startswith('dist/')
        or path.suffix == '.zip'
        or any(part in {'.git', '__pycache__', '.pytest_cache', '.mypy_cache'} for part in Path(name).parts)
    )

tracked = set(subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0'))
files = set(subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z']).decode().split('\0'))
files = {name for name in files if allowed(name)}
leaks = [name for name in sorted(files) if any(needle in (root / name).read_bytes() for needle in needles)]
assert not leaks, 'Credential material found in: ' + ', '.join(leaks)
(out / 'credential-scan.json').write_text(json.dumps({'credential_matches': 0, 'checked_files': len(files), 'scope': 'Tracked source and non-cache validation artifacts, including logs and XML; checked raw and URL-encoded credential bytes.'}, indent=2))
(out / 'git-status.txt').write_text(subprocess.check_output(['git', 'status', '--short', '--untracked-files=all']).decode(), encoding='utf-8')
files.add('validation/credential-scan.json')
files.add('validation/FILES_CHANGED.txt')
changed = subprocess.check_output(['git', 'diff', '--name-only']).decode().splitlines()
added = sorted(files - tracked)
categories = {
    'Implementation fixes': [name for name in changed if name.startswith('fastapi_notification/') and '/tests/' not in name],
    'Tests and fixtures': [name for name in changed + added if name.startswith('fastapi_notification/tests/')],
    'Documentation (original user CHANGELOG changes retained)': [name for name in changed if name.endswith(('.md', '.rst'))],
    'CI/configuration/packaging': [name for name in changed if name.startswith('.github/') or name in {'.gitignore', 'pyproject.toml', 'poetry.lock', 'tox.ini'}],
    'Validation reports, scripts and execution evidence': [name for name in added if name.startswith('validation/')],
}
for name in ['validation/fastapi-notification-issue17-source.zip', 'validation/SOURCE_ARCHIVE.sha256']:
    if name not in categories['Validation reports, scripts and execution evidence']:
        categories['Validation reports, scripts and execution evidence'].append(name)
lines = ['Issue 17 updated source manifest', 'Modified tracked files and added deliverables; no tracked deletions.', 'Environments, caches, HTML coverage, git internals and distribution binaries excluded.', '']
for category, names in categories.items():
    lines.extend([category, *['  ' + name for name in sorted(set(names))], ''])
lines.append('Migration changes: none.')
(out / 'FILES_CHANGED.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
archive = out / 'fastapi-notification-issue17-source.zip'
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
    for name in sorted(files):
        # The archive checksum lives beside the archive, avoiding a recursive hash.
        if name != 'validation/SOURCE_ARCHIVE.sha256':
            handle.write(root / name, arcname='fastapi-notification/' + name)
with zipfile.ZipFile(archive) as handle:
    assert handle.testzip() is None
    for name in handle.namelist():
        assert not any(needle in handle.read(name) for needle in needles), name
    assert 'fastapi-notification/validation/POSTGRESQL.md' in handle.namelist()
    assert 'fastapi-notification/fastapi_notification/tests/repository/test_database_runtime.py' in handle.namelist()
checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
(out / 'SOURCE_ARCHIVE.sha256').write_text(checksum + '  ' + archive.name + '\n', encoding='utf-8')
print(json.dumps({'archive': str(archive), 'source_files': len(files), 'credential_matches': 0, 'sha256': checksum}, indent=2))
