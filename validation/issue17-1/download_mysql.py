"""Download the official isolated MySQL test distribution without a system install."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

root = Path.cwd().resolve()
workspace = root / '.validation-mysql'
workspace.mkdir(exist_ok=True)
archive = workspace / 'mysql-8.4.13-winx64.zip'
urls = [
    'https://dev.mysql.com/get/Downloads/MySQL-8.4/mysql-8.4.13-winx64.zip',
    'https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-8.4.13-winx64.zip',
]
record = {'started_utc': datetime.now(timezone.utc).isoformat(), 'attempts': []}
for url in urls:
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'fastapi-notification-validation/1.0'})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open('wb') as destination:
            record['download_url'] = response.url
            while block := response.read(1024 * 1024):
                destination.write(block)
        break
    except Exception as exc:
        record['attempts'].append({'url': url, 'error': type(exc).__name__ + ': ' + str(exc)})
else:
    Path('validation/issue17-1/mysql-download.json').write_text(json.dumps(record, indent=2))
    raise RuntimeError('Official MySQL download unavailable; diagnostics saved.')
record['bytes'] = archive.stat().st_size
record['sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
record['md5'] = hashlib.md5(archive.read_bytes()).hexdigest()
# Validate extraction targets before writing any member.
with zipfile.ZipFile(archive) as handle:
    for member in handle.infolist():
        target = (workspace / member.filename).resolve()
        assert target.is_relative_to(workspace.resolve()), member.filename
    handle.extractall(workspace)
record['ended_utc'] = datetime.now(timezone.utc).isoformat()
Path('validation/issue17-1/mysql-download.json').write_text(json.dumps(record, indent=2))
print('Downloaded and extracted MySQL:', record['bytes'], 'bytes.')
