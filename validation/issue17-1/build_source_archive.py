"""Archive source and explicit validation evidence, including Git-ignored logs."""

from datetime import datetime, timezone
from getpass import getpass
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

root = Path(__file__).resolve().parents[2]
out = root / "validation/issue17-1"
archive_path = out / "fastapi-notification-issue17-1-source.zip"
sidecar = out / "SOURCE_ARCHIVE.sha256"
manifest_path = out / "ARCHIVE_MANIFEST.json"
assert "READY FOR RELEASE VALIDATION" in (out / "REPORT.md").read_text(encoding="utf-8")
secret = getpass("Private credential to exclude from archive (hidden): ") if "--scan-secret" in sys.argv else None


def permitted(path):
    parts = path.relative_to(root).parts
    if any(part in {".git", ".venv", ".tox", "__pycache__", ".pytest_cache", ".mypy_cache", "htmlcov", "node_modules", "build"} or part.startswith(".validation-") for part in parts):
        return False
    if path == archive_path or path == sidecar or path == manifest_path:
        return False
    if path.suffix in {".pyc", ".pyo"} or path.name == ".coverage":
        return False
    if path.suffix == ".zip" and "source" in path.name.lower():
        return False
    if parts[0] == "validation" and path.suffix == ".html":
        return False
    return path.is_file()


names = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root).decode("utf-8").split("\0")
paths = {root / name for name in names if name and permitted(root / name)}
# Explicit walk is essential: *.log is ignored by this repository's Git config.
paths.update(path for path in (root / "validation").rglob("*") if permitted(path))
paths.add(out / "REPORT.md")
file_list = out / "FILES_CHANGED.txt"
with file_list.open("a", encoding="utf-8") as stream:
    stream.write("\nFinal delivery files:\nvalidation/issue17-1/REPORT.md\nvalidation/issue17-1/FILES_CHANGED.txt\nvalidation/issue17-1/ARCHIVE_MANIFEST.json\nvalidation/issue17-1/fastapi-notification-issue17-1-source.zip (external delivery)\nvalidation/issue17-1/SOURCE_ARCHIVE.sha256 (external sidecar)\n")
paths.add(file_list)
files = {}
for path in sorted(paths):
    payload = path.read_bytes()
    if secret:
        from urllib.parse import quote
        assert secret.encode() not in payload and quote(secret, safe="").encode() not in payload, path
    files[path.relative_to(root).as_posix()] = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
assert "validation/issue17-1/mysql.log" in files
assert all(f"validation/issue17-1/quality-{tool}.stdout.log" in files for tool in ("black", "isort", "docformatter", "pylint", "mypy"))
manifest = {"generated_utc": datetime.now(timezone.utc).isoformat(), "root_prefix": "fastapi-notification", "files": files, "file_count_without_manifest": len(files), "private_credential_scan": "PASS" if secret else "NOT RUN", "exclusions": ["environments", "downloaded interpreters/server binaries", "Git internals", "caches", "generated HTML", "nested source ZIPs", "this archive and its SHA-256 sidecar"], "source_archive_sidecar": sidecar.name}
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
paths.add(manifest_path)
with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(paths):
        archive.write(path, "fastapi-notification/" + path.relative_to(root).as_posix())
with zipfile.ZipFile(archive_path) as archive:
    assert archive.testzip() is None
    assert set(archive.namelist()) == {"fastapi-notification/" + path.relative_to(root).as_posix() for path in paths}
    for name, item in files.items():
        assert hashlib.sha256(archive.read("fastapi-notification/" + name)).hexdigest() == item["sha256"]
digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
sidecar.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
print(json.dumps({"archive": str(archive_path), "bytes": archive_path.stat().st_size, "files": len(paths), "sha256": digest, "credential_scan": manifest["private_credential_scan"], "crc_and_manifest_verification": "PASS"}, indent=2))
