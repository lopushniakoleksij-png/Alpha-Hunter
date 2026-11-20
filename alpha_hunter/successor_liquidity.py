"""Research-only, fail-closed pre-entry liquidity sizing for a FUTURE cohort.

NO importing this module from the active R9/R10 execution, management, or scan
paths. This code neither creates an order nor activates paper admission. Its
pre-entry top-of-book check is NOT a promise of liquidity at a later exit.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any

MODEL_VERSION = "successor-liquidity-shadow-v0.1"
FROZEN_COHORT_IDS = {"PAPER_EXECUTION_R9", "PAPER_EXECUTION_R10"}


def _positive(value: Any) -> Decimal | None:
    """Parse finite positive decimal evidence, never interpret booleans as size."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        float_value = float(result)
    except (InvalidOperation, ValueError, OverflowError):
        return None
    return (
        result if result.is_finite() and result > 0
        and math.isfinite(float_value) and float_value > 0 else None
    )


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp.astimezone(timezone.utc)


def _deny(blockers: list[str], *, identity: dict[str, Any]) -> dict[str, Any]:
    return {
        **identity,
        "status": "BLOCKED",
        "blockers": list(dict.fromkeys(blockers)),
        "quantity": None,
        "risk_used_usdt": None,
        "risk_only_quantity": None,
        "entry_book_quantity": None,
        "exit_book_quantity": None,
        "entry_side": None,
        "exit_side": None,
        "shadow_only": True,
        "paper_only": True,
        "paper_authority": False,
        "exchange_authority": False,
        "trade_permission": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }


