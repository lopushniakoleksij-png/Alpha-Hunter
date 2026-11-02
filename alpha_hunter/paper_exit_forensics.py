"""Isolated, retrospective Bitget 1-minute paper exit path forensics.

This module does not collect data, write to storage, alter exits, or submit orders.
A public candle path can establish an inferred bar-level first touch only, never
an executable quote or a proven exchange fill. For sealed R9 it is NEVER proof
of a qualifying completed trade.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

SOURCE = "BITGET_PUBLIC_V3_1M_HISTORY_CANDLES"
ENDPOINT = "/api/v3/market/history-candles"
MAX_PATH_MINUTES = 1440
_VALID_EXITS = frozenset(("STOP_LOSS", "TAKE_PROFIT", "HORIZON_24H"))


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        timestamp = value
    else:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Timezone-aware timestamps are required")
    return timestamp.astimezone(timezone.utc)


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("Missing numeric price")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Unparseable numeric price") from None
    if not number.is_finite() or number <= 0:
        raise ValueError("Price must be finite and positive")
    return number


def _base_result(reason: str) -> dict[str, Any]:
    return {
        "status": "DATA_INSUFFICIENT",
        "reason": reason,
        "inferred_first_touch_type": None,
        "inferred_first_touch_minute_utc": None,
        "minutes_first_touch_to_observed_exit": None,
        "observed_exit_reason_matches": None,
        "complete_consecutive_candles": False,
        "candle_count_checked": 0,
        "expected_candle_count": None,
        "local_path_sha256": None,
        "evidence_source": SOURCE,
        "source_endpoint": ENDPOINT,
        "source_authentication": "NOT_INDEPENDENTLY_AUTHENTICATED",
        "execution_price_verified": False,
        "counterfactual_only": True,
        "paper_test_evidence": False,
        "profitability_claim_permitted": False,
        "production_promotion_permitted": False,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
    }


def audit_paper_exit_one_minute_path(
    *,
    entry_at_utc: str | datetime,
    observed_exit_at_utc: str | datetime,
    direction: str,
    stop_price: Any,
    target_price: Any,
    observed_exit_reason: str,
    candles: Sequence[Mapping[str, Any]],
    source: str,
    source_endpoint: str,
) -> dict[str, Any]:
    """Return an immutable-input, no-authority first-touch finding.

    Requires the COMPLETE contiguous sequence of minute bars from the entry
    minute THROUGH the observed-exit minute, even if an early bar touches a
    protective level. Rejecting later missing evidence prevents a partial path
    from being presented as an independently complete reconstruction.

    Candle timestamps are minute starts, in chronological order. Bars spanning
    the entry minute cannot establish quote ordering relative to entry fill,
    even when the entry timestamp falls exactly on a boundary.
    """
    result = _base_result("UNVERIFIED_PATH")
    try:
        if source != SOURCE or source_endpoint != ENDPOINT:
            raise ValueError("PUBLIC_SOURCE_PROVENANCE_NOT_IDENTIFIED")
        if direction not in ("LONG", "SHORT"):
            raise ValueError("INVALID_DIRECTION")
        if observed_exit_reason not in _VALID_EXITS:
            raise ValueError("INVALID_RECORDED_EXIT_REASON")
        start = _timestamp(entry_at_utc)
        end = _timestamp(observed_exit_at_utc)
        if end <= start:
            raise ValueError("OBSERVATION_NOT_AFTER_ENTRY")
        start_minute = start.replace(second=0, microsecond=0)
        end_minute = end.replace(second=0, microsecond=0)
        difference = int((end_minute - start_minute).total_seconds() / 60)
        if difference > MAX_PATH_MINUTES:
            raise ValueError("PATH_EXCEEDS_24H_COVERAGE")
        expected = difference + 1
        result["expected_candle_count"] = expected
        if not isinstance(candles, (list, tuple)) or len(candles) != expected:
            raise ValueError("MISSING_OR_EXTRA_CANDLES")
        stop = _number(stop_price)
        target = _number(target_price)
        if (direction == "LONG" and not stop < target) or (
            direction == "SHORT" and not target < stop
        ):
            raise ValueError("INVALID_PROTECTIVE_GEOMETRY")

        clean: list[dict[str, str]] = []
        for i, candle in enumerate(candles):
            if not isinstance(candle, Mapping):
                raise ValueError("INVALID_CANDLE")
            minute = _timestamp(candle.get("minute_utc"))
            if minute != start_minute + timedelta(minutes=i):
                raise ValueError("NONCONTIGUOUS_OR_UNORDERED_CANDLE_PATH")
            o, h, low, close = (
                _number(candle.get("open")),
                _number(candle.get("high")),
                _number(candle.get("low")),
                _number(candle.get("close")),
            )
            if h < max(o, low, close) or low > min(o, h, close):
                raise ValueError("INVALID_OHLC_GEOMETRY")
            clean.append({
                "minute_utc": minute.isoformat(),
                "open": str(o), "high": str(h),
                "low": str(low), "close": str(close),
            })
        result["complete_consecutive_candles"] = True
        result["candle_count_checked"] = expected
        # Local custody checksum permits later byte-for-byte comparisons, but
        # MUST NOT be called independent exchange quote authentication.
        canonical = json.dumps(clean, sort_keys=True, separators=(",", ":"))
        result["local_path_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()

        first = None
        for bar in clean:
            hi = Decimal(bar["high"])
            lo = Decimal(bar["low"])
            minute = _timestamp(bar["minute_utc"])
            stop_hit = (lo <= stop) if direction == "LONG" else (hi >= stop)
            target_hit = (hi >= target) if direction == "LONG" else (lo <= target)
            if not stop_hit and not target_hit:
                continue
            if minute == start_minute:
                first = ("ENTRY_MINUTE_ORDERING_AMBIGUOUS", minute)
            elif stop_hit and target_hit:
                first = ("AMBIGUOUS_SAME_MINUTE", minute)
            else:
                first = ("STOP_LOSS" if stop_hit else "TAKE_PROFIT", minute)
            break

        if first is None:
            result["status"] = "NO_MINUTE_TOUCH_FOUND"
            result["reason"] = "NO_TOUCH_IN_FULL_BAR_PATH"
        else:
            touch_type, touch_minute = first
            result["status"] = touch_type
            result["inferred_first_touch_type"] = touch_type
            result["inferred_first_touch_minute_utc"] = touch_minute.isoformat()
            result["minutes_first_touch_to_observed_exit"] = round(
                (end - touch_minute).total_seconds() / 60, 6
            )
            result["observed_exit_reason_matches"] = (
                touch_type == observed_exit_reason
                if touch_type in ("STOP_LOSS", "TAKE_PROFIT")
                else None
            )
            result["reason"] = (
                "CANDLE_PATH_FIRST_TOUCH_ONLY_NOT_EXCHANGE_FILL"
                if touch_type in ("STOP_LOSS", "TAKE_PROFIT")
                else "INTRAMINUTE_ORDERING_NOT_PROVEN"
            )
    except (TypeError, ValueError, OverflowError, KeyError) as exc:
        result["reason"] = str(exc) or "MALFORMED_PATH"
    return result
