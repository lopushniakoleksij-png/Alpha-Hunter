from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from alpha_hunter.big_mover_evidence import (
    CORE_FEATURE_COLUMNS,
    EvidenceWindow,
    SupabaseRestReader,
    _dt,
    build_forward_evidence,
    load_shadow_inputs,
)


def _normalize_answer_key(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "symbol": row.get("symbol"),
                "audited_at_utc": row.get("observed_at_utc"),
                "mover_direction": row.get("direction"),
                "current_24h_move_pct": row.get("current_24h_move_pct"),
                "mover_threshold_pct": row.get("threshold_pct"),
                "mover_class": "BITGET_ANSWER_KEY",
                "measurement_quality": "BITGET_PUBLIC_ALL_TICKERS",
            }
        )
    return normalized


def load_shadow_inputs_forward(
    reader: SupabaseRestReader,
    *,
    now: datetime | None = None,
    training_days: int = 21,
    horizon_hours: int = 24,
    mover_threshold_pct: float = 10.0,
    control_ceiling_pct: float = 5.0,
    pre_expansion_abs_move_pct: float = 5.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], EvidenceWindow, dict[str, Any]]:
    """Bootstrap from historical audits, then append only mature forward answer-key labels.

    The answer-key collector starts at a known point in time. We therefore never use
    absence of an answer-key event as a CONTROL until a feature snapshot's entire
    forward horizon is covered by the answer-key stream. This prevents the first day
    of collection from falsely relabeling historical snapshots as non-movers.
    """
    reference_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    evidence, live_candidates, window, context = load_shadow_inputs(
        reader,
        now=reference_now,
        training_days=training_days,
        horizon_hours=horizon_hours,
        mover_threshold_pct=mover_threshold_pct,
        control_ceiling_pct=control_ceiling_pct,
        pre_expansion_abs_move_pct=pre_expansion_abs_move_pct,
    )

    coverage = reader.get_rows(
        "alpha_hunter_big_mover_answer_key",
        {
            "select": "observed_at_utc",
            "order": "observed_at_utc.asc",
        },
    )
    if not coverage:
        context.update(
            {
                "answer_key_status": "NOT_STARTED",
                "answer_key_first_at_utc": None,
                "answer_key_latest_at_utc": None,
                "answer_key_staleness_hours": None,
                "forward_answer_key_evidence_rows": 0,
            }
        )
        return evidence, live_candidates, window, context

    first_at = min(_dt(row["observed_at_utc"]) for row in coverage)
    latest_at = max(_dt(row["observed_at_utc"]) for row in coverage)
    mature_training_end = latest_at - timedelta(hours=horizon_hours)
    staleness_hours = max(
        0.0,
        (reference_now - latest_at).total_seconds() / 3600.0,
    )

    context.update(
        {
            "answer_key_status": (
                "MATURE_FORWARD_LABELS_AVAILABLE"
                if mature_training_end >= first_at
                else "COLLECTING_FIRST_HORIZON"
            ),
            "answer_key_first_at_utc": first_at.isoformat(),
            "answer_key_latest_at_utc": latest_at.isoformat(),
            "answer_key_staleness_hours": round(staleness_hours, 3),
            "forward_answer_key_evidence_rows": 0,
        }
    )

    if mature_training_end < first_at:
        return evidence, live_candidates, window, context

    feature_select = ",".join(
        (
            "signal_id",
            "run_id",
            "symbol",
            "captured_at_utc",
            "state",
            "direction",
            *CORE_FEATURE_COLUMNS,
            "features",
            "source_payload",
        )
    )
    forward_features = reader.get_rows(
        "alpha_hunter_signal_features",
        {
            "select": feature_select,
            "captured_at_utc": f"gte.{first_at.isoformat()}",
            "and": f"(captured_at_utc.lte.{mature_training_end.isoformat()})",
            "order": "captured_at_utc.asc",
        },
    )
    answer_rows = reader.get_rows(
        "alpha_hunter_big_mover_answer_key",
        {
            "select": (
                "symbol,observed_at_utc,direction,threshold_pct,"
                "current_24h_move_pct"
            ),
            "observed_at_utc": f"gte.{first_at.isoformat()}",
            "and": f"(observed_at_utc.lte.{latest_at.isoformat()})",
            "order": "observed_at_utc.asc",
        },
    )
    forward_evidence = build_forward_evidence(
        forward_features,
        _normalize_answer_key(answer_rows),
        horizon_hours=horizon_hours,
        mover_threshold_pct=mover_threshold_pct,
        control_ceiling_pct=control_ceiling_pct,
        pre_expansion_abs_move_pct=pre_expansion_abs_move_pct,
    )

    # The historical audit bootstrap is retained only before answer-key coverage.
    # Once the answer-key stream covers a timestamp, that stream is authoritative.
    evidence = [
        row
        for row in evidence
        if _dt(row.get("captured_at_utc")) < first_at
    ] + forward_evidence
    context["forward_answer_key_evidence_rows"] = len(forward_evidence)
    context["historical_bootstrap_evidence_rows"] = len(evidence) - len(forward_evidence)
    return evidence, live_candidates, window, context
