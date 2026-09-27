#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FIXED_RUNTIME_PATHS = (
    ".python-version",
    "requirements.txt",
    "config.json",
    "run.py",
    "hourly.py",
    "performance_job.py",
    "feature_job.py",
    "outcome_job.py",
    "ops/collect_execution_quality_readonly.py",
    "ops/collect_candidate_retention_shadow.py",
    "ops/runtime_release_fingerprint.py",
)


def runtime_release_paths(root: Path) -> list[Path]:
    root = root.resolve()
    paths: set[Path] = set()

    for relative in FIXED_RUNTIME_PATHS:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(
                f"Required runtime file missing: {relative}"
            )
        paths.add(path)

    package_root = root / "alpha_hunter"
    if not package_root.is_dir():
        raise FileNotFoundError("Required runtime package missing: alpha_hunter")

    for path in package_root.rglob("*.py"):
        if path.is_file():
            paths.add(path)

    return sorted(
        paths,
        key=lambda path: path.relative_to(root).as_posix(),
    )


def compute_runtime_release_fingerprint(root: Path) -> dict[str, object]:
    root = root.resolve()
    paths = runtime_release_paths(root)
    digest = hashlib.sha256()
    relative_paths: list[str] = []

    for path in paths:
        relative = path.relative_to(root).as_posix()
        payload = path.read_bytes()
        relative_paths.append(relative)

        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")

    return {
        "runtime_fingerprint_sha256": digest.hexdigest(),
        "runtime_file_count": len(relative_paths),
        "runtime_files": relative_paths,
        "algorithm": "sha256-path-length-bytes-v01",
        "secret_values_included": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute Alpha Hunter Render Cron runtime fingerprint."
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args()

    result = compute_runtime_release_fingerprint(Path(args.root))

    if args.github_output:
        import os

        output_path = os.getenv("GITHUB_OUTPUT")
        if not output_path:
            raise SystemExit("GITHUB_OUTPUT is not configured")
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(
                "runtime_fingerprint_sha256="
                f"{result['runtime_fingerprint_sha256']}\n"
            )
            handle.write(
                f"runtime_file_count={result['runtime_file_count']}\n"
            )

    if args.json or not args.github_output:
        print(json.dumps(result, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
