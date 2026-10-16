"""Research-only audit of existing paper stop/target top-of-book capacity.

No HTTP, SQL, state writes, partial-fill assumptions or paper/admission authority.
Snapshots are *not* orders. Each level's size is momentary and MUST NOT be
aggregated across observations as though it were replenishable liquidity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


def _positive(value: Any) -> Decimal:
    try:
        x = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError("NOT_NUMERIC") from None
    if not x.is_finite() or x <= 0:
        raise ValueError("NOT_POSITIVE")
    return x


def _nonnegative(value: Any) -> Decimal:
    x = Decimal(str(value))
    if not x.is_finite() or x < 0:
        raise ValueError("NEGATIVE_OR_INVALID")
    return x


def _timestamp(value: Any) -> datetime:
    date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError("TIMEZONE_MISSING")
    return date.astimezone(timezone.utc)


def _safe_result() -> dict[str, Any]:
    return {
        "status": "DATA_INSUFFICIENT",
        "trigger_type": None,
        "quantity": None,
        "executable_at_top_of_book": False,
        "paper_fill_verified": False,
        "counterfactual_only": True,
        "trade_permission": False,
        "exchange_authority": False,
        "production_promotion_permitted": False,
        "profitability_claim_permitted": False,
        "partial_fill_permitted": False,
        "position_adjustment_permitted": False,
        "source_authentication": "NOT_INDEPENDENTLY_ATTESTED",
    }


def evaluate_observed_exit_capacity(
    *,
    direction: str,
    quantity: Any,
    stop: Any,
    target: Any,
    best_bid: Any,
    best_ask: Any,
    best_bid_size: Any,
    best_ask_size: Any,
    observed_at_utc: str,
    quote_source: str | None = None,
) -> dict[str, Any]:
    """Classify one existing sampled quote using the sealed v0.4 threshold rule.

    This is *diagnostic*. A large enough displayed size does not prove that
    the size remained available or that a real order executed there.
    """
    result = _safe_result()
    try:
        _timestamp(observed_at_utc)
        q, sl, tp = _positive(quantity), _positive(stop), _positive(target)
        bid, ask = _positive(best_bid), _positive(best_ask)
        bid_size, ask_size = _nonnegative(best_bid_size), _nonnegative(best_ask_size)
        if ask < bid or direction not in ("LONG", "SHORT"):
            raise ValueError("INVALID_MARKET_DIRECTION")
        if not ((sl < tp) if direction == "LONG" else (tp < sl)):
            raise ValueError("INVALID_STOP_TARGET_GEOMETRY")
        result.update(quantity=str(q), quote_source=quote_source or "UNIDENTIFIED")
        if direction == "LONG":
            stop_hit, target_hit, crossing_size = bid <= sl, bid >= tp, bid_size
            result["exit_side"] = "SELL"
        else:
            stop_hit, target_hit, crossing_size = ask >= sl, ask <= tp, ask_size
            result["exit_side"] = "BUY"
        result["observed_top_of_book_size"] = str(crossing_size)
        result["observed_fraction_of_position"] = str(min(crossing_size/q, Decimal("1")))
        if stop_hit and target_hit:
            result.update(status="TRIGGER_ORDER_AMBIGUOUS", blocker="SIMULTANEOUS_STOP_TARGET")
        elif not stop_hit and not target_hit:
            result.update(status="NO_TRIGGER")
        else:
            trigger = "STOP_LOSS" if stop_hit else "TAKE_PROFIT"
            result["trigger_type"] = trigger
            if crossing_size < q:
                result.update(
                    status="TRIGGERED_BUT_CAPACITY_INSUFFICIENT",
                    blocker="EXIT_TOP_OF_BOOK_CAPACITY_INSUFFICIENT",
                    size_shortfall=str(q-crossing_size),
                )
            else:
                result.update(
                    status="SAMPLED_TOP_LEVEL_SIZE_SUFFICIENT_ONLY",
                    blocker="NO_EXECUTION_OR_SOURCE_AUTHENTICATION_PROOF",
                )
        # Never promise to execute a quantity just because it appeared in a
        # historical single-side order book. No partial or multilevel model.
    except (ValueError, TypeError, OverflowError, KeyError) as exc:
        result["blocker"] = str(exc) or "MALFORMED_INPUT"
    return result


def summarize_historical_observations(
    snapshots: Sequence[Mapping[str, Any]], *, quantity: Any,
) -> dict[str, Any]:
    """Read-only count; repeated visible size cannot be summed across time."""
    q = _positive(quantity)
    results = [evaluate_observed_exit_capacity(
        direction=str(row.get("direction") or ""),
        quantity=q,
        stop=row.get("stop"), target=row.get("target"),
        best_bid=row.get("best_bid"),best_ask=row.get("best_ask"),
        best_bid_size=row.get("best_bid_size"),best_ask_size=row.get("best_ask_size"),
        observed_at_utc=str(row.get("observed_at_utc") or ""),
        quote_source=row.get("quote_source"),
    ) for row in snapshots]
    triggered = [x for x in results if x["trigger_type"] is not None]
    no_capacity = [x for x in triggered
                   if x["status"]=="TRIGGERED_BUT_CAPACITY_INSUFFICIENT"]
    target_blocked = [x for x in no_capacity if x["trigger_type"]=="TAKE_PROFIT"]
    stop_blocked = [x for x in no_capacity if x["trigger_type"]=="STOP_LOSS"]
    identified_sources = sum(x.get("quote_source") not in (None, "UNIDENTIFIED")
                             for x in target_blocked)
    return {
        "observations": len(results),
        "position_quantity": str(q),
        "target_capacity_blocked_observations":len(target_blocked),
        "stop_capacity_blocked_observations":len(stop_blocked),
        "target_blocked_source_identified": identified_sources,
        "max_observed_target_top_book_size":max(
            (Decimal(x["observed_top_of_book_size"]) for x in target_blocked),
            default=None,
        ),
        "samples_are_not_accumulable": True,
        "open_position_preserved": True,
        "counterfactual_only":True,
        "profitability_claim_permitted":False,
        "trade_permission":False,
        "production_promotion_permitted":False,
    }
