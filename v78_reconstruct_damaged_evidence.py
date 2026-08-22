from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig
import v78_timing_rr_decay_shadow as v78


ROOT = Path(__file__).resolve().parent
TABLE = v78.TABLE
SCHEMA_VERSION = 1
DAMAGED_QUALITY = "INSUFFICIENT_CANDLE_HISTORY"
CONFIRM_ENV = (
    "ALPHA_HUNTER_V78_RECONSTRUCTION_CONFIRM"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def readonly_headers(
    settings: SupabaseConfig,
) -> dict[str, str]:
    return {
        "apikey": settings.key,
        "Authorization": f"Bearer {settings.key}",
    }


def load_rows(
    settings: SupabaseConfig,
    page_size: int = 1000,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = requests.get(
            f"{settings.url}/rest/v1/{TABLE}",
            params={
                "select": (
                    "snapshot_id,episode_id,symbol,"
                    "phase,phase_at_utc,"
                    "measurement_quality"
                ),
                "order": "snapshot_id.asc",
                "limit": str(page_size),
                "offset": str(offset),
            },
            headers=readonly_headers(settings),
            timeout=settings.timeout_seconds,
        )

        if response.status_code != 200:
            raise RuntimeError(
                "V7.8 reconstruction evidence load failed: "
                f"HTTP {response.status_code}: "
                f"{response.text[:800]}"
            )

        payload = response.json()

        if not isinstance(payload, list):
            raise RuntimeError(
                "V7.8 reconstruction response is not a list"
            )

        rows.extend(
            row
            for row in payload
            if isinstance(row, dict)
        )

        if len(payload) < page_size:
            break

        offset += page_size

    return rows


def candidate_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    unexpected: list[str] = []

    for row in rows:
        quality = str(
            row.get("measurement_quality")
            or ""
        ).upper()

        if quality == "COMPLETE":
            continue

        snapshot_id = str(
            row.get("snapshot_id")
            or ""
        )

        if quality != DAMAGED_QUALITY:
            unexpected.append(
                f"{snapshot_id or '<missing>'}:{quality or '<missing>'}"
            )
            continue

        if not snapshot_id:
            unexpected.append(
                "<missing>:INSUFFICIENT_CANDLE_HISTORY"
            )
            continue

        candidates.append({
            "snapshot_id": snapshot_id,
            "episode_id": str(
                row.get("episode_id")
                or ""
            ),
            "symbol": str(
                row.get("symbol")
                or ""
            ),
            "phase": str(
                row.get("phase")
                or ""
            ),
            "phase_at_utc": str(
                row.get("phase_at_utc")
                or ""
            ),
            "measurement_quality": quality,
        })

    if unexpected:
        raise RuntimeError(
            "Unexpected non-COMPLETE V7.8 qualities: "
            + ", ".join(sorted(unexpected))
        )

    candidates.sort(
        key=lambda row: row["snapshot_id"]
    )

    return candidates


def digest_payload(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE,
        "candidates": sorted(
            candidates,
            key=lambda row: row["snapshot_id"],
        ),
    }


def manifest_digest(
    candidates: list[dict[str, Any]],
) -> str:
    encoded = json.dumps(
        digest_payload(candidates),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def build_manifest(
    candidates: list[dict[str, Any]],
    created_at: datetime | None = None,
) -> dict[str, Any]:
    ordered = sorted(
        candidates,
        key=lambda row: row["snapshot_id"],
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "table": TABLE,
        "created_at_utc": (
            created_at
            or utc_now()
        ).isoformat(),
        "candidate_count": len(ordered),
        "candidate_digest": manifest_digest(ordered),
        "candidates": ordered,
        "trade_permission": False,
    }


def verify_manifest(
    manifest: dict[str, Any],
    current_candidates: list[dict[str, Any]],
) -> str:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(
            "Unsupported reconstruction manifest schema"
        )

    if manifest.get("table") != TABLE:
        raise RuntimeError(
            "Reconstruction manifest table mismatch"
        )

    frozen = manifest.get("candidates")

    if not isinstance(frozen, list):
        raise RuntimeError(
            "Reconstruction manifest candidates are invalid"
        )

    expected_digest = manifest_digest(frozen)

    if manifest.get("candidate_digest") != expected_digest:
        raise RuntimeError(
            "Reconstruction manifest digest mismatch"
        )

    current_digest = manifest_digest(
        current_candidates
    )

    if current_digest != expected_digest:
        raise RuntimeError(
            "V7.8 candidate set drifted after dry-run"
        )

    if manifest.get("candidate_count") != len(frozen):
        raise RuntimeError(
            "Reconstruction manifest count mismatch"
        )

    return expected_digest


def write_manifest(
    path: Path,
    manifest: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run and explicitly apply controlled "
            "V7.8 damaged-evidence reconstruction."
        )
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        help="Write the frozen dry-run manifest.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply only a previously frozen manifest.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Frozen manifest required with --apply.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.apply != bool(args.manifest):
        raise SystemExit(
            "--apply and --manifest must be used together"
        )

    load_env_file(ROOT / ".env")
    config = load_config(ROOT / "config.json")
    settings = SupabaseConfig.from_environment(config)

    if settings is None:
        raise SystemExit("Supabase is not configured")

    current = candidate_rows(
        load_rows(settings)
    )

    if not args.apply:
        manifest = build_manifest(current)

        if args.manifest_out:
            write_manifest(
                args.manifest_out,
                manifest,
            )

        print(json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        ))
        print("DRY RUN ONLY — no Supabase writes performed")
        return 0

    manifest = json.loads(
        args.manifest.read_text(
            encoding="utf-8"
        )
    )
    digest = verify_manifest(
        manifest,
        current,
    )

    if not current:
        raise SystemExit(
            "No damaged V7.8 candidates to reconstruct"
        )

    if os.environ.get(CONFIRM_ENV) != digest:
        raise SystemExit(
            f"Set {CONFIRM_ENV} to the verified "
            "candidate digest before --apply"
        )

    snapshot_ids = {
        row["snapshot_id"]
        for row in current
    }

    print(
        "APPLYING CONTROLLED V7.8 RECONSTRUCTION",
        f"candidates={len(snapshot_ids)}",
        f"digest={digest}",
    )

    return v78.main(
        reconstruction_snapshot_ids=
            snapshot_ids,
    )


if __name__ == "__main__":
    raise SystemExit(main())
