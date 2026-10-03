from __future__ import annotations

from typing import Any


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_s6_closed_reclaim_shadow(
    record: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate sweep/reclaim only from a fully closed 1H candle.

    V15 diagnostic only. It does not grant execution or production permission.
    """
    tf = record.get("timeframes", {}).get("1H", {})
    candle = tf.get("last_closed_candle")
    if not isinstance(candle, dict) or not previous:
        return {
            "status": "DATA_INSUFFICIENT",
            "reason": "closed 1H candle and previous levels are required",
            "shadow_only": True,
            "trade_permission": False,
        }

    prev_support = _float(previous.get("support"))
    prev_resistance = _float(previous.get("resistance"))
    low = _float(candle.get("low"))
    high = _float(candle.get("high"))
    close = _float(candle.get("close"))
    price = _float(record.get("last_price"))

    if None in (low, high, close, price):
        return {
            "status": "DATA_INSUFFICIENT",
            "reason": "closed-candle fields are incomplete",
            "shadow_only": True,
            "trade_permission": False,
        }

    direction = None
    swept_level = None
    if prev_support is not None and low < prev_support < close:
        direction = "LONG"
        swept_level = prev_support
    elif prev_resistance is not None and high > prev_resistance > close:
        direction = "SHORT"
        swept_level = prev_resistance

    indicators = tf.get("indicators") if isinstance(tf, dict) else {}
    volume = (
        indicators.get("volume_anomaly")
        if isinstance(indicators, dict)
        else {}
    )
    volume_state = (
        str(volume.get("state") or "")
        if isinstance(volume, dict)
        else ""
    )
    participation = volume_state in {"ELEVATED", "HIGH"}
    qualified = bool(direction and participation)

    stop = low if direction == "LONG" else high if direction == "SHORT" else None
    risk_pct = (
        abs(price - stop) / price * 100.0
        if qualified and stop is not None and price
        else None
    )

    return {
        "status": "QUALIFIED" if qualified else "WATCH",
        "direction": direction,
        "swept_level": swept_level,
        "closed_low": low,
        "closed_high": high,
        "closed_close": close,
        "reference_price": price,
        "stop_reference": stop,
        "risk_pct": risk_pct,
        "volume_state": volume_state,
        "participation": participation,
        "candle_basis": "LAST_FULLY_CLOSED_1H",
        "shadow_only": True,
        "trade_permission": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }
