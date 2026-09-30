from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


def _load_policy() -> tuple[float, float, float]:
    path = Path(__file__).resolve().parents[1] / "config.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = {}
    quality = config.get("candidate_quality", {})
    minimum_rr = float(
        quality.get(
            "minimum_execution_reward_risk",
            config.get("minimum_reward_risk", 5.0),
        )
    )
    maximum_rr = float(quality.get("maximum_action_reward_risk", 25.0))
    maximum_age = float(quality.get("maximum_action_snapshot_age_seconds", 5400.0))
    return minimum_rr, maximum_rr, maximum_age


MINIMUM_EXECUTION_RR, MAXIMUM_ACTION_RR, MAXIMUM_ACTION_SNAPSHOT_AGE_SECONDS = (
    _load_policy()
)
REFERENCE_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_utc(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def snapshot_action_blockers(
    snapshot: dict[str, Any],
    *,
    observed_at: datetime | None = None,
) -> list[str]:
    """Return global fail-closed blockers for a paper-action decision."""
    blockers: list[str] = []
    freshness = snapshot.get("canonical_market_freshness")
    if not isinstance(freshness, dict) or freshness.get("verified") is not True:
        blockers.append("CANONICAL_MARKET_FRESHNESS_UNVERIFIED")

    collected_at = parse_utc(snapshot.get("collected_at_utc"))
    now = observed_at or datetime.now(timezone.utc)
    if collected_at is None:
        blockers.append("SNAPSHOT_TIMESTAMP_MISSING")
    else:
        age_seconds = (now - collected_at).total_seconds()
        if age_seconds < -300:
            blockers.append("SNAPSHOT_TIMESTAMP_IN_FUTURE")
        elif age_seconds > MAXIMUM_ACTION_SNAPSHOT_AGE_SECONDS:
            blockers.append("SNAPSHOT_STALE_FOR_ACTION")
    return blockers


def _price_tick(instrument: dict[str, Any]) -> Decimal | None:
    try:
        places = int(instrument.get("price_place"))
        end_step = Decimal(str(instrument.get("price_end_step")))
    except (TypeError, ValueError, InvalidOperation):
        return None
    if places < 0 or end_step <= 0:
        return None
    tick = end_step * (Decimal(10) ** -places)
    return tick if tick > 0 else None


def normalize_price(value: Any, instrument: dict[str, Any]) -> float | None:
    number = safe_optional_float(value)
    tick = _price_tick(instrument)
    if number is None or tick is None:
        return None
    try:
        decimal_value = Decimal(str(number))
        ticks = (decimal_value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return float(ticks * tick)
    except (InvalidOperation, ValueError, OverflowError):
        return None


def _action_market_row(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("_market_row")
    return source if isinstance(source, dict) else row


def action_quality_blockers(row: dict[str, Any]) -> list[str]:
    """Validate final paper-action geometry, cost floor and venue precision."""
    action = row.get("_action")
    if not isinstance(action, dict):
        return ["ACTION_PAYLOAD_MISSING"]

    direction = str(action.get("direction") or "").upper()
    entry = safe_optional_float(action.get("entry"))
    stop = safe_optional_float(action.get("stop"))
    target = safe_optional_float(action.get("target"))
    declared_rr = safe_optional_float(action.get("rr"))
    blockers: list[str] = []

    if direction not in {"LONG", "SHORT"}:
        blockers.append("DIRECTION_INVALID")
    if None in (entry, stop, target, declared_rr):
        blockers.append("EXECUTION_GEOMETRY_MISSING")
        return blockers
    assert entry is not None and stop is not None and target is not None
    assert declared_rr is not None

    if not all(
        math.isfinite(value) and value > 0
        for value in (entry, stop, target, declared_rr)
    ):
        blockers.append("EXECUTION_GEOMETRY_NON_FINITE")
        return blockers

    if direction == "LONG":
        geometry_ok = stop < entry < target
        risk = entry - stop
        reward = target - entry
    else:
        geometry_ok = target < entry < stop
        risk = stop - entry
        reward = entry - target
    if not geometry_ok or risk <= 0:
        blockers.append("EXECUTION_GEOMETRY_INVALID")
        return blockers

    calculated_rr = reward / risk
    rr_error = abs(declared_rr - calculated_rr) / calculated_rr
    if rr_error > 0.02:
        blockers.append("DECLARED_RR_MISMATCH")
    if calculated_rr > MAXIMUM_ACTION_RR:
        blockers.append("EXECUTION_RR_OUTLIER")

    market = _action_market_row(row)
    instrument = market.get("instrument_constraints")
    if not isinstance(instrument, dict) or _price_tick(instrument) is None:
        blockers.append("BITGET_PRICE_PRECISION_MISSING")
    else:
        normalized = {
            name: normalize_price(action.get(name), instrument)
            for name in ("entry", "stop", "target")
        }
        if any(value is None for value in normalized.values()):
            blockers.append("BITGET_PRICE_NORMALIZATION_FAILED")
        else:
            action.update(normalized)
            entry = normalized["entry"]
            stop = normalized["stop"]
            target = normalized["target"]
            assert entry is not None and stop is not None and target is not None
            normalized_geometry_ok = (
                stop < entry < target
                if direction == "LONG"
                else target < entry < stop
            )
            if not normalized_geometry_ok:
                blockers.append("BITGET_NORMALIZED_GEOMETRY_INVALID")

    bid = safe_optional_float(market.get("bid_price"))
    ask = safe_optional_float(market.get("ask_price"))
    taker_fee_bps = safe_optional_float(
        instrument.get("public_taker_fee_bps")
        if isinstance(instrument, dict)
        else None
    )
    if bid is None or ask is None or bid <= 0 or ask < bid or taker_fee_bps is None:
        blockers.append("EXECUTION_COST_EVIDENCE_MISSING")
    else:
        midpoint = (bid + ask) / 2.0
        spread_pct = (ask - bid) / midpoint * 100.0
        round_trip_fee_pct = 2.0 * taker_fee_bps / 100.0
        cost_floor_pct = spread_pct + round_trip_fee_pct
        risk_pct = risk / entry * 100.0
        action["cost_floor_pct"] = cost_floor_pct
        action["risk_pct"] = risk_pct
        action["cost_to_stop_ratio"] = (
            cost_floor_pct / risk_pct if risk_pct > 0 else None
        )
        if cost_floor_pct >= risk_pct:
            blockers.append("EXECUTION_COST_FLOOR_CONSUMES_STOP")

    return list(dict.fromkeys(blockers))


def _blocked_copy(row: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    blocked = dict(row)
    action = dict(row.get("_action") or {})
    action.update(
        status="BLOCKED",
        label="BLOCKED — SAFETY GATE",
        priority=0,
        reason="Blocked: " + ", ".join(blockers),
        blockers=list(blockers),
        execution_authority=False,
    )
    blocked["_action"] = action
    return blocked


def canonicalize_action_queue(
    rows: list[dict[str, Any]],
    snapshot: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Produce one fail-closed paper decision per symbol without losing evidence."""
    global_blockers = snapshot_action_blockers(snapshot)
    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for row in rows:
        action = row.get("_action")
        if not isinstance(action, dict):
            blocked.append(_blocked_copy(row, ["ACTION_PAYLOAD_MISSING"]))
            continue
        raw_status = str(action.get("status") or "")
        if raw_status == "RETEST_PLAN":
            if global_blockers:
                blocked.append(_blocked_copy(row, list(global_blockers)))
                continue
            action = dict(action)
            action.update(
                status="WAIT_FOR_TRIGGER",
                label="WAIT FOR TRIGGER",
                priority=1,
                execution_authority=False,
            )
            row = dict(row)
            row["_action"] = action
            eligible.append(row)
            continue

        blockers = list(global_blockers)
        blockers.extend(action_quality_blockers(row))
        if blockers:
            blocked.append(_blocked_copy(row, list(dict.fromkeys(blockers))))
            continue

        action = dict(row["_action"])
        if raw_status in {"READY_NOW", "STRATEGY_READY_NOW"}:
            action.update(
                status="EXECUTE_NOW_PAPER",
                label="PAPER — EXECUTE NOW",
                execution_authority=False,
            )
        elif raw_status == "STRATEGY_LIMIT_READY":
            action.update(
                status="PLACE_LIMIT_PAPER",
                label="PAPER — PLACE LIMIT",
                execution_authority=False,
            )
        row = dict(row)
        row["_action"] = action
        eligible.append(row)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        grouped.setdefault(str(row.get("symbol") or ""), []).append(row)

    canonical: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for candidates in grouped.values():
        executable = [
            row
            for row in candidates
            if row["_action"].get("status")
            in {"EXECUTE_NOW_PAPER", "PLACE_LIMIT_PAPER"}
        ]
        directions = {
            str(row["_action"].get("direction") or "").upper()
            for row in executable
        }
        if len(directions) > 1:
            for row in candidates:
                blocked.append(_blocked_copy(row, ["DIRECTION_CONFLICT"]))
            continue

        ranked = sorted(
            candidates,
            key=lambda row: (
                safe_float(row["_action"].get("priority")),
                -safe_float(row["_action"].get("distance_pct")),
                safe_float(row.get("_behaviour")),
                safe_float(row.get("_score")),
            ),
            reverse=True,
        )
        canonical.append(ranked[0])
        for row in ranked[1:]:
            suppressed.append(
                _blocked_copy(row, ["SUPERSEDED_BY_CANONICAL_SYMBOL_DECISION"])
            )

    canonical.sort(
        key=lambda row: (
            safe_float(row["_action"].get("priority")),
            -safe_float(row["_action"].get("distance_pct")),
            safe_float(row.get("_behaviour")),
            safe_float(row.get("_score")),
        ),
        reverse=True,
    )
    blocked.sort(key=lambda row: str(row.get("symbol") or ""))
    return canonical, blocked, suppressed


def execution_checks(row: dict[str, Any]) -> dict[str, bool]:
    setup = row.get("execution_setup", {})
    raw = setup.get("checks", {})
    return {
        "direction": raw.get("direction_aligned") is True,
        "structure": raw.get("structure_valid") is True,
        "momentum": raw.get("momentum_confirmed") is True,
        "participation": raw.get("participation_confirmed") is True,
        "funding": raw.get("funding_not_extreme") is True,
        "integrity": raw.get("data_integrity_min_88") is True,
        "rr": raw.get("rr_minimum_met") is True,
    }


def required_entry_for_rr(
    stop: float,
    target: float,
    minimum_rr: float,
) -> float | None:
    if minimum_rr <= 0 or stop == target:
        return None
    return (target + minimum_rr * stop) / (minimum_rr + 1.0)


def build_money_action(row: dict[str, Any]) -> dict[str, Any]:
    setup = row.get("execution_setup", {})
    checks = execution_checks(row)
    direction = str(setup.get("direction") or "").upper()
    current = safe_optional_float(row.get("last_price"))
    stop = safe_optional_float(setup.get("stop"))
    target = safe_optional_float(setup.get("target"))
    rr = safe_optional_float(setup.get("rr"))
    phase = str(row.get("market_phase") or "")
    timing = str(row.get("opportunity_timing") or "")
    rejections = list(row.get("rejection_reasons") or [])

    if bool(row.get("v7_trade_ready")):
        return {
            "status": "READY_NOW",
            "label": "EXECUTE NOW",
            "priority": 3,
            "direction": direction,
            "entry": current,
            "stop": stop,
            "target": target,
            "rr": rr,
            "minimum_rr": MINIMUM_EXECUTION_RR,
            "distance_pct": 0.0,
            "reason": "All existing V7 execution gates passed.",
            "cancel": "Cancel if structure invalidates or execution evidence changes before entry.",
        }

    core_without_rr = all(
        checks[name]
        for name in (
            "direction",
            "structure",
            "momentum",
            "participation",
            "funding",
            "integrity",
        )
    )
    allowed_retest_phase = phase in {
        "ACCUMULATION",
        "COMPRESSION",
        "RECOVERY",
        "IGNITION",
    }
    if (
        core_without_rr
        and not checks["rr"]
        and allowed_retest_phase
        and direction in {"LONG", "SHORT"}
        and current is not None
        and stop is not None
        and target is not None
    ):
        required = required_entry_for_rr(stop, target, MINIMUM_EXECUTION_RR)
        geometry_ok = False
        if required is not None:
            if direction == "LONG":
                geometry_ok = stop < required < current < target
            else:
                geometry_ok = target < current < required < stop
        if geometry_ok and required is not None:
            distance_pct = abs(required - current) / current * 100 if current else None
            return {
                "status": "RETEST_PLAN",
                "label": "BEST RETEST / LIMIT ZONE",
                "priority": 2,
                "direction": direction,
                "entry": required,
                "stop": stop,
                "target": target,
                "rr": MINIMUM_EXECUTION_RR,
                "minimum_rr": MINIMUM_EXECUTION_RR,
                "distance_pct": distance_pct,
                "reason": (
                    "Signal quality passes, but the current price is too late. "
                    "This is the nearest price that restores the configured minimum R:R."
                ),
                "cancel": (
                    "Do not use the zone if direction, momentum or participation has "
                    "failed by retest, or if structural invalidation is reached first."
                ),
            }

    failed = [name for name, passed in checks.items() if not passed]
    reason = "Blocked: " + ", ".join(failed) if failed else "No executable geometry"
    if rejections:
        reason += ". Quality: " + ", ".join(rejections)
    return {
        "status": "RESEARCH_ONLY",
        "label": "RESEARCH / WATCH",
        "priority": 0,
        "direction": direction or None,
        "entry": None,
        "stop": stop,
        "target": target,
        "rr": rr,
        "minimum_rr": MINIMUM_EXECUTION_RR,
        "distance_pct": None,
        "reason": reason,
        "cancel": None,
        "phase": phase,
        "timing": timing,
    }


def build_strategy_money_action(strategy: dict[str, Any]) -> dict[str, Any] | None:
    if str(strategy.get("status") or "") != "SHADOW_CANDIDATE":
        return None
    proposed = str(
        strategy.get("action") or strategy.get("proposed_action") or ""
    ).upper()
    direction = str(strategy.get("direction") or "").upper()
    entry = safe_optional_float(strategy.get("entry"))
    stop = safe_optional_float(strategy.get("stop"))
    target = safe_optional_float(strategy.get("target"))
    rr = safe_optional_float(strategy.get("rr"))
    if (
        proposed not in {"EXECUTE_NOW", "PLACE_LIMIT"}
        or direction not in {"LONG", "SHORT"}
        or entry is None
        or stop is None
        or target is None
        or rr is None
        or rr < MINIMUM_EXECUTION_RR
    ):
        return None
    geometry_ok = stop < entry < target if direction == "LONG" else target < entry < stop
    if not geometry_ok:
        return None
    execute_now = proposed == "EXECUTE_NOW"
    return {
        "status": "STRATEGY_READY_NOW" if execute_now else "STRATEGY_LIMIT_READY",
        "label": "READY SETUP — EXECUTE NOW" if execute_now else "READY SETUP — PLACE LIMIT",
        "priority": 4 if execute_now else 3,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": rr,
        "minimum_rr": MINIMUM_EXECUTION_RR,
        "distance_pct": safe_optional_float(strategy.get("distance_to_entry_pct")) or 0.0,
        "reason": (
            f"{strategy.get('strategy_id','S?')} "
            f"{strategy.get('strategy_name','strategy')} passed its signal, shared "
            "safety/data gates, valid geometry and the configured 5R minimum. "
            "Decision support only; order authority remains disabled."
        ),
        "cancel": (
            "Cancel if direction, participation, liquidity/funding safety, or "
            "structural invalidation changes before entry."
        ),
        "strategy_id": strategy.get("strategy_id"),
        "strategy_name": strategy.get("strategy_name"),
        "execution_authority": False,
    }


def build_action_queue_rows(
    snapshot: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the same final queue used by the dashboard for persistence jobs."""
    symbols = [
        dict(row)
        for row in snapshot.get("symbols", [])
        if isinstance(row, dict) and "error" not in row
        and row.get("symbol") not in REFERENCE_SYMBOLS
    ]
    strategy_ready: list[dict[str, Any]] = []
    actionable: list[dict[str, Any]] = []
    for row in symbols:
        intel = row.get("intelligence", {})
        row["_score"] = safe_float(intel.get("huge_rr_score")) if isinstance(intel, dict) else 0.0
        row["_behaviour"] = safe_float(row.get("behaviour_score"))
        row["_action"] = build_money_action(row)
        if row["_action"]["priority"] > 0:
            actionable.append(row)
        engine = row.get("multi_strategy_engine", {})
        strategies = engine.get("strategies", []) if isinstance(engine, dict) else []
        for strategy in strategies:
            if not isinstance(strategy, dict):
                continue
            action = build_strategy_money_action(strategy)
            if action is None:
                continue
            strategy_ready.append(
                {
                    "symbol": row.get("symbol"),
                    "last_price": row.get("last_price"),
                    "state": strategy.get("status"),
                    "_strategy": True,
                    "_score": safe_float(strategy.get("signal_score")),
                    "_behaviour": 0.0,
                    "_action": action,
                    "_strategy_payload": dict(strategy),
                    "_market_row": row,
                }
            )
    return canonicalize_action_queue(actionable + strategy_ready, snapshot)