def assess_successor_liquidity(
    candidate: dict[str, Any], quote: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    """Return an auditable shadow-only *pre-entry* position-size assessment.

    ``policy`` MUST be preregistered for a future cohort before its use as an
    admission rule. No default participation threshold is silently selected.
    Quote snapshot size must be contemporaneous with the candidate decision;
    neither future depth nor multiple market levels are inferred.
    """
    cohort = str(candidate.get("successor_cohort_id") or "").strip()
    run_id = str(candidate.get("source_run_id") or "").strip()
    symbol = str(candidate.get("symbol") or "").strip().upper()
    identity = {
        "model_version": MODEL_VERSION,
        "successor_cohort_id": cohort,
        "source_run_id": run_id,
        "symbol": symbol,
        "quote_source": quote.get("source"),
    }
    blockers: list[str] = []
    if not cohort.startswith("PAPER_EXECUTION_") or cohort in FROZEN_COHORT_IDS:
        blockers.append("SUCCESSOR_COHORT_NOT_PREREGISTERED")
    if not run_id or not symbol or not str(quote.get("source") or "").strip():
        blockers.append("EVIDENCE_IDENTITY_MISSING")
    if (str(quote.get("source_run_id") or "").strip() != run_id
            or str(quote.get("symbol") or "").strip().upper() != symbol):
        blockers.append("QUOTE_IDENTITY_MISMATCH")

    decision_time = _time(candidate.get("observed_at_utc"))
    quote_time = _time(quote.get("captured_at_utc"))
    maximum_age = _positive(policy.get("max_quote_age_seconds"))
    if maximum_age is None:
        blockers.append("QUOTE_FRESHNESS_POLICY_INVALID")
    if decision_time is None or quote_time is None:
        blockers.append("QUOTE_CLOCK_INVALID")
    elif quote_time > decision_time:
        blockers.append("QUOTE_AFTER_DECISION_LOOKAHEAD")
    elif maximum_age is not None and Decimal(str((decision_time - quote_time).total_seconds())) > maximum_age:
        blockers.append("QUOTE_STALE")

    direction = str(candidate.get("direction") or "").upper()
    if direction not in {"LONG", "SHORT"}:
        blockers.append("DIRECTION_INVALID")
    entry = _positive(candidate.get("entry_price"))
    stop = _positive(candidate.get("stop_price"))
    bid = _positive(quote.get("best_bid"))
    ask = _positive(quote.get("best_ask"))
    bid_size = _positive(quote.get("best_bid_size"))
    ask_size = _positive(quote.get("best_ask_size"))
    if (entry is None or stop is None
            or (direction == "LONG" and stop is not None and entry is not None and not stop < entry)
            or (direction == "SHORT" and stop is not None and entry is not None and not entry < stop)):
        blockers.append("RISK_GEOMETRY_INVALID")
    if bid is None or ask is None or (bid is not None and ask is not None and ask < bid):
        blockers.append("TOP_OF_BOOK_PRICE_INVALID")
    if bid_size is None or ask_size is None:
        blockers.append("TOP_OF_BOOK_SIZE_MISSING_OR_INVALID")

    risk_budget = _positive(policy.get("risk_budget_usdt"))
    step = _positive(policy.get("size_multiplier"))
    min_qty = _positive(policy.get("minimum_trade_number"))
    min_notional = _positive(policy.get("minimum_trade_usdt"))
    participation = _positive(policy.get("maximum_book_participation"))
    if risk_budget is None:
        blockers.append("RISK_BUDGET_INVALID")
    if step is None or min_qty is None or min_notional is None:
        blockers.append("INSTRUMENT_LIMITS_MISSING_OR_INVALID")
    if participation is None or participation > 1:
        blockers.append("BOOK_PARTICIPATION_POLICY_INVALID")
    if blockers:
        return _deny(blockers, identity=identity)

    assert all(v is not None for v in (
        entry, stop, bid, ask, bid_size, ask_size, risk_budget, step,
        min_qty, min_notional, participation,
    ))
    entry_book = ask_size if direction == "LONG" else bid_size
    exit_book = bid_size if direction == "LONG" else ask_size
    entry_side = "BUY" if direction == "LONG" else "SELL"
    exit_side = "SELL" if direction == "LONG" else "BUY"
    try:
        risk_quantity = risk_budget / abs(entry - stop)
        # Cap BOTH sides with the same explicit, yet-to-be-frozen conservative
        # participation parameter; never assume a later quote stays this deep.
        upper_bound = min(risk_quantity, entry_book * participation, exit_book * participation)
        quantity = (upper_bound / step).to_integral_value(rounding=ROUND_DOWN) * step
        if not all(math.isfinite(float(v)) for v in (risk_quantity, quantity)):
            return _deny(["SIZE_NUMERIC_OVERFLOW"], identity=identity)
    except (InvalidOperation, OverflowError, ZeroDivisionError):
        return _deny(["SIZE_NUMERIC_OVERFLOW"], identity=identity)
    if quantity <= 0 or quantity < min_qty:
        return _deny(["BELOW_MINIMUM_TRADE_QUANTITY"], identity=identity)
    if quantity * entry < min_notional:
        return _deny(["BELOW_MINIMUM_TRADE_NOTIONAL"], identity=identity)

    used_risk = quantity * abs(entry - stop)
    if used_risk > risk_budget or quantity > entry_book or quantity > exit_book:
        return _deny(["LIQUIDITY_OR_RISK_INVARIANT_BREACH"], identity=identity)
    return {
        **identity,
        "status": "SHADOW_FEASIBLE_AT_ENTRY_SNAPSHOT_ONLY",
        "blockers": [],
        "quantity": float(quantity),
        "risk_used_usdt": float(used_risk),
        "risk_budget_usdt": float(risk_budget),
        "risk_only_quantity": float(risk_quantity),
        "entry_book_quantity": float(entry_book),
        "exit_book_quantity": float(exit_book),
        "maximum_book_participation": float(participation),
        "entry_side": entry_side,
        "exit_side": exit_side,
        "shadow_only": True,
        "paper_only": True,
        "paper_authority": False,
        "exchange_authority": False,
        "trade_permission": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }
