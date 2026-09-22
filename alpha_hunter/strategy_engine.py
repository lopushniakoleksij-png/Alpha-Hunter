from __future__ import annotations

from typing import Any


ENGINE_VERSION = "0.1"
STRATEGY_CATALOG: tuple[tuple[str, str], ...] = (
    ("S1", "Early Momentum / Expansion"),
    ("S2", "Breakout + Retest"),
    ("S3", "Trend Pullback"),
    ("S4", "Relative Strength / Weakness"),
    ("S5", "Volatility Compression"),
    ("S6", "Liquidity Sweep / Reclaim"),
    ("S7", "Acceptance / Absorption"),
    ("S8", "Mean-Reversion Edge"),
    ("S9", "Catalyst / News Momentum"),
    ("S10", "Risk-Regime / Beta"),
)

ACTION_PRIORITY = {
    "EXECUTE_NOW": 4,
    "PLACE_LIMIT": 3,
    "WAIT_FOR_TRIGGER": 2,
    "NO_SAFE_TRADE": 0,
}


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _tf(record: dict[str, Any], timeframe: str) -> dict[str, Any]:
    value = record.get("timeframes", {}).get(timeframe, {})
    return value if isinstance(value, dict) else {}


def _indicators(record: dict[str, Any], timeframe: str = "1H") -> dict[str, Any]:
    value = _tf(record, timeframe).get("indicators", {})
    return value if isinstance(value, dict) else {}


def _trend(record: dict[str, Any], timeframe: str) -> str:
    return str(_tf(record, timeframe).get("trend") or "DATA_UNAVAILABLE").upper()


def _direction_from_trends(record: dict[str, Any]) -> str | None:
    one_hour = _trend(record, "1H")
    four_hour = _trend(record, "4H")
    fifteen = _trend(record, "15m")
    if one_hour == "BULLISH" and four_hour == "BULLISH":
        return "LONG"
    if one_hour == "BEARISH" and four_hour == "BEARISH":
        return "SHORT"
    if one_hour == "BULLISH" and fifteen == "BULLISH":
        return "LONG"
    if one_hour == "BEARISH" and fifteen == "BEARISH":
        return "SHORT"
    return None


def _structural_stop(record: dict[str, Any], direction: str) -> float | None:
    one_hour = _tf(record, "1H")
    if direction == "LONG":
        return _float(one_hour.get("support") or record.get("support"))
    if direction == "SHORT":
        return _float(one_hour.get("resistance") or record.get("resistance"))
    return None


def _structural_target(record: dict[str, Any], direction: str, entry: float | None) -> float | None:
    if entry is None:
        return None
    one_hour = _tf(record, "1H")
    four_hour = _tf(record, "4H")
    candidates: list[float] = []
    if direction == "LONG":
        for raw in (
            one_hour.get("resistance"),
            four_hour.get("resistance"),
            record.get("resistance"),
        ):
            value = _float(raw)
            if value is not None and value > entry:
                candidates.append(value)
        return max(candidates) if candidates else None
    if direction == "SHORT":
        for raw in (
            one_hour.get("support"),
            four_hour.get("support"),
            record.get("support"),
        ):
            value = _float(raw)
            if value is not None and value < entry:
                candidates.append(value)
        return min(candidates) if candidates else None
    return None


def _geometry(direction: str | None, entry: float | None, stop: float | None, target: float | None) -> dict[str, Any]:
    output = {
        "valid": False,
        "risk": None,
        "reward": None,
        "rr": None,
    }
    if direction not in {"LONG", "SHORT"} or None in (entry, stop, target):
        return output
    assert entry is not None and stop is not None and target is not None
    if direction == "LONG":
        valid = stop < entry < target
        risk = entry - stop
        reward = target - entry
    else:
        valid = target < entry < stop
        risk = stop - entry
        reward = entry - target
    rr = reward / risk if valid and risk > 0 else None
    output.update(valid=valid, risk=risk if valid else None, reward=reward if valid else None, rr=rr)
    return output


def _shared_gates(record: dict[str, Any], config: dict[str, Any]) -> dict[str, bool]:
    settings = config.get("multi_strategy_engine", {})
    minimum_integrity = float(
        settings.get(
            "minimum_data_integrity",
            config.get("candidate_quality", {}).get("minimum_data_integrity", 88),
        )
    )
    maximum_spread = float(settings.get("maximum_spread_pct", 0.15))
    integrity = _float(record.get("data_integrity_score"))
    spread = _float(record.get("behaviour", {}).get("spread_pct"))
    funding_extreme = bool(record.get("funding_history", {}).get("extreme", False))
    price = _float(record.get("last_price"))
    return {
        "price_available": price is not None and price > 0,
        "data_integrity": integrity is not None and integrity >= minimum_integrity,
        "funding_not_extreme": not funding_extreme,
        "liquidity_spread": spread is None or spread <= maximum_spread,
    }


