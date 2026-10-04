from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any

from .paper_execution import _load_model_config
from .paper_lifecycle import PaperState, transition_allowed


MODEL_VERSION = "paper-reconciliation-v0.3"
ATTEMPT_TABLE = "alpha_hunter_paper_reconciliation_attempts_v03"
PROTECTIVE_TABLE = "alpha_hunter_paper_protective_orders_v03"
OPEN_VIEW = "alpha_hunter_paper_reconciliation_open_v08"
ENTRY_ORDER_MAX_AGE_MINUTES = 35


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


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _entry_order_age_minutes(order: dict[str, Any], observed_at_utc: str) -> float | None:
    submitted = _parse_utc(order.get("submitted_at_utc"))
    observed = _parse_utc(observed_at_utc)
    if submitted is None or observed is None:
        return None
    return (observed - submitted).total_seconds() / 60.0


def _terminal_event(
    order: dict[str, Any],
    *,
    occurred_at_utc: str,
    state: PaperState,
    event_type: str,
    blockers: list[str],
) -> dict[str, Any]:
    current = PaperState(str(order["execution_state"]))
    if not transition_allowed(current, state):
        raise ValueError(f"Invalid paper transition {current.value} -> {state.value}")
    return {
        "event_id": _id(
            "event",
            order["decision_id"],
            order["source_run_id"],
            int(order["event_sequence"]) + 1,
            state.value,
        ),
        "decision_id": order["decision_id"],
        "sequence": int(order["event_sequence"]) + 1,
        "occurred_at_utc": occurred_at_utc,
        "event_type": event_type,
        "state": state.value,
        "payload": {
            "order_id": order["order_id"],
            "source_run_id": order["source_run_id"],
            "blockers": blockers,
            "exchange_execution": False,
        },
        **_safe_fields(),
    }


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


def _prospective_average_entry(
    order: dict[str, Any],
    fill: dict[str, Any],
) -> float | None:
    prior_quantity = _optional_float(order.get("filled_quantity")) or 0.0
    prior_average = _optional_float(order.get("average_fill_price"))
    new_quantity = _optional_float(fill.get("quantity"))
    new_price = _optional_float(fill.get("fill_price"))
    if new_quantity is None or new_quantity <= 0 or new_price is None or new_price <= 0:
        return None
    if prior_quantity <= 0:
        return new_price
    if prior_average is None or prior_average <= 0:
        return None
    total = prior_quantity + new_quantity
    return ((prior_average * prior_quantity) + (new_price * new_quantity)) / total


def _event(
    order: dict[str, Any],
    *,
    sequence: int,
    occurred_at_utc: str,
    state: PaperState,
    fill: dict[str, Any],
) -> dict[str, Any]:
    current = PaperState(str(order["execution_state"]))
    if not transition_allowed(current, state):
        raise ValueError(f"Invalid paper transition {current.value} -> {state.value}")
    return {
        "event_id": _id(
            "event", order["decision_id"], order["source_run_id"], sequence, state.value
        ),
        "decision_id": order["decision_id"],
        "sequence": sequence,
        "occurred_at_utc": occurred_at_utc,
        "event_type": "PAPER_ORDER_RECONCILED_FILL",
        "state": state.value,
        "payload": {
            "order_id": order["order_id"],
            "fill_id": fill["fill_id"],
            "source_run_id": order["source_run_id"],
            "fill_quantity": fill["quantity"],
            "previous_filled_quantity": order["filled_quantity"],
            "remaining_after_fill": max(
                0.0, float(order["remaining_quantity"]) - float(fill["quantity"])
            ),
            "fee_usdt": fill["fee_usdt"],
            "spread_cost_usdt": fill["spread_cost_usdt"],
            "slippage_cost_usdt": fill["slippage_cost_usdt"],
            "exchange_execution": False,
        },
        **_safe_fields(),
    }


