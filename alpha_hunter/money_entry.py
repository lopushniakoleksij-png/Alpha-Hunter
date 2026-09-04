from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


ENGINE_VERSION = "money-entry-shadow-v1"
SHADOW_TRADE_PERMISSION = False


@dataclass(frozen=True)
class EntryDecision:
    version: str
    stage: str
    direction: str | None
    eligible: bool
    blockers: list[str]
    evidence: dict[str, Any]
    shadow_trade_permission: bool = SHADOW_TRADE_PERMISSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _direction(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in {"LONG", "SHORT"} else None


def _aligned(value: Any, direction: str | None) -> bool:
    if direction is None:
        return False
    text = str(value or "").strip().upper()
    aliases = {
        "BULL": "LONG",
        "BULLISH": "LONG",
        "LONG": "LONG",
        "BEAR": "SHORT",
        "BEARISH": "SHORT",
        "SHORT": "SHORT",
    }
    return aliases.get(text) == direction


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _required_thresholds(config: dict[str, Any]) -> tuple[dict[str, float] | None, list[str]]:
    section = config.get("money_entry_shadow", {})
    required = (
        "max_t0_stop_distance_pct",
        "min_t0_remaining_r",
        "min_t1_remaining_r",
        "min_t2_remaining_r",
    )
    missing = [name for name in required if _float(section.get(name)) is None]
    if missing:
        return None, [f"MISSING_THRESHOLD_{name.upper()}" for name in missing]
    return {name: float(section[name]) for name in required}, []


def build_money_entry_shadow(record: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Classify the earliest evidence-supported entry stage without granting trade permission.

    T0 is intentionally earlier than full READY, but only when downside is objectively
    controlled by a nearby structural invalidation. T1 adds acceptance/trigger evidence.
    T2 adds expansion confirmation. All numeric thresholds must be supplied by config;
    this module refuses to invent them.
    """
    direction = _direction(record.get("direction") or record.get("trade_direction"))
    thresholds, threshold_blockers = _required_thresholds(config)

    evidence = {
        "parent_12h": record.get("direction_12h"),
        "parent_1d": record.get("direction_1d"),
        "timing_1h": record.get("direction_1h"),
        "lifecycle": record.get("lifecycle_stage") or record.get("opportunity_timing"),
        "liquidity_ok": _bool(record.get("liquidity_ok")),
        "participation_emerging": _bool(record.get("participation_emerging")),
        "participation_confirmed": _bool(record.get("participation_confirmed")),
        "acceptance_confirmed": _bool(record.get("acceptance_confirmed")),
        "trigger_confirmed": _bool(record.get("trigger_confirmed")),
        "expansion_confirmed": _bool(record.get("expansion_confirmed")),
        "structural_invalidation_valid": _bool(record.get("structural_invalidation_valid")),
        "stop_distance_pct": _float(record.get("stop_distance_pct")),
        "remaining_r": _float(record.get("remaining_r")),
        "open_position_conflict": _bool(record.get("open_position_conflict")),
    }

    blockers: list[str] = list(threshold_blockers)
    if direction is None:
        blockers.append("DIRECTION_MISSING")
    if not _aligned(record.get("direction_12h"), direction):
        blockers.append("PARENT_12H_NOT_ALIGNED")
    if not _aligned(record.get("direction_1d"), direction):
        blockers.append("PARENT_1D_NOT_ALIGNED")
    if evidence["liquidity_ok"] is not True:
        blockers.append("LIQUIDITY_NOT_VERIFIED")
    if evidence["participation_emerging"] is not True and evidence["participation_confirmed"] is not True:
        blockers.append("PARTICIPATION_NOT_EMERGING")
    if evidence["structural_invalidation_valid"] is not True:
        blockers.append("STRUCTURAL_INVALIDATION_NOT_VALID")
    if evidence["open_position_conflict"] is True:
        blockers.append("OPEN_POSITION_CONFLICT")

    stop_distance = evidence["stop_distance_pct"]
    remaining_r = evidence["remaining_r"]
    if stop_distance is None:
        blockers.append("STOP_DISTANCE_MISSING")
    if remaining_r is None:
        blockers.append("REMAINING_R_MISSING")

    if thresholds is None:
        return EntryDecision(
            ENGINE_VERSION,
            "DATA_INSUFFICIENT",
            direction,
            False,
            blockers,
            evidence,
        ).to_dict()

    if stop_distance is not None and stop_distance > thresholds["max_t0_stop_distance_pct"]:
        blockers.append("T0_STOP_GEOMETRY_TOO_WIDE")
    if remaining_r is not None and remaining_r < thresholds["min_t0_remaining_r"]:
        blockers.append("T0_REMAINING_R_TOO_LOW")

    if blockers:
        return EntryDecision(
            ENGINE_VERSION,
            "NO_T0",
            direction,
            False,
            blockers,
            evidence,
        ).to_dict()

    stage = "T0_CONTROLLED_ENTRY"

    t1_ready = (
        evidence["acceptance_confirmed"] is True
        and evidence["trigger_confirmed"] is True
        and evidence["participation_confirmed"] is True
        and remaining_r is not None
        and remaining_r >= thresholds["min_t1_remaining_r"]
    )
    if t1_ready:
        stage = "T1_ACCEPTANCE_CONFIRMED"

    t2_ready = (
        t1_ready
        and evidence["expansion_confirmed"] is True
        and remaining_r is not None
        and remaining_r >= thresholds["min_t2_remaining_r"]
    )
    if t2_ready:
        stage = "T2_EXPANSION_CONFIRMED"

    return EntryDecision(
        ENGINE_VERSION,
        stage,
        direction,
        True,
        [],
        evidence,
    ).to_dict()


def confirmation_tax(early_rr: Any, confirmed_rr: Any) -> dict[str, Any]:
    """Measure R lost (positive) or gained (negative) while waiting for confirmation."""
    early = _float(early_rr)
    confirmed = _float(confirmed_rr)
    if early is None or confirmed is None:
        return {"status": "DATA_INSUFFICIENT", "confirmation_tax_r": None}
    return {
        "status": "MEASURED",
        "early_rr": early,
        "confirmed_rr": confirmed,
        "confirmation_tax_r": early - confirmed,
    }


def compare_entry_outcomes(early_net_r: Any, confirmed_net_r: Any) -> dict[str, Any]:
    """Compare realized/shadow net R on the same future path; never infer expectancy."""
    early = _float(early_net_r)
    confirmed = _float(confirmed_net_r)
    if early is None or confirmed is None:
        return {
            "status": "DATA_INSUFFICIENT",
            "early_net_r": early,
            "confirmed_net_r": confirmed,
            "delta_net_r": None,
            "expectancy_claim_permitted": False,
        }
    return {
        "status": "MEASURED",
        "early_net_r": early,
        "confirmed_net_r": confirmed,
        "delta_net_r": early - confirmed,
        "expectancy_claim_permitted": False,
    }
