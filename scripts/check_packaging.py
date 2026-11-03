"""Check release metadata, tags and built archives without importing the package."""

from __future__ import annotations

import argparse
import re
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PackageMetadata:
    name: str
    version: str
    python: str
    module: str
    dependencies: frozenset[str]


def canonical_name(value: str) -> str:
    """Normalize distribution names for metadata comparisons."""
    return re.sub(r"[-_.]+", "-", value).lower()


def require(condition: bool, message: str) -> None:
    """Stop a release check with an actionable diagnostic."""
    if not condition:
        raise ValueError(message)


def check_metadata(payload: bytes, project: PackageMetadata, label: str) -> None:
    """Require built metadata to match the declared runtime package."""
    metadata = BytesParser().parsebytes(payload)
    require(
        canonical_name(str(metadata.get("Name", ""))) == canonical_name(project.name),
        f"{label}: package name mismatch",
    )
    require(
        metadata.get("Version") == project.version, f"{label}: package version mismatch"
    )
    declared_python = project.python
    require(
        {part.strip() for part in str(metadata.get("Requires-Python", "")).split(",")}
        == {part.strip() for part in declared_python.split(",")},
        f"{label}: Python requirement mismatch",
    )
    expected = project.dependencies
    actual = set()
    for requirement in metadata.get_all("Requires-Dist", []):
        match = re.match(r"[A-Za-z0-9][A-Za-z0-9_.-]*", requirement)
        if match is None:
            raise ValueError(f"{label}: malformed Requires-Dist")
        actual.add(canonical_name(match.group()))
    require(
        actual == expected, f"{label}: runtime dependencies differ from pyproject.toml"
    )


def read_tar_member(archive: tarfile.TarFile, name: str) -> bytes:
    stream = archive.extractfile(name)
    if stream is None:
        raise ValueError(f"Sdist member is not a regular file: {name}")
    return stream.read()


def check_distributions(directory: Path, project: PackageMetadata) -> None:
    """Inspect the wheel/sdist contents and compare production files bytewise."""
    require(directory.is_dir(), f"Missing distribution directory: {directory}")
    wheels = list(directory.glob("*.whl"))
    sdists = list(directory.glob("*.tar.gz"))
    require(len(wheels) == len(sdists) == 1, "Expected exactly one wheel and one sdist")
    require(
        {path.name for path in directory.iterdir()} == {wheels[0].name, sdists[0].name},
        "Unexpected files in distribution directory",
    )
    production = [
        path
        for path in (ROOT / project.module).rglob("*.py")
        if "tests" not in path.relative_to(ROOT).parts
    ]
    check_wheel(wheels[0], project, production)
    check_sdist(sdists[0], project, production)
    print(f"Distribution contents verified: {wheels[0].name}, {sdists[0].name}")


def check_wheel(path: Path, project: PackageMetadata, production: list[Path]) -> None:
    """Verify wheel metadata, source bytes and excluded tests/caches."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(
            not any(
                "tests" in PurePosixPath(name).parts
                or "__pycache__" in PurePosixPath(name).parts
                or PurePosixPath(name).suffix in {".pyc", ".pyo"}
                for name in names
            ),
            "Wheel contains tests or Python caches",
        )
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        require(len(metadata) == 1, "Expected one wheel METADATA file")
        check_metadata(archive.read(metadata[0]), project, "wheel")
        for source in production:
            name = source.relative_to(ROOT).as_posix()
            require(
                name in names and archive.read(name) == source.read_bytes(),
                f"Wheel source differs from checkout: {name}",
            )


def check_sdist(path: Path, project: PackageMetadata, production: list[Path]) -> None:
    """Verify sdist metadata and the included reference migrations."""
    with tarfile.open(path) as archive:
        names = archive.getnames()
        require(
            not any(
                "tests" in PurePosixPath(name).parts
                or "__pycache__" in PurePosixPath(name).parts
                or PurePosixPath(name).suffix in {".pyc", ".pyo"}
                for name in names
            ),
            "Sdist contains tests or Python caches",
        )
        metadata = [
            name
            for name in names
            if len(PurePosixPath(name).parts) == 2 and name.endswith("/PKG-INFO")
        ]
        require(len(metadata) == 1, "Expected one top-level sdist PKG-INFO file")
        check_metadata(read_tar_member(archive, metadata[0]), project, "sdist")
        prefix = metadata[0].split("/")[0]
        migrations = [
            path
            for path in (ROOT / "migrations").rglob("*")
            if path.suffix in {".py", ".md"} and "__pycache__" not in path.parts
        ]
        for source in [*production, *migrations]:
            name = prefix + "/" + source.relative_to(ROOT).as_posix()
            require(
                name in names and read_tar_member(archive, name) == source.read_bytes(),
                f"Sdist source differs from checkout: {source.relative_to(ROOT)}",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Release tag, exactly v<package-version>")
    parser.add_argument(
        "--dist-dir", type=Path, help="Also inspect built wheel and sdist"
    )
    arguments = parser.parse_args()
    configuration = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declaration = configuration["tool"]["poetry"]
    project = PackageMetadata(
        name=declaration["name"],
        version=declaration["version"],
        python=declaration["dependencies"]["python"],
        module=declaration["packages"][0]["include"],
        dependencies=frozenset(
            canonical_name(name)
            for name in declaration["dependencies"]
            if name != "python"
        ),
    )
    version = project.version
    require(
        version == configuration["tool"]["commitizen"]["version"],
        "Poetry and Commitizen versions differ",
    )
    require(
        configuration["tool"]["semantic_release"]["version_toml"]
        == ["pyproject.toml:tool.poetry.version"],
        "Semantic-release must use the Poetry version",
    )
    require((ROOT / declaration["readme"]).is_file(), "Declared README is missing")
    require((ROOT / "LICENCE").is_file(), "License file is missing")
    if arguments.tag is not None:
        require(
            arguments.tag == f"v{version}",
            f"Release tag {arguments.tag!r} must equal v{version}",
        )
    if arguments.dist_dir is not None:
        check_distributions(arguments.dist_dir, project)
    print(f"Packaging metadata verified: {project.name} {version}")


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        OSError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        raise SystemExit(f"Packaging check failed: {error}") from error
