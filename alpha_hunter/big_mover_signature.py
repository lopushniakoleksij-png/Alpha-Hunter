from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from statistics import median
from typing import Any, Iterable


ENGINE_VERSION = "big-mover-signature-shadow-v0.1"
SHADOW_ONLY = True
TRADE_PERMISSION = False

DEFAULT_FEATURES = (
    "volume_ratio",
    "turnover_acceleration",
    "open_interest_change_pct",
    "relative_strength_btc",
    "volatility_pct",
    "compression_score",
    "funding_rate",
    "taker_imbalance",
    "spot_perp_confirmation",
    "distance_to_support_pct",
    "distance_to_resistance_pct",
    "rsi_15m",
    "rsi_1h",
    "rsi_4h",
)

VALID_DIRECTIONS = {"LONG", "SHORT"}
VALID_LABELS = {"MOVER", "CONTROL"}
ENTRY_LIFECYCLES = {"PRE_MOVER", "IGNITION"}


@dataclass(frozen=True)
class FeatureProfile:
    name: str
    mover_median: float
    control_median: float
    mover_scale: float
    control_scale: float
    separation: float
    coverage: float
    weight: float


@dataclass(frozen=True)
class DirectionalSignature:
    version: str
    direction: str
    mover_examples: int
    control_examples: int
    feature_profiles: tuple[FeatureProfile, ...]
    total_weight: float
    edge_state: str = "UNPROVEN"
    shadow_only: bool = SHADOW_ONLY
    trade_permission: bool = TRADE_PERMISSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateScore:
    version: str
    symbol: str
    direction: str
    similarity_score: float | None
    feature_coverage: float
    lifecycle: str
    research_status: str
    directional_move_pct: float | None
    blockers: tuple[str, ...]
    contributions: tuple[dict[str, Any], ...]
    edge_state: str = "UNPROVEN"
    shadow_only: bool = SHADOW_ONLY
    trade_permission: bool = TRADE_PERMISSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _direction(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in VALID_DIRECTIONS else None


def _label(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in VALID_LABELS else None


def _float(value: Any) -> float | None:
    try:
        if value in (None, "", "N/A", "—"):
            return None
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _features(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("features")
    return value if isinstance(value, dict) else {}


def _median(values: list[float]) -> float:
    return float(median(values))


def _mad(values: list[float], centre: float) -> float:
    if not values:
        return 0.0
    return float(median(abs(value - centre) for value in values))


def _robust_scale(values: list[float], centre: float, fallback: float) -> float:
    scale = _mad(values, centre)
    if scale > 0:
        return scale
    if fallback > 0:
        return fallback
    return 0.0


def _valid_training_record(record: dict[str, Any], direction: str) -> bool:
    if _direction(record.get("direction")) != direction:
        return False
    if _label(record.get("label")) not in VALID_LABELS:
        return False
    # A mover profile must never be trained from a post-expansion snapshot.
    # Controls are also required to be time-valid contemporaneous observations.
    return record.get("is_pre_expansion") is True


def build_directional_signature(
    records: Iterable[dict[str, Any]],
    direction: str,
    *,
    feature_names: Iterable[str] = DEFAULT_FEATURES,
) -> DirectionalSignature:
    """Learn a directional pre-mover profile from movers versus false-positive controls.

    Feature weights are not hand-set. They are derived from the observed separation
    between pre-expansion mover examples and contemporaneous controls, discounted by
    feature coverage. The output is research/shadow-only and cannot grant trade
    permission.
    """
    normalized_direction = _direction(direction)
    if normalized_direction is None:
        raise ValueError("direction must be LONG or SHORT")

    valid = [
        record
        for record in records
        if isinstance(record, dict)
        and _valid_training_record(record, normalized_direction)
    ]
    movers = [record for record in valid if _label(record.get("label")) == "MOVER"]
    controls = [record for record in valid if _label(record.get("label")) == "CONTROL"]

    if not movers:
        raise ValueError(f"no pre-expansion {normalized_direction} mover examples")
    if not controls:
        raise ValueError(f"no pre-expansion {normalized_direction} control examples")

    profiles: list[FeatureProfile] = []
    total_examples = len(movers) + len(controls)

    for name in dict.fromkeys(str(item) for item in feature_names if str(item).strip()):
        mover_values = [
            value
            for record in movers
            if (value := _float(_features(record).get(name))) is not None
        ]
        control_values = [
            value
            for record in controls
            if (value := _float(_features(record).get(name))) is not None
        ]
        if not mover_values or not control_values:
            continue

        mover_centre = _median(mover_values)
        control_centre = _median(control_values)
        centre_gap = abs(mover_centre - control_centre)
        mover_scale = _robust_scale(mover_values, mover_centre, centre_gap)
        control_scale = _robust_scale(control_values, control_centre, centre_gap)
        pooled_scale = median(
            value for value in (mover_scale, control_scale, centre_gap) if value > 0
        ) if any(value > 0 for value in (mover_scale, control_scale, centre_gap)) else 0.0

        if pooled_scale <= 0:
            separation = 0.0
        else:
            separation = centre_gap / pooled_scale

        coverage = (len(mover_values) + len(control_values)) / total_examples
        weight = separation * coverage

        if weight <= 0:
            continue

        profiles.append(
            FeatureProfile(
                name=name,
                mover_median=mover_centre,
                control_median=control_centre,
                mover_scale=mover_scale or pooled_scale,
                control_scale=control_scale or pooled_scale,
                separation=separation,
                coverage=coverage,
                weight=weight,
            )
        )

    profiles.sort(key=lambda item: (-item.weight, item.name))
    total_weight = sum(profile.weight for profile in profiles)

    if total_weight <= 0:
        raise ValueError(
            f"{normalized_direction} mover/control sample has no measurable feature separation"
        )

    return DirectionalSignature(
        version=ENGINE_VERSION,
        direction=normalized_direction,
        mover_examples=len(movers),
        control_examples=len(controls),
        feature_profiles=tuple(profiles),
        total_weight=total_weight,
    )


def directional_move_pct(current_move_pct: Any, direction: str) -> float | None:
    move = _float(current_move_pct)
    normalized_direction = _direction(direction)
    if move is None or normalized_direction is None:
        return None
    return move if normalized_direction == "LONG" else -move


def classify_lifecycle(
    current_move_pct: Any,
    direction: str,
    universe_scan_config: dict[str, Any],
) -> tuple[str, float | None, tuple[str, ...]]:
    """Map a live candidate to PRE_MOVER → IGNITION → EXPANSION → EXTENDED.

    Boundaries come from the existing universe-scan configuration. No new trading
    threshold is invented here.
    """
    move = directional_move_pct(current_move_pct, direction)
    ignition_min = _float(universe_scan_config.get("early_ignition_min_abs_change_pct"))
    ignition_max = _float(universe_scan_config.get("early_ignition_max_abs_change_pct"))
    extension_max = _float(universe_scan_config.get("maximum_24h_extension_pct"))
    quiet_max = _float(universe_scan_config.get("quiet_24h_abs_change_max_pct"))

    missing = []
    for name, value in (
        ("EARLY_IGNITION_MIN", ignition_min),
        ("EARLY_IGNITION_MAX", ignition_max),
        ("MAXIMUM_24H_EXTENSION", extension_max),
        ("QUIET_24H_MAX", quiet_max),
    ):
        if value is None:
            missing.append(f"MISSING_CONFIG_{name}")

    if move is None:
        return "PRE_MOVER", None, tuple(missing + ["CURRENT_MOVE_MISSING"])
    if missing:
        return "PRE_MOVER", move, tuple(missing)

    assert ignition_min is not None
    assert ignition_max is not None
    assert extension_max is not None
    assert quiet_max is not None

    blockers: list[str] = []
    if move < -quiet_max:
        blockers.append("CURRENT_MOVE_OPPOSES_DIRECTION")

    if move < ignition_min:
        lifecycle = "PRE_MOVER"
    elif move <= ignition_max:
        lifecycle = "IGNITION"
    elif move <= extension_max:
        lifecycle = "EXPANSION"
    else:
        lifecycle = "EXTENDED"

    return lifecycle, move, tuple(blockers)


def score_candidate(
    record: dict[str, Any],
    signature: DirectionalSignature,
    *,
    universe_scan_config: dict[str, Any],
) -> CandidateScore:
    """Score one live coin against a learned directional mover signature."""
    symbol = str(record.get("symbol") or "").strip().upper()
    blockers: list[str] = []
    if not symbol:
        blockers.append("SYMBOL_MISSING")

    record_direction = _direction(record.get("direction"))
    if record_direction != signature.direction:
        blockers.append("DIRECTION_SIGNATURE_MISMATCH")

    lifecycle, signed_move, lifecycle_blockers = classify_lifecycle(
        record.get("change_24h_pct"),
        signature.direction,
        universe_scan_config,
    )
    blockers.extend(lifecycle_blockers)

    live_features = _features(record)
    weighted_similarity = 0.0
    used_weight = 0.0
    contributions: list[dict[str, Any]] = []

    for profile in signature.feature_profiles:
        value = _float(live_features.get(profile.name))
        if value is None:
            continue

        mover_distance = abs(value - profile.mover_median) / profile.mover_scale
        control_distance = abs(value - profile.control_median) / profile.control_scale
        closeness = 1.0 / (1.0 + mover_distance)
        weighted_similarity += profile.weight * closeness
        used_weight += profile.weight
        contributions.append(
            {
                "feature": profile.name,
                "value": value,
                "mover_median": profile.mover_median,
                "control_median": profile.control_median,
                "mover_distance": round(mover_distance, 6),
                "control_distance": round(control_distance, 6),
                "weight": round(profile.weight, 6),
                "weighted_similarity": round(profile.weight * closeness, 6),
            }
        )

    feature_coverage = used_weight / signature.total_weight if signature.total_weight > 0 else 0.0
    similarity_score = (
        100.0 * weighted_similarity / used_weight
        if used_weight > 0
        else None
    )

    if used_weight <= 0:
        blockers.append("NO_SIGNATURE_FEATURES_AVAILABLE")

    if lifecycle == "EXTENDED":
        blockers.append("EXTENDED_NO_CHASE")
        research_status = "RESEARCH_ONLY"
    elif lifecycle == "EXPANSION":
        research_status = "RETEST_ONLY"
    elif blockers:
        research_status = "WATCH"
    elif lifecycle in ENTRY_LIFECYCLES:
        research_status = "SHADOW_QUEUE"
    else:
        research_status = "WATCH"

    contributions.sort(key=lambda item: (-item["weighted_similarity"], item["feature"]))

    return CandidateScore(
        version=ENGINE_VERSION,
        symbol=symbol,
        direction=signature.direction,
        similarity_score=round(similarity_score, 4) if similarity_score is not None else None,
        feature_coverage=round(feature_coverage, 6),
        lifecycle=lifecycle,
        research_status=research_status,
        directional_move_pct=round(signed_move, 6) if signed_move is not None else None,
        blockers=tuple(dict.fromkeys(blockers)),
        contributions=tuple(contributions),
    )


def rank_candidates(
    records: Iterable[dict[str, Any]],
    signatures: Iterable[DirectionalSignature],
    *,
    universe_scan_config: dict[str, Any],
) -> list[CandidateScore]:
    """Rank LONG and SHORT candidates together without creating trade permission."""
    signature_by_direction = {signature.direction: signature for signature in signatures}
    scored: list[CandidateScore] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        direction = _direction(record.get("direction"))
        signature = signature_by_direction.get(direction or "")
        if signature is None:
            continue
        scored.append(
            score_candidate(
                record,
                signature,
                universe_scan_config=universe_scan_config,
            )
        )

    lifecycle_priority = {
        "IGNITION": 0,
        "PRE_MOVER": 1,
        "EXPANSION": 2,
        "EXTENDED": 3,
    }
    status_priority = {
        "SHADOW_QUEUE": 0,
        "WATCH": 1,
        "RETEST_ONLY": 2,
        "RESEARCH_ONLY": 3,
    }

    scored.sort(
        key=lambda item: (
            status_priority.get(item.research_status, 9),
            lifecycle_priority.get(item.lifecycle, 9),
            -(item.similarity_score if item.similarity_score is not None else -1.0),
            -item.feature_coverage,
            item.symbol,
        )
    )
    return scored
