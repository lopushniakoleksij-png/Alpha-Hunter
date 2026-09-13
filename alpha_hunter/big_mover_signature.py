from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import fmean, pstdev
from typing import Any, Iterable


ENGINE_VERSION = "big-mover-signature-shadow-v0.1"
SHADOW_ONLY = True
TRADE_PERMISSION = False

DEFAULT_NUMERIC_FEATURES = (
    "source_payload.change_24h_pct",
    "volume_ratio",
    "volatility_pct",
    "compression_score",
    "funding_rate",
    "open_interest_change_pct",
    "relative_strength_btc",
    "diagnostic_context.behaviour_score",
    "diagnostic_context.relative_strength_acceleration",
    "diagnostic_context.funding_change_pct",
    "diagnostic_context.spread_pct",
    "distance_to_support_pct",
    "distance_to_resistance_pct",
)


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A", "—"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested(record: dict[str, Any], path: str) -> Any:
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _feature_value(record: dict[str, Any], name: str) -> float | None:
    direct = _float(record.get(name))
    if direct is not None:
        return direct

    value = _float(_nested(record, name))
    if value is not None:
        return value

    features = record.get("features")
    if isinstance(features, dict):
        value = _float(_nested(features, name))
        if value is not None:
            return value

    source_payload = record.get("source_payload")
    if isinstance(source_payload, dict):
        value = _float(_nested(source_payload, name))
        if value is not None:
            return value

    return None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif value not in (None, ""):
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_scale(values: list[float], delta: float) -> float:
    if len(values) > 1:
        scale = pstdev(values)
        if scale > 1e-12:
            return scale
    return max(abs(delta), 1e-9)


def fit_signature(
    examples: Iterable[dict[str, Any]],
    *,
    direction: str,
    feature_names: Iterable[str] = DEFAULT_NUMERIC_FEATURES,
    min_movers: int,
    min_controls: int,
) -> dict[str, Any]:
    """Learn empirical feature separation for one mover direction.

    Training rows must be pre-move snapshots labelled with target_direction
    and is_mover. The caller owns sample-count policy; the engine fails closed
    until both mover and non-mover control requirements are met.
    """
    direction = str(direction).upper()
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")
    if min_movers < 1 or min_controls < 1:
        raise ValueError("minimum sample counts must be positive")

    rows = [
        row for row in examples
        if str(row.get("target_direction") or "").upper() == direction
    ]
    movers = [row for row in rows if bool(row.get("is_mover"))]
    controls = [row for row in rows if not bool(row.get("is_mover"))]

    base = {
        "version": ENGINE_VERSION,
        "mode": "SHADOW",
        "shadow_only": SHADOW_ONLY,
        "trade_permission": TRADE_PERMISSION,
        "direction": direction,
        "mover_samples": len(movers),
        "control_samples": len(controls),
        "required_mover_samples": min_movers,
        "required_control_samples": min_controls,
    }

    if len(movers) < min_movers or len(controls) < min_controls:
        return {
            **base,
            "status": "INSUFFICIENT_EVIDENCE",
            "features": {},
        }

    stats: dict[str, dict[str, float]] = {}
    raw_weights: dict[str, float] = {}

    for name in feature_names:
        mover_values = [
            value for row in movers
            if (value := _feature_value(row, name)) is not None
        ]
        control_values = [
            value for row in controls
            if (value := _feature_value(row, name)) is not None
        ]

        if len(mover_values) < min_movers or len(control_values) < min_controls:
            continue

        mover_mean = fmean(mover_values)
        control_mean = fmean(control_values)
        delta = mover_mean - control_mean
        pooled_values = mover_values + control_values
        scale = _safe_scale(pooled_values, delta)
        effect = delta / scale
        raw_weight = abs(effect)

        if raw_weight <= 1e-12:
            continue

        stats[name] = {
            "mover_mean": mover_mean,
            "control_mean": control_mean,
            "scale": scale,
            "effect": effect,
            "mover_coverage": len(mover_values) / len(movers),
            "control_coverage": len(control_values) / len(controls),
        }
        raw_weights[name] = raw_weight

    weight_total = sum(raw_weights.values())
    if weight_total <= 0 or not stats:
        return {
            **base,
            "status": "NO_SEPARATING_SIGNAL",
            "features": {},
        }

    for name, raw_weight in raw_weights.items():
        stats[name]["weight"] = raw_weight / weight_total

    return {
        **base,
        "status": "READY_FOR_SHADOW_SCORING",
        "features": stats,
    }


def score_candidate(
    candidate: dict[str, Any],
    model: dict[str, Any],
    *,
    upstream_eligible: bool,
) -> dict[str, Any]:
    """Score similarity without granting or changing trade permission."""
    result = {
        "version": ENGINE_VERSION,
        "mode": "SHADOW",
        "shadow_only": SHADOW_ONLY,
        "trade_permission": TRADE_PERMISSION,
        "symbol": candidate.get("symbol"),
        "direction": model.get("direction"),
        "score": None,
        "feature_coverage": 0.0,
    }

    if not upstream_eligible:
        return {**result, "status": "UPSTREAM_BLOCKED"}

    if model.get("status") != "READY_FOR_SHADOW_SCORING":
        return {**result, "status": "MODEL_NOT_READY"}

    available_weight = 0.0
    weighted_similarity = 0.0
    diagnostics: dict[str, Any] = {}

    for name, stat in model.get("features", {}).items():
        value = _feature_value(candidate, name)
        if value is None:
            continue

        weight = float(stat["weight"])
        scale = max(float(stat["scale"]), 1e-9)
        effect = float(stat["effect"])
        control_mean = float(stat["control_mean"])

        direction_sign = 1.0 if effect >= 0 else -1.0
        aligned_distance = ((value - control_mean) / scale) * direction_sign
        expected_distance = max(abs(effect), 1e-9)
        similarity = max(0.0, min(1.0, aligned_distance / expected_distance))

        available_weight += weight
        weighted_similarity += weight * similarity
        diagnostics[name] = {
            "value": value,
            "similarity": round(similarity, 6),
            "weight": round(weight, 6),
        }

    if available_weight <= 0:
        return {
            **result,
            "status": "NO_SCORABLE_FEATURES",
            "feature_diagnostics": {},
        }

    raw_similarity = weighted_similarity / available_weight
    coverage = max(0.0, min(1.0, available_weight))
    score = 100.0 * raw_similarity * coverage

    return {
        **result,
        "status": "SCORED",
        "score": round(score, 2),
        "feature_coverage": round(coverage, 4),
        "feature_diagnostics": diagnostics,
    }