def _protective_rows(
    *,
    order: dict[str, Any],
    fill: dict[str, Any],
    quantity: float,
    created_at_utc: str,
) -> list[dict[str, Any]]:
    direction = str(order["direction"])
    protective_side = "SELL" if direction == "LONG" else "BUY"
    rows: list[dict[str, Any]] = []
    for protection_type, price_key in (
        ("STOP_LOSS", "stop_price"),
        ("TAKE_PROFIT", "target_price"),
    ):
        trigger_price = _optional_float(order.get(price_key))
        if trigger_price is None or trigger_price <= 0:
            raise ValueError(f"Protective {protection_type} trigger is invalid")
        rows.append(
            {
                "protective_order_id": _id(
                    "protection", order["order_id"], protection_type
                ),
                "entry_order_id": order["order_id"],
                "decision_id": order["decision_id"],
                "activated_by_fill_id": fill["fill_id"],
                "created_at_utc": created_at_utc,
                "symbol": order["symbol"],
                "direction": direction,
                "protection_type": protection_type,
                "side": protective_side,
                "trigger_price": trigger_price,
                "quantity": quantity,
                "reduce_only": True,
                "status": "ACTIVE_PAPER",
                "evidence": {
                    "activation_rule": "ONLY_AFTER_COMPLETE_ENTRY_FILL",
                    "entry_execution_state": "FILLED",
                    "source_run_id": order["source_run_id"],
                    "exchange_submission": False,
                },
                **_safe_fields(),
            }
        )
    return rows


