"""Capture complete Issue 17.1 command evidence without shell interpolation."""
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread

out = Path('validation/issue17-1')
name, *command = sys.argv[1:]
assert name and command
start = datetime.now(timezone.utc)
environment = os.environ.copy()
environment['PYLINTHOME'] = str(Path('.validation-cache/pylint').resolve())
environment['VIRTUALENV_APP_DATA'] = str(Path('.validation-cache/virtualenv').resolve())
environment['POETRY_CACHE_DIR'] = str(Path('.validation-cache/poetry').resolve())
process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', env=environment)
def capture(pipe, path):
    with path.open('w',encoding='utf-8') as target:
        for line in pipe:
            target.write(line)
            target.flush()
threads = [Thread(target=capture, args=(process.stdout, out/f'{name}.stdout.log')), Thread(target=capture, args=(process.stderr, out/f'{name}.stderr.log'))]
for thread in threads:
    thread.start()
returncode = process.wait()
for thread in threads:
    thread.join()
(out / f'{name}.log').write_text((out/f'{name}.stdout.log').read_text(encoding='utf-8') + '\n--- STDERR ---\n' + (out/f'{name}.stderr.log').read_text(encoding='utf-8'), encoding='utf-8')
record = {'command': command, 'exit_code': returncode, 'started_utc': start.isoformat(), 'ended_utc': datetime.now(timezone.utc).isoformat(), 'python': sys.version, 'versions': {package: importlib.metadata.version(package) for package in ['black','isort','docformatter','pylint','mypy','pytest','SQLAlchemy','fastapi','pydantic']}}
probe = subprocess.run([command[0], '-c', 'import sys, importlib.metadata as m, json; print(json.dumps({"python":sys.version,"packages":{d.metadata["Name"]:d.version for d in m.distributions()}}))'], capture_output=True, text=True, encoding='utf-8', errors='replace') if 'python' in Path(command[0]).name.lower() else None
if probe is not None and probe.returncode == 0:
    record['target_environment'] = json.loads(probe.stdout)
(out / f'{name}.result.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
p = out / 'quality-results.json'
data = json.loads(p.read_text()) if p.exists() else {}
data[name] = record
p.write_text(json.dumps(data, indent=2), encoding='utf-8')
print(name, 'exit', returncode)
raise SystemExit(returncode)
