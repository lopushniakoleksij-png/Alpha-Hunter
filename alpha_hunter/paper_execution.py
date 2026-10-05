from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from typing import Any

from .paper_lifecycle import PaperState, _event, transition_allowed


MODEL_VERSION = "paper-execution-v0.2"
ORDER_TABLE = "alpha_hunter_paper_orders_v02"
FILL_TABLE = "alpha_hunter_paper_fills_v02"


def _load_model_config() -> dict[str, float]:
    defaults = {
        "virtual_equity_usdt": 1000.0,
        "risk_fraction": 0.0025,
        "base_market_slippage_bps": 1.0,
        "maximum_market_slippage_bps": 5.0,
    }
    try:
        raw = json.loads(
            (Path(__file__).resolve().parents[1] / "config.json").read_text(
                encoding="utf-8"
            )
        ).get("paper_execution", {})
    except (OSError, json.JSONDecodeError):
        raw = {}
    for key in defaults:
        try:
            defaults[key] = float(raw.get(key, defaults[key]))
        except (TypeError, ValueError):
            pass
    return defaults


def _optional_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _id(prefix: str, *parts: Any) -> str:
    raw = "|".join([MODEL_VERSION, prefix, *[str(part) for part in parts]])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _entry_geometry_valid(
    direction: str,
    entry_price: float,
    stop_price: Any,
    target_price: Any,
) -> bool:
    stop = _optional_float(stop_price)
    target = _optional_float(target_price)
    if stop is None or target is None:
        return False
    if direction == "LONG":
        return stop < entry_price < target
    if direction == "SHORT":
        return target < entry_price < stop
    return False


def _normalized_quantity(value: float, multiplier: Any) -> float | None:
    try:
        step = Decimal(str(multiplier))
        quantity = Decimal(str(value))
        if step <= 0 or quantity <= 0:
            return None
        units = (quantity / step).quantize(Decimal("1"), rounding=ROUND_DOWN)
        normalized = units * step
        return float(normalized) if normalized > 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _submission_event(
    decision: dict[str, Any], order: dict[str, Any]
) -> dict[str, Any]:
    if not transition_allowed(PaperState.AUTHORIZED, PaperState.SUBMITTED):
        raise ValueError("Invalid paper transition AUTHORIZED -> SUBMITTED")
    return _event(
        decision,
        3,
        PaperState.SUBMITTED,
        "PAPER_ORDER_SUBMITTED",
        {
            "order_id": order["order_id"],
            "order_type": order["order_type"],
            "quantity": order["quantity"],
            "sizing_source": order["sizing_source"],
            "exchange_submission": False,
        },
    )


def _cancelled_event(
    decision: dict[str, Any], blockers: list[str]
) -> dict[str, Any]:
    if not transition_allowed(PaperState.AUTHORIZED, PaperState.CANCELLED):
        raise ValueError("Invalid paper transition AUTHORIZED -> CANCELLED")
    return _event(
        decision,
        3,
        PaperState.CANCELLED,
        "PAPER_SUBMISSION_BLOCKED",
        {"blockers": blockers, "exchange_submission": False},
    )


