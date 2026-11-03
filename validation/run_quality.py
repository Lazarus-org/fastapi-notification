"""Execute configured quality checks and preserve exit codes and full logs."""
import json
from pathlib import Path
import subprocess
import sys

checks = {
    "black": ["-m", "black", "--check", "fastapi_notification"],
    "isort": ["-m", "isort", "--check-only", "fastapi_notification"],
    "pylint": ["-m", "pylint", "fastapi_notification", "--rcfile=pyproject.toml"],
    "mypy": ["-m", "mypy", "fastapi_notification"],
    "bandit": ["-m", "bandit", "-c", "pyproject.toml", "-r", "fastapi_notification"],
    "docformatter": ["-m", "docformatter", "--check", "--recursive", "--wrap-summaries", "88", "--wrap-descriptions", "88", "fastapi_notification"],
    "dependencies": ["-m", "pip", "check"],
    "poetry": ["-m", "poetry", "check", "--lock"],
}
results = {}
for name, command in checks.items():
    with Path(f"validation/quality-{name}.log").open("w", encoding="utf-8") as log:
        result = subprocess.run([sys.executable, *command], stdout=log, stderr=subprocess.STDOUT)
    results[name] = {"command": [sys.executable, *command], "exit_code": result.returncode}
    Path("validation/quality-results.json").write_text(json.dumps(results, indent=2))
