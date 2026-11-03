"""Run final wheel runtime checks isolated from the checkout's working directory."""

import json
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
interpreter = root / ".validation-wheel-final/Scripts/python.exe"
working_directory = Path(tempfile.mkdtemp(prefix="notification-wheel-issue17-1-"))
assert root not in working_directory.resolve().parents
print("Running wheel smoke outside checkout:", working_directory, flush=True)
result = subprocess.run([str(interpreter), "-I", str(root / "scripts/wheel_smoke.py")], cwd=working_directory, check=False)
assert result.returncode == 0, result.returncode
probe = subprocess.run([str(interpreter), "-I", "-c", "import json,sys,sqlite3,importlib.metadata as m; print(json.dumps({'python':sys.version,'sqlite':sqlite3.sqlite_version,'packages':{d.metadata['Name']:d.version for d in m.distributions()}},indent=2))"], cwd=working_directory, check=True, capture_output=True, text=True)
environment = json.loads(probe.stdout)
environment["working_directory"] = str(working_directory)
environment["outside_checkout"] = True
(root / "validation/issue17-1/wheel-environment.json").write_text(json.dumps(environment, indent=2), encoding="utf-8")
print(probe.stdout)
working_directory.rmdir()