def _order_from_decision(
    decision: dict[str, Any], config: dict[str, float]
) -> tuple[dict[str, Any] | None, list[str]]:
    direction = str(decision.get("direction") or "").upper()
    entry = _optional_float(decision.get("entry_price"))
    stop = _optional_float(decision.get("stop_price"))
    target = _optional_float(decision.get("target_price"))
    evidence = decision.get("evidence") or {}
    instrument = evidence.get("instrument_constraints") or {}
    blockers: list[str] = []
    if direction not in {"LONG", "SHORT"}:
        blockers.append("DIRECTION_INVALID")
    if (
        entry is None
        or stop is None
        or target is None
        or entry <= 0
        or stop <= 0
        or target <= 0
        or not _entry_geometry_valid(direction, entry, stop, target)
    ):
        blockers.append("RISK_GEOMETRY_INVALID")

    virtual_equity = config["virtual_equity_usdt"]
    risk_fraction = config["risk_fraction"]
    if virtual_equity <= 0 or not 0 < risk_fraction <= 0.01:
        blockers.append("PAPER_RISK_POLICY_INVALID")
    if blockers:
        return None, blockers

    assert entry is not None and stop is not None
    planned_risk = virtual_equity * risk_fraction
    raw_quantity = planned_risk / abs(entry - stop)
    quantity = _normalized_quantity(raw_quantity, instrument.get("size_multiplier"))
    if quantity is None:
        blockers.append("BITGET_SIZE_PRECISION_MISSING_OR_INVALID")
        return None, blockers

    minimum_quantity = _optional_float(instrument.get("minimum_trade_number"))
    minimum_notional = _optional_float(instrument.get("minimum_trade_usdt"))
    if minimum_quantity is not None and quantity < minimum_quantity:
        blockers.append("BELOW_MINIMUM_TRADE_QUANTITY")
    if minimum_notional is not None and quantity * entry < minimum_notional:
        blockers.append("BELOW_MINIMUM_TRADE_NOTIONAL")
    if blockers:
        return None, blockers

    action_status = str(decision.get("action_status") or "")
    order_type = "MARKET" if action_status == "EXECUTE_NOW_PAPER" else "LIMIT"
    order_id = _id("order", decision["decision_id"])
    return {
        "order_id": order_id,
        "decision_id": decision["decision_id"],
        "model_version": MODEL_VERSION,
        "submitted_at_utc": decision["observed_at_utc"],
        "symbol": decision["symbol"],
        "direction": direction,
        "order_type": order_type,
        "limit_price": entry if order_type == "LIMIT" else None,
        "quantity": quantity,
        "virtual_equity_usdt": virtual_equity,
        "risk_fraction": risk_fraction,
        "planned_risk_usdt": planned_risk,
        "sizing_source": "VIRTUAL_PAPER_CAPITAL",
        "best_bid": decision.get("best_bid"),
        "best_ask": decision.get("best_ask"),
        "best_bid_size": decision.get("best_bid_size"),
        "best_ask_size": decision.get("best_ask_size"),
        "public_maker_fee_bps": decision.get("public_maker_fee_bps"),
        "public_taker_fee_bps": decision.get("public_taker_fee_bps"),
        "evidence": {
            "raw_quantity": raw_quantity,
            "size_multiplier": instrument.get("size_multiplier"),
            "minimum_trade_number": instrument.get("minimum_trade_number"),
            "minimum_trade_usdt": instrument.get("minimum_trade_usdt"),
            "risk_policy": "0.25_PERCENT_OF_EXPLICIT_VIRTUAL_EQUITY",
            "not_live_account_equity": True,
        },
        "paper_only": True,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
    }, []


