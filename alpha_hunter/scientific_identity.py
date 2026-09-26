from __future__ import annotations

import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any


SCIENTIFIC_FINGERPRINT_VERSION = "scientific-fingerprint-v0.1"
RUNTIME_DISTRIBUTIONS = ("requests", "Flask", "gunicorn")


def _scientific_paths(root: Path) -> list[Path]:
    paths: list[Path] = []

    package_root = root / "alpha_hunter"
    if package_root.exists():
        paths.extend(
            path
            for path in package_root.rglob("*.py")
            if "__pycache__" not in path.parts
        )

    for name in ("run.py", "hourly.py", "requirements.txt"):
        path = root / name
        if path.exists():
            paths.append(path)

    paths.extend(root.glob("*.sql"))

    return sorted(
        {path.resolve() for path in paths},
        key=lambda path: path.relative_to(root.resolve()).as_posix(),
    )


def _runtime_versions() -> dict[str, str]:
    versions: dict[str, str] = {
        "python": ".".join(str(part) for part in sys.version_info[:3]),
    }
    for distribution in RUNTIME_DISTRIBUTIONS:
        try:
            versions[distribution.lower()] = importlib.metadata.version(
                distribution
            )
        except importlib.metadata.PackageNotFoundError:
            versions[distribution.lower()] = "NOT_INSTALLED"
    return versions


def build_scientific_fingerprint(
    config: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    project_root = (
        root.resolve()
        if root is not None
        else Path(__file__).resolve().parents[1]
    )

    digest = hashlib.sha256()
    digest.update(SCIENTIFIC_FINGERPRINT_VERSION.encode("utf-8"))
    digest.update(b"\0")

    canonical_config = json.dumps(
        config,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest.update(b"config.json\0")
    digest.update(canonical_config)
    digest.update(b"\0")

    files: list[str] = []
    for path in _scientific_paths(project_root):
        relative = path.relative_to(project_root).as_posix()
        files.append(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")

    runtime_versions = _runtime_versions()
    digest.update(
        json.dumps(
            runtime_versions,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    return {
        "version": SCIENTIFIC_FINGERPRINT_VERSION,
        "sha256": digest.hexdigest(),
        "file_count": len(files),
        "files": files,
        "runtime_versions": runtime_versions,
    }
