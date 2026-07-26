from __future__ import annotations

from math import sqrt
from statistics import mean, pstdev
from typing import Any


def to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_candles(rows: list[list[str]]) -> list[dict[str, float | int]]:
    candles = []
    for row in rows:
        if len(row) < 7:
            continue
        candles.append(
            {
                "timestamp": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "base_volume": float(row[5]),
                "quote_volume": float(row[6]),
            }
        )
    candles.sort(key=lambda x: x["timestamp"])
    return candles


def ema(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    value = mean(values[:period])
    multiplier = 2 / (period + 1)
    for current in values[period:]:
        value = (current - value) * multiplier + value
    return value


def ema_series(values: list[float], period: int) -> list[float]:
    if period <= 0 or len(values) < period:
        return []
    output = [mean(values[:period])]
    multiplier = 2 / (period + 1)
    for current in values[period:]:
        output.append((current - output[-1]) * multiplier + output[-1])
    return output


def rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    avg_gain = mean(gains[:period])
    avg_loss = mean(losses[:period])
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0
    relative_strength = avg_gain / avg_loss
    return 100 - (100 / (1 + relative_strength))


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float | None]:
    if len(values) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None}
    fast_series = ema_series(values, fast)
    slow_series = ema_series(values, slow)
    offset = slow - fast
    aligned_fast = fast_series[offset:]
    macd_line = [a - b for a, b in zip(aligned_fast, slow_series)]
    signal_line = ema_series(macd_line, signal)
    if not signal_line:
        return {"macd": None, "signal": None, "histogram": None}
    current_macd = macd_line[-1]
    current_signal = signal_line[-1]
    return {
        "macd": current_macd,
        "signal": current_signal,
        "histogram": current_macd - current_signal,
    }


def bollinger(values: list[float], period: int = 20, deviations: float = 2.0) -> dict[str, float | None]:
    if len(values) < period:
        return {"middle": None, "upper": None, "lower": None, "width_pct": None}
    sample = values[-period:]
    middle = mean(sample)
    deviation = pstdev(sample)
    upper = middle + deviations * deviation
    lower = middle - deviations * deviation
    width_pct = ((upper - lower) / middle * 100) if middle else None
    return {"middle": middle, "upper": upper, "lower": lower, "width_pct": width_pct}


def atr(candles: list[dict[str, float | int]], period: int = 14) -> float | None:
    if len(candles) <= period:
        return None
    ranges: list[float] = []
    for index in range(1, len(candles)):
        high = float(candles[index]["high"])
        low = float(candles[index]["low"])
        previous_close = float(candles[index - 1]["close"])
        ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    value = mean(ranges[:period])
    for current in ranges[period:]:
        value = ((value * (period - 1)) + current) / period
    return value


def volume_anomaly(candles: list[dict[str, float | int]], lookback: int = 20) -> dict[str, float | str | None]:
    if len(candles) < lookback + 1:
        return {"ratio": None, "z_score": None, "state": "DATA_UNAVAILABLE"}
    historical = [float(c["quote_volume"]) for c in candles[-(lookback + 1):-1]]
    current = float(candles[-1]["quote_volume"])
    baseline = mean(historical)
    deviation = pstdev(historical)
    ratio = current / baseline if baseline else None
    z_score = (current - baseline) / deviation if deviation else 0.0
    if ratio is not None and (ratio >= 2.0 or z_score >= 2.0):
        state = "HIGH"
    elif ratio is not None and ratio >= 1.25:
        state = "ELEVATED"
    else:
        state = "NORMAL"
    return {"ratio": ratio, "z_score": z_score, "state": state}


def calculate_indicators(candles: list[dict[str, float | int]]) -> dict[str, Any]:
    closes = [float(c["close"]) for c in candles]
    current_atr = atr(candles)
    latest_close = closes[-1] if closes else None
    return {
        "ema_9": ema(closes, 9),
        "ema_21": ema(closes, 21),
        "ema_50": ema(closes, 50),
        "rsi_14": rsi(closes, 14),
        "macd": macd(closes),
        "bollinger": bollinger(closes),
        "atr_14": current_atr,
        "atr_pct": (current_atr / latest_close * 100) if current_atr and latest_close else None,
        "volume_anomaly": volume_anomaly(candles),
    }


def trend_state(candles: list[dict[str, float | int]]) -> str:
    if len(candles) < 30:
        return "DATA_UNAVAILABLE"
    closes = [float(c["close"]) for c in candles]
    fast = ema(closes, 9)
    slow = ema(closes, 21)
    recent = closes[-1]
    prior = closes[-5]
    if fast is not None and slow is not None and fast > slow and recent > prior:
        return "BULLISH"
    if fast is not None and slow is not None and fast < slow and recent < prior:
        return "BEARISH"
    return "NEUTRAL"


