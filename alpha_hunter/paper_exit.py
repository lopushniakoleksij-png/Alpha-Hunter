from __future__ import annotations

import hashlib
import math
from typing import Any

from .paper_execution import _load_model_config
from .paper_lifecycle import PaperState, transition_allowed


MODEL_VERSION = "paper-exit-v0.4"
ATTEMPT_TABLE = "alpha_hunter_paper_exit_attempts_v04"
EXIT_FILL_TABLE = "alpha_hunter_paper_exit_fills_v04"
OPEN_VIEW = "alpha_hunter_paper_protection_open_v04"


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _id(prefix: str, *parts: Any) -> str:
    raw = "|".join([MODEL_VERSION, prefix, *[str(part) for part in parts]])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _safe_fields() -> dict[str, Any]:
    return {
        "paper_only": True,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
    }


def _quote_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("symbol") or "").upper(): row
        for row in snapshot.get("symbols", [])
        if isinstance(row, dict) and "error" not in row and row.get("symbol")
    }


def _attempt(
    position: dict[str, Any],
    quote: dict[str, Any] | None,
    *,
    source_run_id: str,
    observed_at_utc: str,
    outcome: str,
    blockers: list[str],
    triggered_protection_type: str | None = None,
) -> dict[str, Any]:
    return {
        "attempt_id": _id("attempt", position["entry_order_id"], source_run_id),
        "entry_order_id": position["entry_order_id"],
        "decision_id": position["decision_id"],
        "source_run_id": source_run_id,
        "observed_at_utc": observed_at_utc,
        "symbol": position["symbol"],
        "direction": position["direction"],
        "best_bid": quote.get("bid_price") if quote else None,
        "best_ask": quote.get("ask_price") if quote else None,
        "best_bid_size": quote.get("bid_size") if quote else None,
        "best_ask_size": quote.get("ask_size") if quote else None,
        "outcome": outcome,
        "triggered_protection_type": triggered_protection_type,
        "blockers": blockers,
        "evidence": {
            "model_version": MODEL_VERSION,
            "captured_quote_only": True,
            "quote_source": (
                quote.get("_reconciliation_quote_source")
                if quote
                else "MISSING"
            ),
            "exchange_request_added": False,
        },
        **_safe_fields(),
    }


def _exit_event(
    position: dict[str, Any],
    exit_fill: dict[str, Any],
    *,
    source_run_id: str,
    observed_at_utc: str,
    state: PaperState,
) -> dict[str, Any]:
    if not transition_allowed(PaperState.FILLED, state):
        raise ValueError(f"Invalid paper transition FILLED -> {state.value}")
    return {
        "event_id": _id(
            "event",
            position["decision_id"],
            source_run_id,
            int(position["event_sequence"]) + 1,
            state.value,
        ),
        "decision_id": position["decision_id"],
        "sequence": int(position["event_sequence"]) + 1,
        "occurred_at_utc": observed_at_utc,
        "event_type": "PAPER_PROTECTIVE_EXIT_RECONCILED",
        "state": state.value,
        "payload": {
            "entry_order_id": position["entry_order_id"],
            "exit_fill_id": exit_fill["exit_fill_id"],
            "triggered_protective_order_id": exit_fill["triggered_protective_order_id"],
            "protection_type": exit_fill["protection_type"],
            "source_run_id": source_run_id,
            "exit_price": exit_fill["exit_price"],
            "quantity": exit_fill["quantity"],
            "gross_pnl_usdt": exit_fill["gross_pnl_usdt"],
            "paper_net_pnl_ex_funding": exit_fill["paper_net_pnl_ex_funding"],
            "gross_r": exit_fill["gross_r"],
            "net_r_ex_funding": exit_fill["net_r_ex_funding"],
            "exchange_execution": False,
        },
        **_safe_fields(),
    }


def _trigger_state(
    position: dict[str, Any],
    *,
    bid: float,
    ask: float,
) -> tuple[str | None, list[str]]:
    direction = str(position.get("direction") or "").upper()
    stop = _optional_float(position.get("stop_trigger_price"))
    target = _optional_float(position.get("target_trigger_price"))
    if direction not in {"LONG", "SHORT"}:
        return None, ["DIRECTION_INVALID"]
    if stop is None or target is None or stop <= 0 or target <= 0:
        return None, ["PROTECTIVE_TRIGGER_MISSING"]
    if direction == "LONG" and not stop < target:
        return None, ["PROTECTIVE_GEOMETRY_INVALID"]
    if direction == "SHORT" and not target < stop:
        return None, ["PROTECTIVE_GEOMETRY_INVALID"]

    if direction == "LONG":
        stop_hit = bid <= stop
        target_hit = bid >= target
    else:
        stop_hit = ask >= stop
        target_hit = ask <= target

    if stop_hit and target_hit:
        return None, ["PROTECTIVE_TRIGGER_AMBIGUOUS"]
    if stop_hit:
        return "STOP_LOSS", []
    if target_hit:
        return "TAKE_PROFIT", []
    return None, []