def _base_result(strategy_id: str, strategy_name: str) -> dict[str, Any]:
    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "engine_version": ENGINE_VERSION,
        "status": "NO_SETUP",
        "action": "NO_SAFE_TRADE",
        "proposed_action": "NO_SAFE_TRADE",
        "direction": None,
        "signal_score": 0.0,
        "score_is_calibrated": False,
        "entry": None,
        "stop": None,
        "target": None,
        "risk": None,
        "reward": None,
        "rr": None,
        "distance_to_entry_pct": None,
        "geometry_valid": False,
        "evidence": {},
        "checks": {},
        "reasons": [],
        "shadow_only": True,
        "trade_permission": False,
        "production_permission": False,
        "considered_sides": ["LONG", "SHORT"],
    }


def _data_insufficient(
    strategy_id: str,
    strategy_name: str,
    reason: str,
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = _base_result(strategy_id, strategy_name)
    result["status"] = "DATA_INSUFFICIENT"
    result["reasons"] = [reason]
    result["evidence"] = evidence or {}
    return result


def _finish(
    *,
    record: dict[str, Any],
    config: dict[str, Any],
    strategy_id: str,
    strategy_name: str,
    direction: str | None,
    signal: bool,
    signal_score: float,
    action: str,
    entry: float | None,
    stop: float | None,
    target: float | None,
    evidence: dict[str, Any],
    reasons: list[str],
    extra_checks: dict[str, bool] | None = None,
) -> dict[str, Any]:
    result = _base_result(strategy_id, strategy_name)
    geometry = _geometry(direction, entry, stop, target)
    shared = _shared_gates(record, config)
    minimum_rr = float(
        config.get("multi_strategy_engine", {}).get(
            "minimum_shadow_reward_risk",
            config.get("candidate_quality", {}).get(
                "minimum_execution_reward_risk",
                config.get("minimum_reward_risk", 5.0),
            ),
        )
    )
    minimum_signal = float(
        config.get("multi_strategy_engine", {}).get("minimum_signal_score", 6.5)
    )
    rr_ok = bool(geometry["rr"] is not None and geometry["rr"] >= minimum_rr)
    checks = {
        **shared,
        "signal_present": bool(signal),
        "signal_score_minimum": signal_score >= minimum_signal,
        "geometry_valid": bool(geometry["valid"]),
        "rr_minimum_met": rr_ok,
    }
    if extra_checks:
        checks.update(extra_checks)

    current = _float(record.get("last_price"))
    distance = None
    if current and entry:
        distance = abs(entry - current) / current * 100

    proposed_action = (
        action
        if action in ACTION_PRIORITY
        else "NO_SAFE_TRADE"
    )

    result.update(
        direction=direction,
        signal_score=round(max(0.0, min(10.0, signal_score)), 2),
        action="NO_SAFE_TRADE",
        proposed_action=proposed_action,
        entry=entry,
        stop=stop,
        target=target,
        risk=geometry["risk"],
        reward=geometry["reward"],
        rr=geometry["rr"],
        distance_to_entry_pct=distance,
        geometry_valid=bool(geometry["valid"]),
        evidence=evidence,
        checks=checks,
        reasons=list(reasons),
    )

    all_shared = all(shared.values())
    candidate = (
        signal
        and signal_score >= minimum_signal
        and all_shared
        and geometry["valid"]
        and rr_ok
        and proposed_action in {"EXECUTE_NOW", "PLACE_LIMIT"}
        and all(value for key, value in checks.items() if key not in {"rr_minimum_met"})
    )

    if candidate:
        result["status"] = "SHADOW_CANDIDATE"
        result["action"] = proposed_action
    elif signal:
        result["status"] = "WATCH"
        result["action"] = "WAIT_FOR_TRIGGER"
    else:
        result["status"] = "NO_SETUP"
        result["action"] = "NO_SAFE_TRADE"

    if not geometry["valid"] and signal:
        result["reasons"].append("No valid strategy-specific stop/target geometry")
    elif geometry["valid"] and not rr_ok and signal:
        result["reasons"].append(
            f"Shadow R:R {geometry['rr']:.2f} is below configured minimum {minimum_rr:.2f}"
        )

    failed_shared = [name for name, passed in shared.items() if not passed]
    if failed_shared:
        result["reasons"].append("Shared safety/data gates failed: " + ", ".join(failed_shared))

    return result


def _s1_early_momentum(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    del previous
    strategy_id, strategy_name = STRATEGY_CATALOG[0]
    direction = _direction_from_trends(record)
    price = _float(record.get("last_price"))
    phase = str(record.get("market_phase") or "")
    timing = str(record.get("opportunity_timing") or "")
    indicators = _indicators(record)
    volume = indicators.get("volume_anomaly", {}) if isinstance(indicators.get("volume_anomaly"), dict) else {}
    volume_ratio = _float(volume.get("ratio")) or 0.0
    macd_hist = _float(indicators.get("macd", {}).get("histogram")) if isinstance(indicators.get("macd"), dict) else None
    momentum_ok = (
        direction == "LONG" and macd_hist is not None and macd_hist > 0
    ) or (
        direction == "SHORT" and macd_hist is not None and macd_hist < 0
    )
    phase_ok = phase in {"IGNITION", "RECOVERY"}
    timing_ok = timing in {"EARLY", "FAIR"}
    participation_ok = volume_ratio >= 1.25
    signal = bool(direction and phase_ok and timing_ok and momentum_ok and participation_ok)
    score = (
        (2.0 if direction else 0.0)
        + (2.0 if phase_ok else 0.0)
        + (1.5 if timing_ok else 0.0)
        + (2.0 if momentum_ok else 0.0)
        + (2.5 if participation_ok else min(2.0, volume_ratio))
    )
    entry = price
    stop = _structural_stop(record, direction or "")
    target = _structural_target(record, direction or "", entry)
    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=signal,
        signal_score=score,
        action="EXECUTE_NOW" if signal and timing == "EARLY" else "WAIT_FOR_TRIGGER",
        entry=entry,
        stop=stop,
        target=target,
        evidence={
            "phase": phase,
            "timing": timing,
            "volume_ratio": volume_ratio,
            "macd_histogram": macd_hist,
            "trend_15m": _trend(record, "15m"),
            "trend_1h": _trend(record, "1H"),
            "trend_4h": _trend(record, "4H"),
        },
        reasons=[] if signal else ["Momentum/phase/participation conditions are not simultaneously present"],
        extra_checks={
            "phase": phase_ok,
            "timing": timing_ok,
            "momentum": momentum_ok,
            "participation": participation_ok,
        },
    )


def _s2_breakout_retest(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    strategy_id, strategy_name = STRATEGY_CATALOG[1]
    price = _float(record.get("last_price"))
    atr = _float(_indicators(record).get("atr_14"))
    long_trigger = _float(record.get("breakout_trigger"))
    previous_support = _float(previous.get("support")) if previous else None
    short_trigger = previous_support or _float(_tf(record, "1H").get("support"))
    direction = None
    trigger = None
    trend_1h = _trend(record, "1H")
    trend_15m = _trend(record, "15m")
    if price is not None and long_trigger is not None and trend_1h == "BULLISH" and trend_15m == "BULLISH":
        if price >= long_trigger:
            direction = "LONG"
            trigger = long_trigger
    if (
        direction is None
        and price is not None
        and short_trigger is not None
        and trend_1h == "BEARISH"
        and trend_15m == "BEARISH"
        and price <= short_trigger
    ):
        direction = "SHORT"
        trigger = short_trigger

    if price is None or trigger is None or direction is None:
        return _finish(
            record=record,
            config=config,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            direction=direction,
            signal=False,
            signal_score=0.0,
            action="NO_SAFE_TRADE",
            entry=None,
            stop=None,
            target=None,
            evidence={
                "long_breakout_trigger": long_trigger,
                "short_breakdown_trigger": short_trigger,
                "trend_15m": trend_15m,
                "trend_1h": trend_1h,
            },
            reasons=["No confirmed breakout/breakdown aligned with the short-term trend"],
        )

    retest_distance = abs(price - trigger) / price * 100 if price else None
    atr_value = atr or abs(price - trigger) or (price * 0.01)
    if direction == "LONG":
        stop = trigger - atr_value
        structural = _structural_stop(record, direction)
        if structural is not None:
            stop = max(structural, stop) if structural < trigger else stop
    else:
        stop = trigger + atr_value
        structural = _structural_stop(record, direction)
        if structural is not None:
            stop = min(structural, stop) if structural > trigger else stop
    target = _structural_target(record, direction, trigger)
    signal = bool(retest_distance is not None and retest_distance <= 3.0)
    score = 5.0 + (2.0 if signal else 0.0) + (1.5 if atr is not None else 0.0) + 1.5
    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=signal,
        signal_score=score,
        action="PLACE_LIMIT",
        entry=trigger,
        stop=stop,
        target=target,
        evidence={
            "trigger": trigger,
            "retest_distance_pct": retest_distance,
            "atr_14": atr,
            "geometry_basis": "breakout_or_breakdown_trigger_plus_atr_invalidation_to_structural_target",
        },
        reasons=[] if signal else ["Price is too far from the breakout/retest zone"],
        extra_checks={"retest_distance": bool(signal)},
    )


def _s3_trend_pullback(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    del previous
    strategy_id, strategy_name = STRATEGY_CATALOG[2]
    direction = _direction_from_trends(record)
    price = _float(record.get("last_price"))
    ema21 = _float(_indicators(record).get("ema_21"))
    atr = _float(_indicators(record).get("atr_14"))
    if direction is None or price is None or ema21 is None:
        return _data_insufficient(
            strategy_id,
            strategy_name,
            "Trend pullback requires aligned direction, current price and 1H EMA21",
            evidence={"direction": direction, "price": price, "ema_21": ema21},
        )
    correct_side = (direction == "LONG" and price >= ema21) or (direction == "SHORT" and price <= ema21)
    distance_abs = abs(price - ema21)
    distance_atr = distance_abs / atr if atr and atr > 0 else None
    within_pullback_range = distance_atr is not None and distance_atr <= 2.5
    phase = str(record.get("market_phase") or "")
    phase_ok = phase not in {"DISTRIBUTION_RISK", "EXPANSION_MANAGEMENT", "FOMO", "EXTENDED"}
    signal = bool(correct_side and within_pullback_range and phase_ok)
    score = 3.0 + (2.0 if correct_side else 0.0) + (2.5 if within_pullback_range else 0.0) + (2.5 if phase_ok else 0.0)
    stop = _structural_stop(record, direction)
    target = _structural_target(record, direction, ema21)
    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=signal,
        signal_score=score,
        action="PLACE_LIMIT",
        entry=ema21,
        stop=stop,
        target=target,
        evidence={
            "ema_21": ema21,
            "atr_14": atr,
            "distance_to_ema21_atr": distance_atr,
            "phase": phase,
            "trend_1h": _trend(record, "1H"),
            "trend_4h": _trend(record, "4H"),
        },
        reasons=[] if signal else ["Price/EMA pullback geometry or phase is not suitable"],
        extra_checks={
            "correct_trend_side": correct_side,
            "within_2_5_atr": within_pullback_range,
            "phase": phase_ok,
        },
    )


def _s4_relative_strength(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    del previous
    strategy_id, strategy_name = STRATEGY_CATALOG[3]
    behaviour = record.get("behaviour", {})
    rs = _float(behaviour.get("relative_strength_vs_btc_pct"))
    acceleration = _float(behaviour.get("relative_strength_acceleration"))
    price = _float(record.get("last_price"))
    direction = None
    if rs is not None:
        if rs >= 2.0 and _trend(record, "1H") == "BULLISH":
            direction = "LONG"
        elif rs <= -2.0 and _trend(record, "1H") == "BEARISH":
            direction = "SHORT"
    accel_ok = bool(
        direction == "LONG" and acceleration is not None and acceleration >= 0
        or direction == "SHORT" and acceleration is not None and acceleration <= 0
    )
    signal = bool(direction and accel_ok)
    score = min(7.5, abs(rs or 0.0)) + (2.5 if accel_ok else 0.0)
    stop = _structural_stop(record, direction or "")
    target = _structural_target(record, direction or "", price)
    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=signal,
        signal_score=score,
        action="EXECUTE_NOW" if signal else "WAIT_FOR_TRIGGER",
        entry=price,
        stop=stop,
        target=target,
        evidence={
            "relative_strength_vs_btc_pct": rs,
            "relative_strength_acceleration": acceleration,
            "trend_1h": _trend(record, "1H"),
            "btc_change_24h_pct": _float(record.get("btc_change_24h_pct")),
        },
        reasons=[] if signal else ["Relative strength/weakness and acceleration are not aligned"],
        extra_checks={"relative_strength_direction": direction is not None, "acceleration": accel_ok},
    )


def _s5_compression(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    del previous
    strategy_id, strategy_name = STRATEGY_CATALOG[4]
    compression = _tf(record, "1H").get("compression", {})
    compression_state = str(compression.get("state") or "")
    compression_score = _float(compression.get("score")) or 0.0
    direction = _direction_from_trends(record)
    price = _float(record.get("last_price"))
    volume_state = str(_indicators(record).get("volume_anomaly", {}).get("state") or "")
    breakout = _float(record.get("breakout_trigger"))
    support = _float(_tf(record, "1H").get("support"))
    compressed = compression_state in {"STRONG", "MODERATE"}
    trigger_crossed = False
    entry = None
    if direction == "LONG" and breakout is not None:
        entry = breakout
        trigger_crossed = bool(price is not None and price >= breakout and volume_state in {"ELEVATED", "HIGH"})
    elif direction == "SHORT" and support is not None:
        entry = support
        trigger_crossed = bool(price is not None and price <= support and volume_state in {"ELEVATED", "HIGH"})
    signal = bool(compressed and direction)
    action = "EXECUTE_NOW" if signal and trigger_crossed else "WAIT_FOR_TRIGGER"
    score = min(6.0, compression_score * 0.6) + (2.0 if direction else 0.0) + (2.0 if trigger_crossed else 0.0)
    stop = _structural_stop(record, direction or "")
    target = _structural_target(record, direction or "", entry)
    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=signal,
        signal_score=score,
        action=action,
        entry=entry,
        stop=stop,
        target=target,
        evidence={
            "compression_state": compression_state,
            "compression_score": compression_score,
            "volume_state": volume_state,
            "trigger_crossed_with_participation": trigger_crossed,
            "trigger": entry,
        },
        reasons=[] if signal else ["No directional compression setup"],
        extra_checks={"compression": compressed, "direction": direction is not None},
    )


def _s6_sweep_reclaim(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    strategy_id, strategy_name = STRATEGY_CATALOG[5]
    latest = _tf(record, "1H").get("latest_candle")
    if not isinstance(latest, dict) or not previous:
        return _data_insufficient(
            strategy_id,
            strategy_name,
            "Sweep/reclaim requires a current 1H candle plus the previous canonical snapshot levels",
        )
    prev_support = _float(previous.get("support"))
    prev_resistance = _float(previous.get("resistance"))
    low = _float(latest.get("low"))
    high = _float(latest.get("high"))
    close = _float(latest.get("close"))
    price = _float(record.get("last_price"))
    if None in (low, high, close, price):
        return _data_insufficient(strategy_id, strategy_name, "Sweep/reclaim candle fields are incomplete")
    direction = None
    swept_level = None
    if prev_support is not None and low < prev_support < close:
        direction = "LONG"
        swept_level = prev_support
    elif prev_resistance is not None and high > prev_resistance > close:
        direction = "SHORT"
        swept_level = prev_resistance
    volume_state = str(_indicators(record).get("volume_anomaly", {}).get("state") or "")
    participation = volume_state in {"ELEVATED", "HIGH"}
    signal = bool(direction and participation)
    score = (6.0 if direction else 0.0) + (4.0 if participation else 0.0)
    stop = low if direction == "LONG" else high if direction == "SHORT" else None
    target = _structural_target(record, direction or "", price)
    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=signal,
        signal_score=score,
        action="EXECUTE_NOW" if signal else "WAIT_FOR_TRIGGER",
        entry=price,
        stop=stop,
        target=target,
        evidence={
            "previous_support": prev_support,
            "previous_resistance": prev_resistance,
            "latest_low": low,
            "latest_high": high,
            "latest_close": close,
            "swept_level": swept_level,
            "volume_state": volume_state,
        },
        reasons=[] if signal else ["No participation-confirmed sweep and reclaim of a previous canonical level"],
        extra_checks={"sweep_reclaim": direction is not None, "participation": participation},
    )


def _s7_acceptance_absorption(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    strategy_id, strategy_name = STRATEGY_CATALOG[6]
    latest = _tf(record, "1H").get("latest_candle")
    if not previous or not isinstance(latest, dict):
        return _data_insufficient(
            strategy_id,
            strategy_name,
            "Acceptance requires the previous canonical levels plus a current 1H candle",
        )

    micro = record.get("microstructure")
    if not isinstance(micro, dict) or micro.get("status") != "COMPLETE":
        return _data_insufficient(
            strategy_id,
            strategy_name,
            "Canonical Bitget order-book and recent-trade evidence is incomplete; acceptance/absorption cannot be assessed",
            evidence={
                "microstructure_status": (
                    micro.get("status")
                    if isinstance(micro, dict)
                    else "MISSING"
                ),
            },
        )

    book = micro.get("order_book") if isinstance(micro.get("order_book"), dict) else {}
    flow = micro.get("recent_trades") if isinstance(micro.get("recent_trades"), dict) else {}
    settings = config.get("multi_strategy_engine", {}).get("s7_acceptance", {})
    min_trade_count = int(settings.get("minimum_recent_trade_count", 20))
    min_trade_imbalance = float(settings.get("minimum_trade_imbalance_abs", 0.15))
    min_depth_imbalance = float(settings.get("minimum_depth_imbalance_abs", 0.05))
    max_distance_pct = float(settings.get("maximum_distance_from_level_pct", 3.0))
    max_source_skew_ms = int(settings.get("maximum_source_skew_ms", 60000))

    prev_support = _float(previous.get("support"))
    prev_resistance = _float(previous.get("resistance"))
    close = _float(latest.get("close"))
    price = _float(record.get("last_price"))
    atr = _float(_indicators(record).get("atr_14"))
    volume_state = str(_indicators(record).get("volume_anomaly", {}).get("state") or "")
    trade_count = int(flow.get("trade_count") or 0)
    trade_imbalance = _float(flow.get("trade_imbalance"))
    depth_imbalance = _float(book.get("depth_imbalance"))
    midpoint = _float(book.get("midpoint"))
    source_skew_ms = micro.get("source_skew_ms")
    source_fresh = (
        isinstance(source_skew_ms, int)
        and source_skew_ms <= max_source_skew_ms
    )

    if None in (close, price, trade_imbalance, depth_imbalance, midpoint):
        return _data_insufficient(
            strategy_id,
            strategy_name,
            "Acceptance microstructure fields are incomplete",
            evidence={
                "trade_count": trade_count,
                "trade_imbalance": trade_imbalance,
                "depth_imbalance": depth_imbalance,
                "midpoint": midpoint,
                "source_skew_ms": source_skew_ms,
            },
        )

    direction = None
    accepted_level = None
    if (
        prev_resistance is not None
        and close > prev_resistance
        and price > prev_resistance
        and midpoint > prev_resistance
    ):
        direction = "LONG"
        accepted_level = prev_resistance
    elif (
        prev_support is not None
        and close < prev_support
        and price < prev_support
        and midpoint < prev_support
    ):
        direction = "SHORT"
        accepted_level = prev_support

    if direction is None or accepted_level is None:
        return _finish(
            record=record,
            config=config,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            direction=None,
            signal=False,
            signal_score=0.0,
            action="NO_SAFE_TRADE",
            entry=None,
            stop=None,
            target=None,
            evidence={
                "previous_support": prev_support,
                "previous_resistance": prev_resistance,
                "latest_close": close,
                "current_price": price,
                "book_midpoint": midpoint,
                "trade_imbalance": trade_imbalance,
                "depth_imbalance": depth_imbalance,
            },
            reasons=["No price acceptance beyond a previous canonical support/resistance level"],
        )

    if direction == "LONG":
        flow_aligned = trade_imbalance >= min_trade_imbalance
        depth_aligned = depth_imbalance >= min_depth_imbalance
    else:
        flow_aligned = trade_imbalance <= -min_trade_imbalance
        depth_aligned = depth_imbalance <= -min_depth_imbalance

    volume_aligned = volume_state in {"ELEVATED", "HIGH"}
    trade_count_ok = trade_count >= min_trade_count
    distance_pct = abs(price - accepted_level) / price * 100 if price else None
    distance_ok = distance_pct is not None and distance_pct <= max_distance_pct
    signal = bool(
        source_fresh
        and trade_count_ok
        and flow_aligned
        and depth_aligned
        and volume_aligned
        and distance_ok
    )

    atr_buffer = atr if atr is not None and atr > 0 else abs(price - accepted_level)
    if not atr_buffer:
        atr_buffer = price * 0.01
    stop = (
        accepted_level - atr_buffer
        if direction == "LONG"
        else accepted_level + atr_buffer
    )
    target = _structural_target(record, direction, accepted_level)

    score = (
        3.0
        + (1.5 if source_fresh else 0.0)
        + (1.0 if trade_count_ok else 0.0)
        + (1.5 if flow_aligned else 0.0)
        + (1.0 if depth_aligned else 0.0)
        + (1.0 if volume_aligned else 0.0)
        + (1.0 if distance_ok else 0.0)
    )
    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=signal,
        signal_score=score,
        action="PLACE_LIMIT",
        entry=accepted_level,
        stop=stop,
        target=target,
        evidence={
            "evidence_type": "ACCEPTANCE_SNAPSHOT_V1",
            "absorption_confirmed": False,
            "accepted_level": accepted_level,
            "previous_support": prev_support,
            "previous_resistance": prev_resistance,
            "latest_close": close,
            "current_price": price,
            "book_midpoint": midpoint,
            "trade_count": trade_count,
            "trade_imbalance": trade_imbalance,
            "depth_imbalance": depth_imbalance,
            "volume_state": volume_state,
            "distance_from_level_pct": distance_pct,
            "source_skew_ms": source_skew_ms,
            "note": "Snapshot evidence can establish acceptance; it does not by itself prove absorption",
        },
        reasons=[] if signal else ["Acceptance exists, but microstructure/participation/freshness conditions are not all aligned"],
        extra_checks={
            "source_fresh": source_fresh,
            "trade_count": trade_count_ok,
            "trade_flow_alignment": flow_aligned,
            "depth_alignment": depth_aligned,
            "volume_participation": volume_aligned,
            "distance_to_level": distance_ok,
        },
    )

def _s8_mean_reversion(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    del previous
    strategy_id, strategy_name = STRATEGY_CATALOG[7]
    indicators = _indicators(record)
    boll = indicators.get("bollinger", {}) if isinstance(indicators.get("bollinger"), dict) else {}
    upper = _float(boll.get("upper"))
    lower = _float(boll.get("lower"))
    middle = _float(boll.get("middle"))
    rsi = _float(indicators.get("rsi_14"))
    stoch = _float(indicators.get("stoch_rsi"))
    atr = _float(indicators.get("atr_14"))
    price = _float(record.get("last_price"))
    if None in (upper, lower, middle, rsi, stoch, price):
        return _data_insufficient(strategy_id, strategy_name, "Mean reversion requires Bollinger, RSI, StochRSI and price")
    direction = None
    if price >= upper * 0.995 and rsi >= 68 and stoch >= 85 and _trend(record, "4H") != "BULLISH":
        direction = "SHORT"
    elif price <= lower * 1.005 and rsi <= 32 and stoch <= 15 and _trend(record, "4H") != "BEARISH":
        direction = "LONG"
    signal = direction is not None
    if direction == "SHORT":
        stop = max(_float(record.get("resistance")) or upper, upper + (atr or 0.0))
        target = middle
    elif direction == "LONG":
        stop = min(_float(record.get("support")) or lower, lower - (atr or 0.0))
        target = middle
    else:
        stop = None
        target = None
    score = (
        (4.0 if signal else 0.0)
        + (3.0 if (stoch >= 90 or stoch <= 10) else 1.0)
        + (3.0 if (rsi >= 72 or rsi <= 28) else 1.0)
    )
    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=signal,
        signal_score=score,
        action="EXECUTE_NOW" if signal else "NO_SAFE_TRADE",
        entry=price if signal else None,
        stop=stop,
        target=target,
        evidence={
            "bollinger_upper": upper,
            "bollinger_middle": middle,
            "bollinger_lower": lower,
            "rsi_14": rsi,
            "stoch_rsi": stoch,
            "trend_4h": _trend(record, "4H"),
        },
        reasons=[] if signal else ["No countertrend extreme that passes the mean-reversion preconditions"],
    )


def _s9_catalyst(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    del previous
    strategy_id, strategy_name = STRATEGY_CATALOG[8]
    catalyst = record.get("catalyst")
    if not isinstance(catalyst, dict) or catalyst.get("validated") is not True:
        return _data_insufficient(
            strategy_id,
            strategy_name,
            "No validated, timestamped official catalyst evidence is bound to this canonical scan",
        )

    raw_direction = str(catalyst.get("direction") or "").upper()
    if raw_direction in {"LONG", "SHORT"}:
        direction = raw_direction
        direction_source = "CATALYST_EXPLICIT"
    else:
        direction = _direction_from_trends(record)
        direction_source = "MARKET_CONFIRMED_TRENDS"

    price = _float(record.get("last_price"))
    freshness_ok = bool(catalyst.get("fresh") is True)
    participation = str(
        _indicators(record).get(
            "volume_anomaly",
            {},
        ).get(
            "state"
        )
        or ""
    ) in {"ELEVATED", "HIGH"}
    direction_ok = direction in {"LONG", "SHORT"}

    stop = _structural_stop(record, direction or "")
    target = _structural_target(record, direction or "", price)
    context_signal = freshness_ok
    actionable_signal = bool(
        freshness_ok
        and participation
        and direction_ok
    )
    score = (
        3.0
        + (2.0 if freshness_ok else 0.0)
        + (2.0 if direction_ok else 0.0)
        + (3.0 if participation else 0.0)
    )

    reasons: list[str] = []
    if not freshness_ok:
        reasons.append("Official catalyst is outside the configured freshness window")
    if freshness_ok and not direction_ok:
        reasons.append("Waiting for market-confirmed LONG/SHORT direction after the catalyst")
    if freshness_ok and direction_ok and not participation:
        reasons.append("Waiting for participation confirmation after the catalyst")

    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=context_signal,
        signal_score=score,
        action="EXECUTE_NOW" if actionable_signal else "WAIT_FOR_TRIGGER",
        entry=price if direction_ok else None,
        stop=stop,
        target=target,
        evidence={
            "catalyst_id": catalyst.get("id"),
            "source": catalyst.get("source"),
            "source_read_only": catalyst.get("source_read_only"),
            "title": catalyst.get("title"),
            "ann_type": catalyst.get("ann_type"),
            "ann_sub_type": catalyst.get("ann_sub_type"),
            "published_at": catalyst.get("published_at"),
            "age_ms": catalyst.get("age_ms"),
            "matched_on": catalyst.get("matched_on"),
            "fresh": freshness_ok,
            "direction_source": direction_source,
            "market_direction": direction,
            "volume_participation": participation,
            "note": "Announcement sentiment is not used to invent direction; direction is market-confirmed when not explicit",
        },
        reasons=reasons,
        extra_checks={
            "catalyst_fresh": freshness_ok,
            "direction_confirmed": direction_ok,
            "participation": participation,
        },
    )

def _s10_regime_beta(record: dict[str, Any], previous: dict[str, Any] | None, config: dict[str, Any]) -> dict[str, Any]:
    del previous
    strategy_id, strategy_name = STRATEGY_CATALOG[9]
    btc_change = _float(record.get("btc_change_24h_pct"))
    rs = _float(record.get("behaviour", {}).get("relative_strength_vs_btc_pct"))
    price = _float(record.get("last_price"))
    if btc_change is None or rs is None or price is None:
        return _data_insufficient(
            strategy_id,
            strategy_name,
            "Risk-regime strategy requires BTC regime, relative-strength proxy and price",
        )
    direction = None
    if btc_change >= 1.0 and rs >= 0 and _trend(record, "1H") == "BULLISH":
        direction = "LONG"
    elif btc_change <= -1.0 and rs <= 0 and _trend(record, "1H") == "BEARISH":
        direction = "SHORT"
    regime_strength = min(4.0, abs(btc_change))
    rs_strength = min(3.0, abs(rs))
    trend_strength = 3.0 if direction else 0.0
    signal = direction is not None
    stop = _structural_stop(record, direction or "")
    target = _structural_target(record, direction or "", price)
    return _finish(
        record=record,
        config=config,
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        direction=direction,
        signal=signal,
        signal_score=regime_strength + rs_strength + trend_strength,
        action="EXECUTE_NOW" if signal else "WAIT_FOR_TRIGGER",
        entry=price if signal else None,
        stop=stop,
        target=target,
        evidence={
            "btc_change_24h_pct": btc_change,
            "relative_strength_vs_btc_pct": rs,
            "trend_1h": _trend(record, "1H"),
            "note": "Regime proxy only; no calibrated beta coefficient is claimed",
        },
        reasons=[] if signal else ["BTC regime, relative strength and symbol trend are not aligned"],
        extra_checks={"regime_alignment": signal},
    )


EVALUATORS = (
    _s1_early_momentum,
    _s2_breakout_retest,
    _s3_trend_pullback,
    _s4_relative_strength,
    _s5_compression,
    _s6_sweep_reclaim,
    _s7_acceptance_absorption,
    _s8_mean_reversion,
    _s9_catalyst,
    _s10_regime_beta,
)


def _best_shadow_candidate(strategies: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [row for row in strategies if row.get("status") == "SHADOW_CANDIDATE"]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda row: (
            ACTION_PRIORITY.get(str(row.get("action")), 0),
            _float(row.get("signal_score")) or 0.0,
            _float(row.get("rr")) or 0.0,
            -(_float(row.get("distance_to_entry_pct")) or 0.0),
        ),
        reverse=True,
    )[0]


def apply_multi_strategy_engine(
    record: dict[str, Any],
    previous: dict[str, Any] | None,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate S1-S10 against one canonical scanner record.

    This engine is deliberately shadow-only. It cannot mutate or grant the existing
    V7 trade permission. Every strategy emits transparent evidence, a strategy-
    specific geometry when available, and an explicit fail-closed state.
    """
    settings = config.get("multi_strategy_engine", {})
    enabled = settings.get("enabled", True) is True
    original_trade_permission = bool(record.get("trade_permission", False))
    original_v7_ready = bool(record.get("v7_trade_ready", False))

    if not enabled:
        strategies = [
            {
                **_base_result(strategy_id, strategy_name),
                "status": "DISABLED",
                "reasons": ["Multi-strategy engine disabled by configuration"],
            }
            for strategy_id, strategy_name in STRATEGY_CATALOG
        ]
    else:
        strategies = [evaluator(record, previous, config) for evaluator in EVALUATORS]

    candidate = _best_shadow_candidate(strategies)
    payload = {
        "version": ENGINE_VERSION,
        "enabled": enabled,
        "shadow_only": True,
        "trade_permission": False,
        "production_permission": False,
        "strategy_count": len(strategies),
        "strategies": strategies,
        "shadow_candidate_count": sum(row.get("status") == "SHADOW_CANDIDATE" for row in strategies),
        "watch_count": sum(row.get("status") == "WATCH" for row in strategies),
        "data_insufficient_count": sum(row.get("status") == "DATA_INSUFFICIENT" for row in strategies),
        "best_shadow_candidate": candidate,
    }
    record["multi_strategy_engine"] = payload

    # Safety invariant: this engine never changes legacy execution authority.
    record["trade_permission"] = original_trade_permission
    record["v7_trade_ready"] = original_v7_ready
    return payload


def build_multi_strategy_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    strategy_counts = {strategy_id: 0 for strategy_id, _ in STRATEGY_CATALOG}
    candidate_counts = {strategy_id: 0 for strategy_id, _ in STRATEGY_CATALOG}
    total_evaluations = 0
    shadow_candidates = 0
    watches = 0
    data_insufficient = 0
    covered_symbols = 0
    persistent_active = 0
    persistent_continuing = 0

    for record in results:
        if "error" in record:
            continue
        engine = record.get("multi_strategy_engine", {})
        strategies = engine.get("strategies", []) if isinstance(engine, dict) else []
        if strategies:
            covered_symbols += 1
        persistence_summary = (
            engine.get("persistence_summary", {})
            if isinstance(engine, dict)
            else {}
        )
        if isinstance(persistence_summary, dict):
            persistent_active += int(persistence_summary.get("active_count") or 0)
            persistent_continuing += int(persistence_summary.get("continuing_count") or 0)
        for row in strategies:
            strategy_id = str(row.get("strategy_id") or "")
            if strategy_id in strategy_counts:
                strategy_counts[strategy_id] += 1
            total_evaluations += 1
            status = row.get("status")
            if status == "SHADOW_CANDIDATE":
                shadow_candidates += 1
                if strategy_id in candidate_counts:
                    candidate_counts[strategy_id] += 1
            elif status == "WATCH":
                watches += 1
            elif status == "DATA_INSUFFICIENT":
                data_insufficient += 1

    return {
        "version": ENGINE_VERSION,
        "shadow_only": True,
        "trade_permission": False,
        "configured_strategy_count": len(STRATEGY_CATALOG),
        "covered_symbol_count": covered_symbols,
        "total_evaluations": total_evaluations,
        "shadow_candidate_count": shadow_candidates,
        "watch_count": watches,
        "data_insufficient_count": data_insufficient,
        "persistent_active_count": persistent_active,
        "persistent_continuing_count": persistent_continuing,
        "evaluations_by_strategy": strategy_counts,
        "candidates_by_strategy": candidate_counts,
    }
