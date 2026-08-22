from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig


ROOT = Path(__file__).resolve().parent


def fetch_latest_snapshot(
    settings: SupabaseConfig,
) -> dict[str, Any] | None:

    response = requests.get(
        (
            f"{settings.url}"
            f"/rest/v1/{settings.snapshot_table}"
        ),
        params={
            "select":
                "run_id,collected_at_utc,payload",

            "order":
                "collected_at_utc.desc",

            "limit":
                "1",
        },
        headers={
            "apikey":
                settings.key,

            "Authorization":
                f"Bearer {settings.key}",
        },
        timeout=
            settings.timeout_seconds,
    )

    if response.status_code != 200:
        raise RuntimeError(
            "Supabase snapshot restore failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    rows = response.json()

    if not isinstance(rows, list):
        raise RuntimeError(
            "Supabase snapshot response "
            "must be a list"
        )

    if not rows:
        return None

    row = rows[0]

    if not isinstance(row, dict):
        raise RuntimeError(
            "Supabase snapshot row "
            "must be an object"
        )

    payload = row.get(
        "payload"
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "Latest Supabase snapshot "
            "has no valid payload"
        )

    restored = dict(
        payload
    )

    if not restored.get(
        "run_id"
    ):
        restored["run_id"] = (
            row.get(
                "run_id"
            )
        )

    if not restored.get(
        "collected_at_utc"
    ):
        restored[
            "collected_at_utc"
        ] = row.get(
            "collected_at_utc"
        )

    return restored


def snapshot_path(
    config: dict[str, Any],
    root: Path = ROOT,
) -> Path:

    directory = str(
        config.get(
            "snapshot_directory",
            "data/snapshots",
        )
    )

    return (
        root
        / directory
        / "latest.json"
    )


def write_snapshot_atomic(
    path: Path,
    snapshot: dict[str, Any],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = (
        path.parent
        / ".latest.json.tmp"
    )

    temporary.write_text(
        json.dumps(
            snapshot,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(
        path
    )


def restore(
    settings: SupabaseConfig,
    config: dict[str, Any],
    *,
    root: Path = ROOT,
) -> Path | None:

    snapshot = (
        fetch_latest_snapshot(
            settings
        )
    )

    if snapshot is None:
        return None

    path = snapshot_path(
        config,
        root,
    )

    write_snapshot_atomic(
        path,
        snapshot,
    )

    return path


def build_parser() -> argparse.ArgumentParser:

    return argparse.ArgumentParser(
        description=(
            "Restore the latest Alpha Hunter "
            "snapshot from Supabase."
        )
    )


def main(
    argv: list[str] | None = None,
) -> int:

    parser = build_parser()
    parser.parse_args(argv)

    load_env_file(
        ROOT / ".env"
    )

    config = load_config(
        ROOT / "config.json"
    )

    settings = (
        SupabaseConfig
        .from_environment(
            config
        )
    )

    if settings is None:
        raise SystemExit(
            "Supabase is not configured"
        )

    path = restore(
        settings,
        config,
    )

    if path is None:
        print(
            "No previous Supabase "
            "snapshot available."
        )

        print(
            "Restore status: BOOTSTRAP"
        )

        return 0

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    print(
        "Previous Alpha Hunter "
        "snapshot restored."
    )

    print(
        "Run ID:",
        payload.get(
            "run_id"
        ),
    )

    print(
        "Collected at:",
        payload.get(
            "collected_at_utc"
        ),
    )

    print(
        "Local path:",
        path,
    )

    print(
        "Restore status: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