def _modeled_exit_fill(
    position: dict[str, Any],
    quote: dict[str, Any],
    *,
    source_run_id: str,
    observed_at_utc: str,
    protection_type: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    direction = str(position["direction"]).upper()
    bid = _optional_float(quote.get("bid_price"))
    ask = _optional_float(quote.get("ask_price"))
    if bid is None or ask is None or bid <= 0 or ask < bid:
        return None, ["TOP_OF_BOOK_PRICE_INVALID"]

    side = "SELL" if direction == "LONG" else "BUY"
    top_size = _optional_float(
        quote.get("bid_size") if side == "SELL" else quote.get("ask_size")
    )
    quantity = _optional_float(position.get("entry_quantity"))
    if top_size is None or top_size <= 0:
        return None, ["TOP_OF_BOOK_SIZE_MISSING"]
    if quantity is None or quantity <= 0:
        return None, ["ENTRY_QUANTITY_INVALID"]
    if top_size + 1e-12 < quantity:
        return None, ["EXIT_TOP_OF_BOOK_CAPACITY_INSUFFICIENT"]

    fee_bps = _optional_float(position.get("public_taker_fee_bps"))
    if fee_bps is None or fee_bps < 0:
        return None, ["TAKER_FEE_EVIDENCE_MISSING"]

    entry_price = _optional_float(position.get("average_entry_fill_price"))
    planned_risk = _optional_float(position.get("planned_risk_usdt"))
    if entry_price is None or entry_price <= 0:
        return None, ["ENTRY_PRICE_INVALID"]
    if planned_risk is None or planned_risk <= 0:
        return None, ["PLANNED_RISK_INVALID"]

    trigger_id = (
        position.get("stop_protective_order_id")
        if protection_type == "STOP_LOSS"
        else position.get("target_protective_order_id")
    )
    if not trigger_id:
        return None, ["TRIGGERED_PROTECTIVE_ORDER_MISSING"]

    cross_price = bid if side == "SELL" else ask
    config = _load_model_config()
    participation = min(1.0, quantity / top_size)
    slippage_bps = min(
        config["maximum_market_slippage_bps"],
        config["base_market_slippage_bps"]
        + participation
        * (
            config["maximum_market_slippage_bps"]
            - config["base_market_slippage_bps"]
        ),
    )
    sign = -1.0 if side == "SELL" else 1.0
    exit_price = cross_price * (1.0 + sign * slippage_bps / 10000.0)
    midpoint = (bid + ask) / 2.0
    spread_per_unit = midpoint - cross_price if side == "SELL" else cross_price - midpoint
    notional = quantity * exit_price
    spread_cost = max(0.0, spread_per_unit * quantity)
    slippage_cost = abs(exit_price - cross_price) * quantity
    exit_fee = notional * fee_bps / 10000.0

    entry_fee = _optional_float(position.get("entry_fee_usdt")) or 0.0
    entry_spread = _optional_float(position.get("entry_spread_cost_usdt")) or 0.0
    entry_slippage = _optional_float(position.get("entry_slippage_cost_usdt")) or 0.0
    gross_pnl = (
        (exit_price - entry_price) * quantity
        if direction == "LONG"
        else (entry_price - exit_price) * quantity
    )
    entry_costs = entry_fee + entry_spread + entry_slippage
    exit_costs = exit_fee + spread_cost + slippage_cost
    net_ex_funding = gross_pnl - entry_costs - exit_costs

    exit_fill_id = _id("exit-fill", position["entry_order_id"], source_run_id)
    return {
        "exit_fill_id": exit_fill_id,
        "entry_order_id": position["entry_order_id"],
        "decision_id": position["decision_id"],
        "source_run_id": source_run_id,
        "triggered_protective_order_id": str(trigger_id),
        "protection_type": protection_type,
        "filled_at_utc": observed_at_utc,
        "symbol": position["symbol"],
        "direction": direction,
        "side": side,
        "quantity": quantity,
        "entry_average_fill_price": entry_price,
        "exit_price": exit_price,
        "notional_usdt": notional,
        "midpoint_reference": midpoint,
        "cross_price_reference": cross_price,
        "spread_cost_usdt": spread_cost,
        "slippage_bps": slippage_bps,
        "slippage_cost_usdt": slippage_cost,
        "fee_bps": fee_bps,
        "fee_usdt": exit_fee,
        "entry_costs_usdt": entry_costs,
        "exit_costs_usdt": exit_costs,
        "gross_pnl_usdt": gross_pnl,
        "paper_net_pnl_ex_funding": net_ex_funding,
        "planned_risk_usdt": planned_risk,
        "gross_r": gross_pnl / planned_risk,
        "net_r_ex_funding": net_ex_funding / planned_risk,
        "funding_bound": False,
        "full_economic_pnl_claim_permitted": False,
        "liquidity_source": str(
            quote.get("_reconciliation_quote_source")
            or "BITGET_TOP_OF_BOOK_SNAPSHOT"
        ),
        "model_quality": "DETERMINISTIC_PAPER_MODEL_NOT_EXCHANGE_EXECUTION",
        **_safe_fields(),
    }, []


def reconcile_active_protections(
    snapshot: dict[str, Any],
    open_positions: list[dict[str, Any]],
    *,
    attempted_entry_order_ids: set[str] | None = None,
    quote_overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Reconcile fully-filled paper positions against active SL/TP protection."""
    source_run_id = str(snapshot.get("run_id") or "")
    observed_at = str(snapshot.get("collected_at_utc") or "")
    if not source_run_id or not observed_at:
        raise ValueError("Protective reconciliation requires immutable run identity")

    quotes = _quote_map(snapshot)
    if quote_overrides:
        quotes.update({
            str(symbol).upper(): dict(quote)
            for symbol, quote in quote_overrides.items()
            if isinstance(quote, dict)
        })
    attempted = attempted_entry_order_ids or set()
    attempts: list[dict[str, Any]] = []
    exit_fills: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for raw in open_positions:
        position = dict(raw)
        entry_order_id = str(position.get("entry_order_id") or "")
        if not entry_order_id or entry_order_id in attempted:
            continue

        quote = quotes.get(str(position.get("symbol") or "").upper())
        quote_observed_at = str((quote or {}).get("_captured_at_utc") or observed_at)
        if quote is None:
            attempts.append(
                _attempt(
                    position,
                    None,
                    source_run_id=source_run_id,
                    observed_at_utc=quote_observed_at,
                    outcome="INPUT_MISSING",
                    blockers=["SYMBOL_QUOTE_MISSING"],
                )
            )
            continue

        if str(position.get("entry_completed_source_run_id") or "") == source_run_id:
            attempts.append(
                _attempt(
                    position,
                    quote,
                    source_run_id=source_run_id,
                    observed_at_utc=quote_observed_at,
                    outcome="AMBIGUOUS",
                    blockers=["ENTRY_AND_EXIT_ORDERING_AMBIGUOUS_SAME_SNAPSHOT"],
                )
            )
            continue

        bid = _optional_float(quote.get("bid_price"))
        ask = _optional_float(quote.get("ask_price"))
        if bid is None or ask is None or bid <= 0 or ask < bid:
            attempts.append(
                _attempt(
                    position,
                    quote,
                    source_run_id=source_run_id,
                    observed_at_utc=quote_observed_at,
                    outcome="INPUT_MISSING",
                    blockers=["TOP_OF_BOOK_PRICE_INVALID"],
                )
            )
            continue

        protection_type, trigger_blockers = _trigger_state(position, bid=bid, ask=ask)
        if trigger_blockers:
            attempts.append(
                _attempt(
                    position,
                    quote,
                    source_run_id=source_run_id,
                    observed_at_utc=quote_observed_at,
                    outcome="AMBIGUOUS",
                    blockers=trigger_blockers,
                )
            )
            continue
        if protection_type is None:
            attempts.append(
                _attempt(
                    position,
                    quote,
                    source_run_id=source_run_id,
                    observed_at_utc=quote_observed_at,
                    outcome="NO_TRIGGER",
                    blockers=[],
                )
            )
            continue

        exit_fill, blockers = _modeled_exit_fill(
            position,
            quote,
            source_run_id=source_run_id,
            observed_at_utc=quote_observed_at,
            protection_type=protection_type,
        )
        if blockers or exit_fill is None:
            attempts.append(
                _attempt(
                    position,
                    quote,
                    source_run_id=source_run_id,
                    observed_at_utc=quote_observed_at,
                    outcome="INPUT_MISSING",
                    blockers=blockers,
                    triggered_protection_type=protection_type,
                )
            )
            continue

        attempts.append(
            _attempt(
                position,
                quote,
                source_run_id=source_run_id,
                observed_at_utc=quote_observed_at,
                outcome=(
                    "STOP_TRIGGERED"
                    if protection_type == "STOP_LOSS"
                    else "TARGET_TRIGGERED"
                ),
                blockers=[],
                triggered_protection_type=protection_type,
            )
        )
        exit_fills.append(exit_fill)
        state = (
            PaperState.STOPPED
            if protection_type == "STOP_LOSS"
            else PaperState.TARGETED
        )
        events.append(
            _exit_event(
                position,
                exit_fill,
                source_run_id=source_run_id,
                observed_at_utc=quote_observed_at,
                state=state,
            )
        )

    return attempts, exit_fills, events
