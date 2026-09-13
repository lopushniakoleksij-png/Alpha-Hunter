from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from alpha_hunter.big_mover_signature import (
    build_directional_signature,
    rank_candidates,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            rows.append(value)
    return rows


def _feature_names(evidence: list[dict[str, Any]]) -> tuple[str, ...]:
    names: set[str] = set()
    for row in evidence:
        features = row.get("features")
        if not isinstance(features, dict):
            continue
        for key, value in features.items():
            if isinstance(value, bool):
                continue
            try:
                float(value)
            except (TypeError, ValueError):
                continue
            names.add(str(key))
    return tuple(sorted(names))


def run(
    *,
    evidence_path: Path,
    live_path: Path,
    config_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    evidence = _read_jsonl(evidence_path)
    live_payload = _read_json(live_path)
    config = _read_json(config_path)

    if isinstance(live_payload, dict):
        live_rows = live_payload.get("candidates", [])
    else:
        live_rows = live_payload
    if not isinstance(live_rows, list):
        raise ValueError("live input must be a list or an object containing candidates")

    universe_scan = config.get("universe_scan", {})
    if not isinstance(universe_scan, dict):
        raise ValueError("config.universe_scan must be an object")

    names = _feature_names(evidence)
    if not names:
        raise ValueError("evidence contains no numeric features")

    signatures = []
    training_errors: dict[str, str] = {}
    for direction in ("LONG", "SHORT"):
        try:
            signatures.append(
                build_directional_signature(
                    evidence,
                    direction,
                    feature_names=names,
                )
            )
        except ValueError as exc:
            training_errors[direction] = str(exc)

    if not signatures:
        raise ValueError("no directional signature could be trained")

    ranked = rank_candidates(
        (row for row in live_rows if isinstance(row, dict)),
        signatures,
        universe_scan_config=universe_scan,
    )

    payload = {
        "mode": "SHADOW_RESEARCH_ONLY",
        "shadow_only": True,
        "trade_permission": False,
        "training_errors": training_errors,
        "signatures": [signature.to_dict() for signature in signatures],
        "ranked_candidates": [candidate.to_dict() for candidate in ranked],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train and run the Alpha Hunter Big-Mover Signature Engine in shadow mode."
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--live", required=True, type=Path)
    parser.add_argument("--config", default=Path("config.json"), type=Path)
    parser.add_argument(
        "--output",
        default=Path("data/big-mover-signature/latest.json"),
        type=Path,
    )
    args = parser.parse_args()

    payload = run(
        evidence_path=args.evidence,
        live_path=args.live,
        config_path=args.config,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "mode": payload["mode"],
                "trade_permission": payload["trade_permission"],
                "signatures": [item["direction"] for item in payload["signatures"]],
                "ranked_candidates": len(payload["ranked_candidates"]),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