def _fill_from_order(
    decision: dict[str, Any], order: dict[str, Any], config: dict[str, float]
) -> tuple[dict[str, Any] | None, list[str]]:
    direction = order["direction"]
    bid = _optional_float(order.get("best_bid"))
    ask = _optional_float(order.get("best_ask"))
    top_size = _optional_float(
        order.get("best_ask_size") if direction == "LONG" else order.get("best_bid_size")
    )
    if bid is None or ask is None or bid <= 0 or ask < bid:
        return None, ["TOP_OF_BOOK_PRICE_INVALID"]
    if top_size is None or top_size <= 0:
        return None, ["TOP_OF_BOOK_SIZE_MISSING"]

    required_quantity = _optional_float(order.get("quantity"))
    if required_quantity is None or required_quantity <= 0:
        return None, ["ENTRY_QUANTITY_INVALID"]

    cross_price = ask if direction == "LONG" else bid
    if order["order_type"] == "LIMIT":
        limit_price = float(order["limit_price"])
        crossed = ask <= limit_price if direction == "LONG" else bid >= limit_price
        if not crossed:
            return None, []
        if top_size + 1e-12 < required_quantity:
            return None, []
        fill_price = min(ask, limit_price) if direction == "LONG" else max(bid, limit_price)
        fee_bps = _optional_float(order.get("public_maker_fee_bps"))
        slippage_bps = 0.0
    else:
        fee_bps = _optional_float(order.get("public_taker_fee_bps"))
        if fee_bps is None:
            return None, ["TAKER_FEE_EVIDENCE_MISSING"]
        if top_size + 1e-12 < required_quantity:
            return None, ["TOP_OF_BOOK_CAPACITY_INSUFFICIENT_FOR_ALL_OR_NONE_ENTRY"]
        participation = min(1.0, required_quantity / top_size)
        slippage_bps = min(
            config["maximum_market_slippage_bps"],
            config["base_market_slippage_bps"]
            + participation * (
                config["maximum_market_slippage_bps"]
                - config["base_market_slippage_bps"]
            ),
        )
        direction_sign = 1.0 if direction == "LONG" else -1.0
        fill_price = cross_price * (1.0 + direction_sign * slippage_bps / 10000.0)
    if fee_bps is None:
        return None, ["MAKER_FEE_EVIDENCE_MISSING"]

    if not _entry_geometry_valid(
        str(direction).upper(),
        fill_price,
        decision.get("stop_price"),
        decision.get("target_price"),
    ):
        return None, ["ENTRY_FILL_GEOMETRY_INVALID"]

    fill_quantity = required_quantity
    midpoint = (bid + ask) / 2.0
    notional = fill_quantity * fill_price
    spread_per_unit = (cross_price - midpoint) if direction == "LONG" else (midpoint - cross_price)
    slippage_per_unit = abs(fill_price - cross_price)
    funding_rate = _optional_float((decision.get("evidence") or {}).get("funding_rate"))
    projected_funding = (
        notional * funding_rate * (1.0 if direction == "LONG" else -1.0)
        if funding_rate is not None
        else None
    )
    fill_id = _id("fill", order["order_id"], 1)
    return {
        "fill_id": fill_id,
        "order_id": order["order_id"],
        "decision_id": decision["decision_id"],
        "source_run_id": decision["run_id"],
        "fill_sequence": 1,
        "filled_at_utc": decision["observed_at_utc"],
        "quantity": fill_quantity,
        "fill_price": fill_price,
        "notional_usdt": notional,
        "midpoint_reference": midpoint,
        "cross_price_reference": cross_price,
        "spread_cost_usdt": max(0.0, spread_per_unit * fill_quantity),
        "slippage_bps": slippage_bps,
        "slippage_cost_usdt": slippage_per_unit * fill_quantity,
        "fee_bps": fee_bps,
        "fee_usdt": notional * fee_bps / 10000.0,
        "funding_rate_snapshot": funding_rate,
        "projected_next_funding_usdt": projected_funding,
        "accrued_funding_usdt": 0.0,
        "funding_status": "NOT_ACCRUED",
        "liquidity_source": "BITGET_TOP_OF_BOOK_SNAPSHOT",
        "model_quality": "DETERMINISTIC_PAPER_MODEL_NOT_EXCHANGE_EXECUTION",
        "paper_only": True,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
    }, []


def _successor_identity_fields(
    decision: dict[str, Any],
    successor_identity: dict[str, Any] | None,
    *,
    required: bool,
) -> dict[str, str] | None:
    if successor_identity is None:
        return None if required else {}
    activation_id = str(successor_identity.get("activation_id") or "")
    spec_id = str(successor_identity.get("spec_id") or "")
    fingerprint = str(
        successor_identity.get("scientific_fingerprint_sha256") or ""
    ).lower()
    source_run_id = str(decision.get("run_id") or "")
    valid_fingerprint = (
        len(fingerprint) == 64
        and all(char in "0123456789abcdef" for char in fingerprint)
    )
    if (
        activation_id != "PAPER_EXECUTION_R10"
        or not spec_id
        or not valid_fingerprint
        or not source_run_id
    ):
        return None
    return {
        "successor_activation_id": activation_id,
        "successor_spec_id": spec_id,
        "successor_scientific_fingerprint_sha256": fingerprint,
        "successor_source_run_id": source_run_id,
    }


def paper_exposure_key(decision: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(decision.get("symbol") or "").upper(),
        str(decision.get("strategy_id") or ""),
        str(decision.get("direction") or "").upper(),
    )


def build_initial_paper_execution(
    decisions: list[dict[str, Any]],
    *,
    active_exposure_keys: set[tuple[str, str, str]] | None = None,
    execution_gate_open: bool = True,
    execution_gate_blocker: str = "PAPER_R8_INTEGRITY_NOT_ACTIVATED",
    successor_identity: dict[str, Any] | None = None,
    successor_identity_required: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Create deterministic paper submissions and at most one top-of-book fill.

    This is a simulation only. It never imports or calls an exchange client. A limit
    order remains SUBMITTED until later reconciliation when the captured quote does
    not cross it. Funding is projected but never booked before it accrues.
    """
    config = _load_model_config()
    orders: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    occupied = set(active_exposure_keys or set())
    for decision in decisions:
        if decision.get("paper_authority") is not True:
            continue
        if not execution_gate_open:
            events.append(
                _cancelled_event(decision, [execution_gate_blocker])
            )
            continue

        successor_fields = _successor_identity_fields(
            decision,
            successor_identity,
            required=successor_identity_required,
        )
        if successor_fields is None:
            events.append(
                _cancelled_event(decision, ["PAPER_SUCCESSOR_IDENTITY_INVALID"])
            )
            continue

        exposure_key = paper_exposure_key(decision)
        if not all(exposure_key):
            events.append(
                _cancelled_event(decision, ["PAPER_EXPOSURE_KEY_INVALID"])
            )
            continue
        if exposure_key in occupied:
            events.append(
                _cancelled_event(decision, ["ACTIVE_PAPER_EXPOSURE_EXISTS"])
            )
            continue

        order, blockers = _order_from_decision(decision, config)
        if order is None:
            events.append(_cancelled_event(decision, blockers))
            continue
        order.update(successor_fields)
        orders.append(order)
        occupied.add(exposure_key)
        events.append(_submission_event(decision, order))
        fill, fill_blockers = _fill_from_order(decision, order, config)
        if fill_blockers:
            if not transition_allowed(
                PaperState.SUBMITTED, PaperState.RECONCILIATION_REQUIRED
            ):
                raise ValueError(
                    "Invalid paper transition SUBMITTED -> RECONCILIATION_REQUIRED"
                )
            events.append(
                _event(
                    decision,
                    4,
                    PaperState.RECONCILIATION_REQUIRED,
                    "PAPER_FILL_EVIDENCE_INCOMPLETE",
                    {"order_id": order["order_id"], "blockers": fill_blockers},
                )
            )
            continue
        if fill is None:
            continue
        fills.append(fill)
        state = (
            PaperState.FILLED
            if fill["quantity"] >= order["quantity"]
            else PaperState.PARTIALLY_FILLED
        )
        if not transition_allowed(PaperState.SUBMITTED, state):
            raise ValueError(f"Invalid paper transition SUBMITTED -> {state.value}")
        events.append(
            _event(
                decision,
                4,
                state,
                "PAPER_FILL_MODELED",
                {
                    "order_id": order["order_id"],
                    "fill_id": fill["fill_id"],
                    "fill_quantity": fill["quantity"],
                    "order_quantity": order["quantity"],
                    "fee_usdt": fill["fee_usdt"],
                    "spread_cost_usdt": fill["spread_cost_usdt"],
                    "slippage_cost_usdt": fill["slippage_cost_usdt"],
                    "funding_status": fill["funding_status"],
                    "exchange_execution": False,
                },
            )
        )
    return orders, fills, events
