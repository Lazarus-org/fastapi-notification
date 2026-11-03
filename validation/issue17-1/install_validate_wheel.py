"""Install final artifact, check its dependency graph, and run isolated smoke."""

from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
python = str(root / ".validation-venv/Scripts/python.exe")
target = str(root / ".validation-wheel-final/Scripts/python.exe")
subprocess.run([python, "-m", "uv", "pip", "install", "--python", target, "--reinstall-package", "fastapi-notification", str(root / "validation/issue17-1/dist/fastapi_notification-1.0.0-py3-none-any.whl"), "aiosqlite>=0.20,<0.21"], cwd=root, check=True)
subprocess.run([python, "-m", "uv", "pip", "check", "--python", target], cwd=root, check=True)
subprocess.run([python, str(root / "validation/issue17-1/wheel_runtime.py")], cwd=root, check=True)
