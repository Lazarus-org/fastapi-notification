import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import sqlite3
import sys

packages = {d.metadata["Name"]: d.version for d in metadata.distributions()}
result = {"python": sys.version, "platform": platform.platform(), "architecture": platform.machine(), "sqlite": sqlite3.sqlite_version, "packages": dict(sorted(packages.items(), key=lambda item: item[0].lower()))}
Path(sys.argv[1]).write_text(json.dumps(result, indent=2), encoding="utf-8")