def support_resistance(candles: list[dict[str, float | int]], window: int = 40) -> dict[str, float | None]:
    sample = candles[-window:]
    if not sample:
        return {"support": None, "resistance": None}
    return {
        "support": min(float(c["low"]) for c in sample),
        "resistance": max(float(c["high"]) for c in sample),
    }


def percentage_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous * 100


def funding_summary(rows: list[dict[str, Any]], current: float | None) -> dict[str, Any]:
    rates = [to_float(row.get("fundingRate")) for row in rows]
    valid = [rate for rate in rates if rate is not None]
    if not valid:
        return {"current": current, "average": None, "change_vs_average_pct": None, "extreme": False}
    average = mean(valid)
    return {
        "current": current,
        "average": average,
        "change_vs_average_pct": percentage_change(current, average),
        "extreme": bool(current is not None and abs(current) >= 0.001),
    }


def classify_state(timeframe_trends: dict[str, str], last_price: float | None, levels: dict[str, float | None]) -> tuple[str, bool, str]:
    valid = [v for v in timeframe_trends.values() if v != "DATA_UNAVAILABLE"]
    if len(valid) < 3 or last_price is None:
        return "DATA_UNAVAILABLE", False, "Critical market data is incomplete"

    bullish = sum(v == "BULLISH" for v in valid)
    bearish = sum(v == "BEARISH" for v in valid)
    support = levels.get("support")
    resistance = levels.get("resistance")

    if bullish == 3:
        state = "DIRECTION_EMERGING_LONG"
    elif bearish == 3:
        state = "DIRECTION_EMERGING_SHORT"
    elif bullish >= 2:
        state = "WATCH_LONG"
    elif bearish >= 2:
        state = "WATCH_SHORT"
    else:
        state = "NEUTRAL"

    if support is None or resistance is None or support >= resistance:
        return state, False, "Invalid support/resistance structure"

    return state, False, "Execution gate is locked until Task 2 validates a realistic 1:5 RR setup"



def compression_score(candles: list[dict[str, float | int]], lookback: int = 20) -> dict[str, Any]:
    """Measure recent volatility compression without inventing a breakout target."""
    if len(candles) < lookback * 2:
        return {"score": None, "state": "DATA_UNAVAILABLE", "recent_range_pct": None, "prior_range_pct": None}
    recent = candles[-lookback:]
    prior = candles[-(lookback * 2):-lookback]

    def range_pct(sample: list[dict[str, float | int]]) -> float | None:
        high = max(float(c["high"]) for c in sample)
        low = min(float(c["low"]) for c in sample)
        midpoint = (high + low) / 2
        return ((high - low) / midpoint * 100) if midpoint else None

    recent_pct = range_pct(recent)
    prior_pct = range_pct(prior)
    if recent_pct is None or prior_pct in (None, 0):
        return {"score": None, "state": "DATA_UNAVAILABLE", "recent_range_pct": recent_pct, "prior_range_pct": prior_pct}
    ratio = recent_pct / prior_pct
    score = max(0.0, min(10.0, (1.5 - ratio) / 1.0 * 10.0))
    state = "STRONG" if ratio <= 0.65 else "MODERATE" if ratio <= 0.9 else "NONE"
    return {"score": round(score, 2), "state": state, "recent_range_pct": recent_pct, "prior_range_pct": prior_pct}


def build_intelligence_score(record: dict[str, Any], minimum_rr: float = 5.0) -> dict[str, Any]:
    """Transparent heuristic scorecard; probability is not statistically calibrated."""
    one_hour = record.get("timeframes", {}).get("1H", {})
    indicators = one_hour.get("indicators", {})
    setup = record.get("execution_setup", {})
    state = record.get("state", "DATA_UNAVAILABLE")
    direction = setup.get("direction")
    rr = setup.get("rr")
    integrity = float(record.get("data_integrity_score") or 0)
    oi_change = record.get("open_interest_change_pct")
    volume_state = indicators.get("volume_anomaly", {}).get("state")
    compression = one_hour.get("compression", {})
    funding_extreme = record.get("funding_history", {}).get("extreme", False)

    components = {
        "direction": 20 if state.startswith("DIRECTION_EMERGING") else 12 if state.startswith("WATCH") else 4,
        "momentum": 15 if setup.get("checks", {}).get("momentum_confirmed") else 5,
        "participation": 15 if setup.get("checks", {}).get("participation_confirmed") else 7 if volume_state == "ELEVATED" else 2,
        "compression": min(10, float(compression.get("score") or 0)),
        "reward_risk": 20 if rr is not None and rr >= minimum_rr else min(20, max(0, float(rr or 0) / minimum_rr * 20)),
        "funding_quality": 10 if not funding_extreme else 0,
        "data_quality": integrity / 10,
    }
    total = round(min(100.0, sum(components.values())), 1)
    # This is deliberately labelled an estimate, not a backtested probability.
    probability_estimate = round(min(90.0, max(20.0, 20.0 + total * 0.72)), 1)

    if oi_change is not None and oi_change > 0 and volume_state in {"ELEVATED", "HIGH"}:
        participation = "CONFIRMED"
    elif volume_state in {"ELEVATED", "HIGH"} or (oi_change is not None and oi_change > 0):
        participation = "PARTIAL"
    else:
        participation = "NOT_CONFIRMED"

    if setup.get("permission"):
        verdict = f"{direction}_READY"
    elif state.startswith("DIRECTION_EMERGING"):
        verdict = "DIRECTION_EMERGING"
    elif state.startswith("WATCH"):
        verdict = "WATCH"
    elif state == "DATA_UNAVAILABLE":
        verdict = "DATA_UNAVAILABLE"
    else:
        verdict = "NO_SETUP"

    return {
        "huge_rr_score": round(total / 10, 1),
        "confidence_estimate_pct": probability_estimate,
        "confidence_is_calibrated": False,
        "institutional_participation": participation,
        "verdict": verdict,
        "components": components,
    }

