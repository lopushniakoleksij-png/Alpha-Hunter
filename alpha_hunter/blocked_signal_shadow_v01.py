"""Read-only synthetic/prospective blocked-signal OHLC shadow classification.

No orders, database writes, or inference of intrabar ordering.
Caller must provide consecutive, verified, fully closed candles after signal time.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _number(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean price")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid price") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError("nonpositive/nonfinite price")
    return result


def _time(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def evaluate_blocked_shadow(
    signal: dict[str, Any],
    candles: list[dict[str, Any]],
    *,
    horizon_hours: int,
    interval_minutes: int = 60,
) -> dict[str, Any]:
    """Return conservative gross path classification; never a simulated trade."""
    result = {"classification": "INSUFFICIENT_DATA", "gross_only": True,
              "fill_verified": False, "net_return": None}
    if not isinstance(horizon_hours, int) or isinstance(horizon_hours, bool) or horizon_hours <= 0:
        return result
    if interval_minutes <= 0 or 60 * horizon_hours % interval_minutes:
        return result
    try:
        if signal.get("final_gate_outcome") != "BLOCKED" or not signal.get("block_reasons"):
            return result
        direction = signal["direction"]
        if direction not in ("LONG", "SHORT"):
            return result
        decision = _time(signal["decision_at"])
        entry, stop, target, tick = (_number(signal[k]) for k in
                                      ("entry", "stop", "target", "tick_size"))
        if any(price % tick != 0 for price in (entry, stop, target)):
            return result
        if not ((stop < entry < target) if direction == "LONG"
                else (target < entry < stop)):
            return result
        expected = horizon_hours * 60 // interval_minutes
        if len(candles) != expected:
            return result
        interval = timedelta(minutes=interval_minutes)
        first_open = decision.replace(minute=0, second=0, microsecond=0)
        if interval_minutes != 60:
            return result  # v1 supports only closed hourly candles
        first_open += interval
        # Validate the entire evidence window before classifying any outcome.
        # Otherwise an early target can hide a later missing or forged candle.
        validated = []
        for index, candle in enumerate(candles):
            opened = _time(candle["open_at"])
            closed = _time(candle["closed_at"])
            if opened != first_open + index * interval or closed != opened + interval:
                return result
            if candle.get("verified") is not True or candle.get("fully_closed") is not True:
                return result
            if _time(candle["known_at"]) < closed:
                return result
            low, high = _number(candle["low"]), _number(candle["high"])
            if low > high:
                return result
            validated.append((low, high))
        filled = False
        for low, high in validated:
            if not filled:
                if not (low <= entry <= high):
                    continue
                filled = True
                # Intrabar ordering after entry is unknowable even when one barrier touched.
                if ((low <= stop or high >= target) if direction == "LONG"
                    else (high >= stop or low <= target)):
                    return {**result, "classification": "BOTH_SAME_CANDLE_AMBIGUOUS",
                            "entry_touched": True}
                continue
            target_hit = high >= target if direction == "LONG" else low <= target
            stop_hit = low <= stop if direction == "LONG" else high >= stop
            if target_hit and stop_hit:
                label = "BOTH_SAME_CANDLE_AMBIGUOUS"
            elif target_hit:
                label = "TARGET_FIRST"
            elif stop_hit:
                label = "STOP_FIRST"
            else:
                continue
            return {**result, "classification": label, "entry_touched": True}
        return {**result, "classification": "EXPIRED" if filled else "NO_FILL",
                "entry_touched": filled}
    except (KeyError, TypeError, ValueError, OverflowError):
        return result
