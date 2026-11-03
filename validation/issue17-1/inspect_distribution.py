"""Inspect final artifacts and record checksums without importing the checkout."""

import email
import hashlib
import json
from pathlib import Path
import tarfile
import zipfile

from packaging.specifiers import SpecifierSet

root = Path(__file__).resolve().parents[2]
out = root / "validation/issue17-1"
distribution = out / "dist"
checksums = {
    path.name: {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    for path in sorted(distribution.iterdir())
}
with zipfile.ZipFile(next(distribution.glob("*.whl"))) as archive:
    names = archive.namelist()
    assert not any("/tests/" in name for name in names)
    metadata = email.message_from_bytes(
        archive.read(next(name for name in names if name.endswith("/METADATA")))
    )
    assert metadata["Version"] == "1.0.0"
    assert SpecifierSet(metadata["Requires-Python"]) == SpecifierSet(">=3.11,<4.0")
    classifiers = metadata.get_all("Classifier")
    for version in ("3.11", "3.12", "3.13", "3.14", "3.15"):
        assert "Programming Language :: Python :: " + version in classifiers
    for version in ("3.9", "3.10"):
        assert "Programming Language :: Python :: " + version not in classifiers
    for path in (root / "fastapi_notification").rglob("*.py"):
        if "tests" not in path.parts:
            assert archive.read(path.relative_to(root).as_posix()) == path.read_bytes()
    inspection = {
        "version": metadata["Version"],
        "requires_python": metadata["Requires-Python"],
        "classifiers": classifiers,
        "requires_dist": metadata.get_all("Requires-Dist"),
        "wheel_file_count": len(names),
        "tests_bundled": False,
        "all_production_python_files_match_checkout": True,
    }
with tarfile.open(next(distribution.glob("*.tar.gz"))) as archive:
    names = archive.getnames()
    assert not any("/fastapi_notification/tests/" in name for name in names)
    revision = next(name for name in names if name.endswith("/migrations/versions/20261103_mysql_identity_precision.py"))
    assert archive.extractfile(revision).read() == (root / "migrations/versions/20261103_mysql_identity_precision.py").read_bytes()
    inspection["migration_in_sdist"] = True
(out / "distribution-checksums.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
(out / "distribution-inspection.json").write_text(json.dumps(inspection, indent=2), encoding="utf-8")
print(json.dumps({"checksums": checksums, "inspection": inspection}, indent=2))