def build_initial_protective_orders(
    decisions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Protect only Release 2.2 fills that completed the entire entry immediately."""
    decision_by_id = {row["decision_id"]: row for row in decisions}
    fill_by_order = {row["order_id"]: row for row in fills}
    rows: list[dict[str, Any]] = []
    for raw_order in orders:
        fill = fill_by_order.get(raw_order["order_id"])
        if fill is None or float(fill["quantity"]) < float(raw_order["quantity"]):
            continue
        decision = decision_by_id[raw_order["decision_id"]]
        order = {
            **raw_order,
            "stop_price": decision["stop_price"],
            "target_price": decision["target_price"],
            "source_run_id": decision["run_id"],
        }
        rows.extend(
            _protective_rows(
                order=order,
                fill=fill,
                quantity=float(raw_order["quantity"]),
                created_at_utc=str(fill["filled_at_utc"]),
            )
        )
    return rows


def _quote_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("symbol") or "").upper(): row
        for row in snapshot.get("symbols", [])
        if isinstance(row, dict) and "error" not in row and row.get("symbol")
    }


def snapshot_has_reconciliation_quotes(snapshot: dict[str, Any]) -> bool:
    return any(
        _optional_float(row.get("bid_price")) is not None
        and _optional_float(row.get("ask_price")) is not None
        for row in _quote_map(snapshot).values()
    )


def _attempt(
    order: dict[str, Any],
    quote: dict[str, Any] | None,
    *,
    outcome: str,
    blockers: list[str],
    observed_at_utc: str,
) -> dict[str, Any]:
    return {
        "attempt_id": _id("attempt", order["order_id"], order["source_run_id"]),
        "order_id": order["order_id"],
        "decision_id": order["decision_id"],
        "source_run_id": order["source_run_id"],
        "observed_at_utc": observed_at_utc,
        "symbol": order["symbol"],
        "prior_state": order["execution_state"],
        "prior_filled_quantity": order["filled_quantity"],
        "prior_remaining_quantity": order["remaining_quantity"],
        "best_bid": quote.get("bid_price") if quote else None,
        "best_ask": quote.get("ask_price") if quote else None,
        "best_bid_size": quote.get("bid_size") if quote else None,
        "best_ask_size": quote.get("ask_size") if quote else None,
        "outcome": outcome,
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


def _modeled_fill(
    order: dict[str, Any], quote: dict[str, Any], observed_at_utc: str
) -> tuple[dict[str, Any] | None, list[str], bool]:
    direction = str(order["direction"])
    bid = _optional_float(quote.get("bid_price"))
    ask = _optional_float(quote.get("ask_price"))
    if bid is None or ask is None or bid <= 0 or ask < bid:
        return None, ["TOP_OF_BOOK_PRICE_INVALID"], False
    top_size = _optional_float(
        quote.get("ask_size") if direction == "LONG" else quote.get("bid_size")
    )
    if top_size is None or top_size <= 0:
        return None, ["TOP_OF_BOOK_SIZE_MISSING"], False

    remaining_quantity = _optional_float(order.get("remaining_quantity"))
    if remaining_quantity is None or remaining_quantity <= 0:
        return None, ["ENTRY_REMAINING_QUANTITY_INVALID"], False

    cross_price = ask if direction == "LONG" else bid
    limit_price = _optional_float(order.get("limit_price"))
    if str(order["order_type"]) == "LIMIT":
        if limit_price is None:
            return None, ["LIMIT_PRICE_MISSING"], False
        crossed = ask <= limit_price if direction == "LONG" else bid >= limit_price
        if not crossed:
            return None, [], False
        if top_size + 1e-12 < remaining_quantity:
            return None, ["TOP_OF_BOOK_CAPACITY_INSUFFICIENT_FOR_ALL_OR_NONE_ENTRY"], False
        # A later scanner observation only proves that a resting limit crossed.
        # It does not prove the current quote was the historical execution price.
        # Use the submitted limit as the conservative executable price so delayed
        # reconciliation cannot manufacture favorable price improvement.
        fill_price = limit_price
        fee_bps = _optional_float(order.get("public_maker_fee_bps"))
        slippage_bps = 0.0
    else:
        fee_bps = _optional_float(order.get("public_taker_fee_bps"))
        if top_size + 1e-12 < remaining_quantity:
            return None, ["TOP_OF_BOOK_CAPACITY_INSUFFICIENT_FOR_ALL_OR_NONE_ENTRY"], False
        config = _load_model_config()
        participation = min(1.0, remaining_quantity / top_size)
        slippage_bps = min(
            config["maximum_market_slippage_bps"],
            config["base_market_slippage_bps"]
            + participation
            * (
                config["maximum_market_slippage_bps"]
                - config["base_market_slippage_bps"]
            ),
        )
        sign = 1.0 if direction == "LONG" else -1.0
        fill_price = cross_price * (1.0 + sign * slippage_bps / 10000.0)
    if fee_bps is None:
        return None, ["FEE_EVIDENCE_MISSING"], False

    quantity = remaining_quantity
    is_limit = str(order["order_type"]) == "LIMIT"
    midpoint = fill_price if is_limit else (bid + ask) / 2.0
    cross_reference = fill_price if is_limit else cross_price
    notional = quantity * fill_price
    spread_per_unit = (
        0.0
        if is_limit
        else (
            cross_price - midpoint
            if direction == "LONG"
            else midpoint - cross_price
        )
    )
    funding_rate = _optional_float(quote.get("funding_rate"))
    fill_sequence = int(order["fill_count"]) + 1
    fill_id = _id("fill", order["order_id"], order["source_run_id"], fill_sequence)
    fill = {
        "fill_id": fill_id,
        "order_id": order["order_id"],
        "decision_id": order["decision_id"],
        "source_run_id": order["source_run_id"],
        "fill_sequence": fill_sequence,
        "filled_at_utc": observed_at_utc,
        "quantity": quantity,
        "fill_price": fill_price,
        "notional_usdt": notional,
        "midpoint_reference": midpoint,
        "cross_price_reference": cross_reference,
        "spread_cost_usdt": max(0.0, spread_per_unit * quantity),
        "slippage_bps": slippage_bps,
        "slippage_cost_usdt": 0.0 if is_limit else abs(fill_price - cross_price) * quantity,
        "fee_bps": fee_bps,
        "fee_usdt": notional * fee_bps / 10000.0,
        "funding_rate_snapshot": funding_rate,
        "projected_next_funding_usdt": (
            notional * funding_rate * (1.0 if direction == "LONG" else -1.0)
            if funding_rate is not None
            else None
        ),
        "accrued_funding_usdt": 0.0,
        "funding_status": "NOT_ACCRUED",
        "liquidity_source": str(
            quote.get("_reconciliation_quote_source")
            or "BITGET_TOP_OF_BOOK_SNAPSHOT"
        ),
        "model_quality": "DETERMINISTIC_PAPER_MODEL_NOT_EXCHANGE_EXECUTION",
        **_safe_fields(),
    }
    completed = quantity >= float(order["remaining_quantity"])
    return fill, [], completed


def reconcile_open_orders(
    snapshot: dict[str, Any],
    open_orders: list[dict[str, Any]],
    *,
    attempted_order_ids: set[str] | None = None,
    quote_overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Reconcile each prior open order once against this run's captured quote."""
    run_id = str(snapshot.get("run_id") or "")
    observed_at = str(snapshot.get("collected_at_utc") or "")
    if not run_id or not observed_at:
        raise ValueError("Reconciliation requires immutable run identity")
    quotes = _quote_map(snapshot)
    if quote_overrides:
        quotes.update({
            str(symbol).upper(): dict(quote)
            for symbol, quote in quote_overrides.items()
            if isinstance(quote, dict)
        })
    attempted = attempted_order_ids or set()
    attempts: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    protections: list[dict[str, Any]] = []

    for raw in open_orders:
        order = dict(raw)
        if str(order.get("order_id")) in attempted:
            continue
        order["source_run_id"] = run_id

        prior_filled_quantity = _optional_float(order.get("filled_quantity")) or 0.0
        remaining_quantity = _optional_float(order.get("remaining_quantity")) or 0.0
        execution_state = str(order.get("execution_state") or "")

        if execution_state == PaperState.RECONCILIATION_REQUIRED.value:
            # Initial fill evidence was incomplete. Do not turn a failed market
            # decision into a delayed fill on a later snapshot. Keep the order
            # fail-closed until the already-frozen 35-minute entry age expires.
            if prior_filled_quantity > 0:
                attempts.append(
                    _attempt(
                        order,
                        None,
                        outcome="INPUT_MISSING",
                        blockers=[
                            "RECONCILIATION_REQUIRED_WITH_EXISTING_FILL_UNSUPPORTED"
                        ],
                        observed_at_utc=observed_at,
                    )
                )
                continue

            age_minutes = _entry_order_age_minutes(order, observed_at)
            if age_minutes is None:
                attempts.append(
                    _attempt(
                        order,
                        None,
                        outcome="INPUT_MISSING",
                        blockers=["ENTRY_ORDER_AGE_UNAVAILABLE"],
                        observed_at_utc=observed_at,
                    )
                )
                continue

            if age_minutes > ENTRY_ORDER_MAX_AGE_MINUTES:
                blockers = ["ENTRY_ORDER_EXPIRED_35M"]
                attempts.append(
                    _attempt(
                        order,
                        None,
                        outcome="EXPIRED",
                        blockers=blockers,
                        observed_at_utc=observed_at,
                    )
                )
                events.append(
                    _terminal_event(
                        order,
                        occurred_at_utc=observed_at,
                        state=PaperState.EXPIRED,
                        event_type="PAPER_RECONCILIATION_REQUIRED_ENTRY_EXPIRED",
                        blockers=blockers,
                    )
                )
                continue

            attempts.append(
                _attempt(
                    order,
                    None,
                    outcome="INPUT_MISSING",
                    blockers=["RECONCILIATION_REQUIRED_NO_DELAYED_FILL"],
                    observed_at_utc=observed_at,
                )
            )
            continue

        if prior_filled_quantity > 0 and remaining_quantity > 0:
            blockers = ["LEGACY_PARTIAL_ENTRY_NOT_R8_ELIGIBLE"]
            attempts.append(
                _attempt(
                    order,
                    None,
                    outcome="QUARANTINED_LEGACY_PARTIAL",
                    blockers=blockers,
                    observed_at_utc=observed_at,
                )
            )
            events.append(
                _terminal_event(
                    order,
                    occurred_at_utc=observed_at,
                    state=PaperState.RECONCILIATION_REQUIRED,
                    event_type="PAPER_LEGACY_PARTIAL_QUARANTINED",
                    blockers=blockers,
                )
            )
            continue

        age_minutes = _entry_order_age_minutes(order, observed_at)
        if (
            prior_filled_quantity <= 0
            and age_minutes is not None
            and age_minutes > ENTRY_ORDER_MAX_AGE_MINUTES
        ):
            blockers = ["ENTRY_ORDER_EXPIRED_35M"]
            attempts.append(
                _attempt(
                    order,
                    None,
                    outcome="EXPIRED",
                    blockers=blockers,
                    observed_at_utc=observed_at,
                )
            )
            events.append(
                _terminal_event(
                    order,
                    occurred_at_utc=observed_at,
                    state=PaperState.EXPIRED,
                    event_type="PAPER_ENTRY_ORDER_EXPIRED",
                    blockers=blockers,
                )
            )
            continue

        quote = quotes.get(str(order.get("symbol") or "").upper())
        quote_observed_at = str(
            (quote or {}).get("_captured_at_utc")
            or observed_at
        )
        if quote is None:
            attempts.append(
                _attempt(
                    order,
                    None,
                    outcome="INPUT_MISSING",
                    blockers=["SYMBOL_QUOTE_MISSING"],
                    observed_at_utc=quote_observed_at,
                )
            )
            continue
        fill, blockers, completed = _modeled_fill(order, quote, quote_observed_at)
        if blockers:
            capacity_only = blockers == [
                "TOP_OF_BOOK_CAPACITY_INSUFFICIENT_FOR_ALL_OR_NONE_ENTRY"
            ]
            attempts.append(
                _attempt(
                    order,
                    quote,
                    outcome="NO_FULL_CAPACITY" if capacity_only else "INPUT_MISSING",
                    blockers=blockers,
                    observed_at_utc=quote_observed_at,
                )
            )
            continue
        if fill is None:
            attempts.append(
                _attempt(
                    order,
                    quote,
                    outcome="NO_CROSS",
                    blockers=[],
                    observed_at_utc=quote_observed_at,
                )
            )
            continue

        if completed:
            completed_average = _prospective_average_entry(order, fill)
            direction = str(order.get("direction") or "").upper()
            if (
                completed_average is None
                or not _entry_geometry_valid(
                    direction,
                    completed_average,
                    order.get("stop_price"),
                    order.get("target_price"),
                )
            ):
                attempts.append(
                    _attempt(
                        order,
                        quote,
                        outcome="INPUT_MISSING",
                        blockers=["COMPLETED_ENTRY_GEOMETRY_INVALID"],
                        observed_at_utc=quote_observed_at,
                    )
                )
                continue

        attempts.append(
            _attempt(
                order,
                quote,
                outcome="FILL_MODELED",
                blockers=[],
                observed_at_utc=quote_observed_at,
            )
        )
        fills.append(fill)
        state = PaperState.FILLED if completed else PaperState.PARTIALLY_FILLED
        events.append(
            _event(
                order,
                sequence=int(order["event_sequence"]) + 1,
                occurred_at_utc=quote_observed_at,
                state=state,
                fill=fill,
            )
        )
        if completed:
            protections.extend(
                _protective_rows(
                    order=order,
                    fill=fill,
                    quantity=float(order["ordered_quantity"]),
                    created_at_utc=quote_observed_at,
                )
            )
    return attempts, fills, events, protections
