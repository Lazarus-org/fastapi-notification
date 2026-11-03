"""Capture new Issue 17.2 runs, keeping earlier evidence untouched."""

import importlib.metadata as metadata
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread

root = Path(__file__).resolve().parents[3]
target = (
    root / "fastapi-notification"
    if (root / "fastapi-notification/pyproject.toml").is_file()
    else root
)
out = root / "validation/issue17-2-runtime"
name, *command = sys.argv[1:]
environment = os.environ.copy()
environment["PYLINTHOME"] = str(root / ".validation-cache/pylint-issue17-2")
environment["VIRTUALENV_APP_DATA"] = str(root / ".validation-cache/virtualenv")
started = datetime.now(timezone.utc)
process = subprocess.Popen(
    command,
    cwd=target,
    env=environment,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    errors="replace",
)


def capture(pipe, path):
    with path.open("w", encoding="utf-8") as stream:
        for line in pipe:
            stream.write(line)
            stream.flush()


threads = [
    Thread(target=capture, args=(process.stdout, out / f"{name}.stdout.log")),
    Thread(target=capture, args=(process.stderr, out / f"{name}.stderr.log")),
]
for thread in threads:
    thread.start()
code = process.wait()
for thread in threads:
    thread.join()
(out / f"{name}.log").write_text(
    (out / f"{name}.stdout.log").read_text(encoding="utf-8")
    + "\n--- STDERR ---\n"
    + (out / f"{name}.stderr.log").read_text(encoding="utf-8"),
    encoding="utf-8",
)
record = {
    "command": command,
    "cwd": str(target),
    "exit_code": code,
    "started_utc": started.isoformat(),
    "ended_utc": datetime.now(timezone.utc).isoformat(),
    "python": sys.version,
    "versions": {d.metadata["Name"]: d.version for d in metadata.distributions()},
}
(out / f"{name}.result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print(name, "exit", code, flush=True)
raise SystemExit(code)
