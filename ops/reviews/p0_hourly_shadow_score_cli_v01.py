"""Offline command-line smoke runner for the non-deployable hourly research scorer.

Usage (no network or secrets):
  python -m ops.reviews.p0_hourly_shadow_score_cli_v01 \
    --input synthetic-fixture.json --output /tmp/hourly-research.json \
    --as-of-utc 2026-11-04T19:47:00Z

Input JSON keys: parent, children, feature_rows, profile_bundle,
universe_scan_config, expected_scientific_fingerprint.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from alpha_hunter.hourly_shadow_score import score_verified_hourly


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--as-of-utc", required=True)
    args = parser.parse_args()

    evidence = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(evidence, dict):
        raise ValueError("research fixture must be a JSON object")
    as_of = datetime.fromisoformat(args.as_of_utc.replace("Z", "+00:00"))
    result = score_verified_hourly(
        parent=evidence["parent"],
        children=evidence["children"],
        feature_rows=evidence["feature_rows"],
        profile_bundle=evidence["profile_bundle"],
        universe_scan_config=evidence["universe_scan_config"],
        expected_scientific_fingerprint=evidence["expected_scientific_fingerprint"],
        now_utc=as_of,
    )
    # Never write a 'success' output on a blocked or incomplete evidence bundle.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "mode": result["mode"],
        "source_run_id": result["source_run_id"],
        "scored_research_directions": len(result["ranked_research_only"]),
        "trade_permission": False,
        "production_promotion_permitted": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
