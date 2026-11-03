"""Rebuild and inspect the final source, including the published README."""

import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
environment = os.environ.copy()
environment["VIRTUAL_ENV"] = str(root / ".validation-venv")
subprocess.run(["C:/Python315/python.exe", "-m", "poetry", "build", "--output", "validation/issue17-1/dist"], cwd=root, env=environment, check=True)
subprocess.run([str(root / ".validation-venv/Scripts/python.exe"), str(root / "validation/issue17-1/inspect_distribution.py")], cwd=root, check=True)
subprocess.run([str(root / ".validation-tools/Scripts/python.exe"), "-m", "twine", "check", str(root / "validation/issue17-1/dist/fastapi_notification-1.0.0-py3-none-any.whl"), str(root / "validation/issue17-1/dist/fastapi_notification-1.0.0.tar.gz")], cwd=root, check=True)