def rank_candidates(
    candidates: Iterable[dict[str, Any]],
    *,
    long_model: dict[str, Any],
    short_model: dict[str, Any],
    upstream_eligibility_field: str = "upstream_eligible",
) -> list[dict[str, Any]]:
    """Rank LONG/SHORT signature similarity while respecting upstream blocks."""
    ranked: list[dict[str, Any]] = []

    for candidate in candidates:
        eligible = bool(candidate.get(upstream_eligibility_field))
        long_score = score_candidate(candidate, long_model, upstream_eligible=eligible)
        short_score = score_candidate(candidate, short_model, upstream_eligible=eligible)

        scores = [
            result for result in (long_score, short_score)
            if result.get("status") == "SCORED"
            and result.get("score") is not None
        ]
        best = max(scores, key=lambda row: float(row["score"])) if scores else None

        ranked.append({
            "version": ENGINE_VERSION,
            "mode": "SHADOW",
            "shadow_only": SHADOW_ONLY,
            "trade_permission": TRADE_PERMISSION,
            "symbol": candidate.get("symbol"),
            "upstream_eligible": eligible,
            "long_signature_score": long_score.get("score"),
            "short_signature_score": short_score.get("score"),
            "best_direction": best.get("direction") if best else None,
            "best_score": best.get("score") if best else None,
            "status": best.get("status") if best else (
                "UPSTREAM_BLOCKED" if not eligible else "NOT_SCORABLE"
            ),
        })

    def sort_key(row: dict[str, Any]) -> tuple[int, float]:
        score = row.get("best_score")
        return (1 if score is not None else 0, float(score or -1.0))

    ranked.sort(key=sort_key, reverse=True)
    return ranked


def classify_lifecycle(
    move_pct: float,
    *,
    direction: str,
    ignition_abs_pct: float,
    expansion_abs_pct: float,
    extended_abs_pct: float,
) -> str:
    """Classify PRE_MOVER -> IGNITION -> EXPANSION -> EXTENDED.

    Thresholds are caller-owned so this research module cannot silently relax
    production policy.
    """
    if not (0 <= ignition_abs_pct < expansion_abs_pct < extended_abs_pct):
        raise ValueError(
            "lifecycle thresholds must satisfy 0 <= ignition < expansion < extended"
        )

    direction = str(direction).upper()
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")

    progress = float(move_pct) if direction == "LONG" else -float(move_pct)

    if progress < ignition_abs_pct:
        return "PRE_MOVER"
    if progress < expansion_abs_pct:
        return "IGNITION"
    if progress < extended_abs_pct:
        return "EXPANSION"
    return "EXTENDED"


def classify_detection(
    *,
    first_found_at: Any,
    ignition_at: Any,
    traded: bool,
    auditable: bool,
) -> str:
    """Map a realized mover to the canonical discovery audit state."""
    if not auditable:
        return "NOT_AUDITABLE"

    ignition = _parse_time(ignition_at)
    found = _parse_time(first_found_at)

    if ignition is None:
        return "NOT_AUDITABLE"
    if found is None:
        return "NOT_FOUND"
    if found > ignition:
        return "LATE_DETECTED"
    if traded:
        return "FOUND_AND_TRADED"
    return "FOUND_BUT_MISSED"


def reconstruct_lead_snapshots(
    history: Iterable[dict[str, Any]],
    *,
    ignition_at: Any,
    lead_hours: Iterable[int] = (24, 12, 6, 3, 1),
    timestamp_field: str = "captured_at_utc",
) -> dict[str, dict[str, Any] | None]:
    """Reconstruct the latest evidence available at each pre-ignition lead."""
    ignition = _parse_time(ignition_at)
    if ignition is None:
        raise ValueError("ignition_at must be a valid timestamp")

    timed_rows: list[tuple[datetime, dict[str, Any]]] = []
    for row in history:
        captured = _parse_time(row.get(timestamp_field))
        if captured is not None and captured <= ignition:
            timed_rows.append((captured, row))
    timed_rows.sort(key=lambda item: item[0])

    output: dict[str, dict[str, Any] | None] = {}
    for hours in lead_hours:
        if hours < 0:
            raise ValueError("lead_hours cannot contain negative values")
        cutoff = ignition - timedelta(hours=int(hours))
        eligible = [item for item in timed_rows if item[0] <= cutoff]
        output[f"T-{int(hours)}h"] = eligible[-1][1] if eligible else None

    output["IGNITION"] = (
        [item for item in timed_rows if item[0] <= ignition][-1][1]
        if timed_rows
        else None
    )
    return output
