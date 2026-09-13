from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha_hunter.big_mover_evidence import (
    SupabaseRestReader,
    load_shadow_inputs,
    summarize_evidence,
)
from alpha_hunter.big_mover_priority import (
    is_early_entry_candidate,
    prioritize_early_money,
)
from alpha_hunter.big_mover_signature import (
    ENGINE_VERSION,
    build_directional_signature,
    rank_candidates,
)
from alpha_hunter.env import load_env_file


SHADOW_TABLE = "alpha_hunter_big_mover_shadow"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _observation_id(run_id: str, symbol: str, direction: str) -> str:
    raw = f"{ENGINE_VERSION}|{run_id}|{symbol}|{direction}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


def _shadow_rows(
    *,
    run_id: str,
    captured_at_utc: str,
    ranked: list,
    signatures: list,
    evidence_window: dict[str, Any],
) -> list[dict[str, Any]]:
    signature_by_direction = {item.direction: item for item in signatures}
    rows: list[dict[str, Any]] = []
    for candidate in ranked:
        signature = signature_by_direction[candidate.direction]
        rows.append(
            {
                "observation_id": _observation_id(
                    run_id,
                    candidate.symbol,
                    candidate.direction,
                ),
                "run_id": run_id,
                "captured_at_utc": captured_at_utc,
                "symbol": candidate.symbol,
                "direction": candidate.direction,
                "similarity_score": candidate.similarity_score,
                "feature_coverage": candidate.feature_coverage,
                "lifecycle": candidate.lifecycle,
                "research_status": candidate.research_status,
                "current_move_pct": candidate.directional_move_pct,
                "model_version": candidate.version,
                "mover_examples": signature.mover_examples,
                "control_examples": signature.control_examples,
                "training_end_utc": evidence_window["training_end_utc"],
                "latest_audit_utc": evidence_window["latest_audit_utc"],
                "audit_staleness_hours": evidence_window["audit_staleness_hours"],
                "blockers": list(candidate.blockers),
                "contributions": list(candidate.contributions),
                "shadow_only": True,
                "trade_permission": False,
            }
        )
    return rows


def run(
    *,
    root: Path,
    config_path: Path,
    output_path: Path,
    persist: bool,
    training_days: int,
    horizon_hours: int,
) -> dict[str, Any]:
    load_env_file(root / ".env")
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("Supabase service-role environment is not configured")

    config = _read_json(config_path)
    universe_scan = config.get("universe_scan")
    if not isinstance(universe_scan, dict):
        raise RuntimeError("config.universe_scan must be an object")

    reader = SupabaseRestReader(url, key)
    evidence, live_candidates, window, context = load_shadow_inputs(
        reader,
        now=datetime.now(timezone.utc),
        training_days=training_days,
        horizon_hours=horizon_hours,
        mover_threshold_pct=10.0,
        control_ceiling_pct=5.0,
        pre_expansion_abs_move_pct=5.0,
    )
    feature_names = _feature_names(evidence)
    if not feature_names:
        raise RuntimeError("forward evidence contains no numeric features")

    signatures = []
    training_errors: dict[str, str] = {}
    for direction in ("LONG", "SHORT"):
        try:
            signatures.append(
                build_directional_signature(
                    evidence,
                    direction,
                    feature_names=feature_names,
                )
            )
        except ValueError as exc:
            training_errors[direction] = str(exc)

    if not signatures:
        raise RuntimeError("no directional signature could be trained")

    ranked = rank_candidates(
        live_candidates,
        signatures,
        universe_scan_config=universe_scan,
    )
    ranked = prioritize_early_money(ranked)

    evidence_summary = summarize_evidence(evidence)
    evidence_health = (
        "CURRENT"
        if window.audit_staleness_hours <= 48.0
        else "DEGRADED_STALE_OUTCOME_LEDGER"
    )
    payload = {
        "mode": "PRODUCTION_EVIDENCE_SHADOW_ONLY",
        "shadow_only": True,
        "trade_permission": False,
        "engine_version": ENGINE_VERSION,
        "evidence_health": evidence_health,
        "evidence_window": window.to_dict(),
        "evidence_summary": evidence_summary,
        "source_context": context,
        "training_errors": training_errors,
        "signatures": [item.to_dict() for item in signatures],
        "ranked_candidates": [item.to_dict() for item in ranked],
        "top_pre_mover_long": next(
            (
                item.to_dict()
                for item in ranked
                if item.direction == "LONG"
                and is_early_entry_candidate(item)
            ),
            None,
        ),
        "top_pre_mover_short": next(
            (
                item.to_dict()
                for item in ranked
                if item.direction == "SHORT"
                and is_early_entry_candidate(item)
            ),
            None,
        ),
        "persisted_rows": 0,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if persist:
        rows = _shadow_rows(
            run_id=context["latest_feature_run_id"],
            captured_at_utc=context["latest_feature_at_utc"],
            ranked=ranked,
            signatures=signatures,
            evidence_window=window.to_dict(),
        )
        payload["persisted_rows"] = reader.insert_rows(SHADOW_TABLE, rows)
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Train the Big-Mover Signature Engine from canonical production evidence "
            "and score the latest Alpha Hunter feature universe in shadow mode."
        )
    )
    parser.add_argument("--config", default=Path("config.json"), type=Path)
    parser.add_argument(
        "--output",
        default=Path("data/big-mover-signature/production-shadow-latest.json"),
        type=Path,
    )
    parser.add_argument("--training-days", type=int, default=21)
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist shadow rankings to alpha_hunter_big_mover_shadow.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    payload = run(
        root=root,
        config_path=(root / args.config if not args.config.is_absolute() else args.config),
        output_path=(root / args.output if not args.output.is_absolute() else args.output),
        persist=args.persist,
        training_days=args.training_days,
        horizon_hours=args.horizon_hours,
    )

    print(
        json.dumps(
            {
                "mode": payload["mode"],
                "shadow_only": payload["shadow_only"],
                "trade_permission": payload["trade_permission"],
                "evidence_health": payload["evidence_health"],
                "evidence_rows": payload["evidence_summary"]["rows"],
                "ranked_candidates": len(payload["ranked_candidates"]),
                "persisted_rows": payload["persisted_rows"],
                "top_pre_mover_long": (
                    payload["top_pre_mover_long"] or {}
                ).get("symbol"),
                "top_pre_mover_short": (
                    payload["top_pre_mover_short"] or {}
                ).get("symbol"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
