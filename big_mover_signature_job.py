from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from alpha_hunter.big_mover_signature import (
    DEFAULT_NUMERIC_FEATURES,
    ENGINE_VERSION,
    TRADE_PERMISSION,
    fit_signature,
    rank_candidates,
)


def load_rows(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []

    if source.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("JSONL rows must be objects")
            rows.append(value)
        return rows

    value = json.loads(text)
    if isinstance(value, list):
        rows = value
    elif isinstance(value, dict):
        rows = value.get("rows")
    else:
        rows = None

    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("JSON input must be a list of objects or {'rows': [...]}")

    return rows


def run_shadow_scan(
    training_rows: Iterable[dict[str, Any]],
    candidate_rows: Iterable[dict[str, Any]],
    *,
    min_movers: int,
    min_controls: int,
    feature_names: Iterable[str] = DEFAULT_NUMERIC_FEATURES,
) -> dict[str, Any]:
    training = list(training_rows)
    candidates = list(candidate_rows)
    selected_features = tuple(feature_names)

    long_model = fit_signature(
        training,
        direction="LONG",
        feature_names=selected_features,
        min_movers=min_movers,
        min_controls=min_controls,
    )
    short_model = fit_signature(
        training,
        direction="SHORT",
        feature_names=selected_features,
        min_movers=min_movers,
        min_controls=min_controls,
    )

    ranked = rank_candidates(
        candidates,
        long_model=long_model,
        short_model=short_model,
        safety_eligibility_field="safety_eligible",
    )

    return {
        "version": ENGINE_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW",
        "shadow_only": True,
        "trade_permission": TRADE_PERMISSION,
        "training_rows": len(training),
        "candidate_rows": len(candidates),
        "features_requested": list(selected_features),
        "long_model_status": long_model.get("status"),
        "short_model_status": short_model.get("status"),
        "long_mover_samples": long_model.get("mover_samples"),
        "long_control_samples": long_model.get("control_samples"),
        "short_mover_samples": short_model.get("mover_samples"),
        "short_control_samples": short_model.get("control_samples"),
        "ranked_candidates": ranked,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Shadow-only Bitget Futures Big Mover Signature scanner. "
            "Consumes labelled pre-move/control evidence and current candidate rows."
        )
    )
    parser.add_argument(
        "--training",
        required=True,
        help="JSON/JSONL labelled training rows",
    )
    parser.add_argument(
        "--candidates",
        required=True,
        help="JSON/JSONL current universe rows",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON path; stdout when omitted",
    )
    parser.add_argument("--min-movers", required=True, type=int)
    parser.add_argument("--min-controls", required=True, type=int)
    parser.add_argument(
        "--feature",
        dest="features",
        action="append",
        help="Feature path to include; repeatable. Defaults to engine feature set.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    training_rows = load_rows(args.training)
    candidate_rows = load_rows(args.candidates)
    features = tuple(args.features) if args.features else DEFAULT_NUMERIC_FEATURES

    report = run_shadow_scan(
        training_rows,
        candidate_rows,
        min_movers=args.min_movers,
        min_controls=args.min_controls,
        feature_names=features,
    )
    payload = json.dumps(report, indent=2, sort_keys=True)

    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