def integrity_score(record: dict[str, Any]) -> int:
    checks = [
        record.get("last_price") is not None,
        record.get("mark_price") is not None,
        record.get("index_price") is not None,
        record.get("open_interest") is not None,
        record.get("funding_rate") is not None,
        bool(record.get("funding_history", {}).get("average") is not None),
        all(tf.get("candle_count", 0) >= 50 for tf in record.get("timeframes", {}).values()),
        all(tf.get("indicators", {}).get("rsi_14") is not None for tf in record.get("timeframes", {}).values()),
    ]
    return round(100 * sum(checks) / len(checks))


def validate_trade_setup(record: dict[str, Any], minimum_rr: float = 5.0) -> dict[str, Any]:
    """Conservative execution gate using only observable structure.

    The current price is treated as a reference entry. For longs, 1H support is
    the invalidation and 1H resistance is the first structural target. Shorts
    use the inverse. No projected or synthetic target is invented.
    """
    state = record.get("state")
    price = record.get("last_price")
    support = record.get("support")
    resistance = record.get("resistance")
    integrity = record.get("data_integrity_score", 0)
    one_hour = record.get("timeframes", {}).get("1H", {})
    indicators = one_hour.get("indicators", {})
    rsi_value = indicators.get("rsi_14")
    histogram = indicators.get("macd", {}).get("histogram")
    volume_state = indicators.get("volume_anomaly", {}).get("state")
    funding_extreme = record.get("funding_history", {}).get("extreme", False)
    oi_change = record.get("open_interest_change_pct")

    result = {
        "direction": None,
        "entry": price,
        "stop": None,
        "target": None,
        "risk": None,
        "reward": None,
        "rr": None,
        "permission": False,
        "reason": "Setup conditions are incomplete",
        "checks": {},
    }
    if None in (price, support, resistance) or support >= resistance:
        result["reason"] = "Invalid or incomplete price structure"
        return result

    if state == "DIRECTION_EMERGING_LONG":
        direction = "LONG"
        stop, target = support, resistance
        momentum_ok = rsi_value is not None and 50 <= rsi_value <= 68 and histogram is not None and histogram > 0
        participation_ok = volume_state in {"ELEVATED", "HIGH"} and (oi_change is None or oi_change >= 0)
        structure_ok = support < price < resistance
    elif state == "DIRECTION_EMERGING_SHORT":
        direction = "SHORT"
        stop, target = resistance, support
        momentum_ok = rsi_value is not None and 32 <= rsi_value <= 50 and histogram is not None and histogram < 0
        participation_ok = volume_state in {"ELEVATED", "HIGH"} and (oi_change is None or oi_change >= 0)
        structure_ok = support < price < resistance
    else:
        result["reason"] = "Direction is not fully aligned across 15m, 1H and 4H"
        return result

    risk = abs(price - stop)
    reward = abs(target - price)
    rr = reward / risk if risk > 0 else None
    checks = {
        "direction_aligned": True,
        "structure_valid": structure_ok,
        "momentum_confirmed": momentum_ok,
        "participation_confirmed": participation_ok,
        "funding_not_extreme": not funding_extreme,
        "data_integrity_min_88": integrity >= 88,
        "rr_minimum_met": rr is not None and rr >= minimum_rr,
    }
    permission = all(checks.values())
    failed = [name for name, passed in checks.items() if not passed]
    result.update({
        "direction": direction,
        "stop": stop,
        "target": target,
        "risk": risk,
        "reward": reward,
        "rr": rr,
        "permission": permission,
        "reason": "All execution conditions passed" if permission else "Failed: " + ", ".join(failed),
        "checks": checks,
    })
    return result
