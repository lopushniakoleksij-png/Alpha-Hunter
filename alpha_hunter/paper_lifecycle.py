from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from .action_queue import build_action_queue_rows, safe_optional_float


CONTRACT_VERSION = "paper-lifecycle-v0.1"
DECISION_TABLE = "alpha_hunter_paper_decisions_v01"
EVENT_TABLE = "alpha_hunter_paper_events_v01"


class PaperState(str, Enum):
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    WATCHING = "WATCHING"
    BLOCKED = "BLOCKED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    STOPPED = "STOPPED"
    TARGETED = "TARGETED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


ALLOWED_TRANSITIONS: dict[PaperState, frozenset[PaperState]] = {
    PaperState.CREATED: frozenset(
        {PaperState.AUTHORIZED, PaperState.WATCHING, PaperState.BLOCKED}
    ),
    PaperState.AUTHORIZED: frozenset(
        {PaperState.SUBMITTED, PaperState.CANCELLED, PaperState.EXPIRED}
    ),
    PaperState.WATCHING: frozenset(
        {PaperState.AUTHORIZED, PaperState.CANCELLED, PaperState.EXPIRED}
    ),
    PaperState.SUBMITTED: frozenset(
        {
            PaperState.PARTIALLY_FILLED,
            PaperState.FILLED,
            PaperState.CANCELLED,
            PaperState.EXPIRED,
            PaperState.RECONCILIATION_REQUIRED,
        }
    ),
    PaperState.PARTIALLY_FILLED: frozenset(
        {
            PaperState.PARTIALLY_FILLED,
            PaperState.FILLED,
            PaperState.CANCELLED,
            PaperState.EXPIRED,
            PaperState.RECONCILIATION_REQUIRED,
        }
    ),
    PaperState.FILLED: frozenset(
        {
            PaperState.STOPPED,
            PaperState.TARGETED,
            PaperState.RECONCILIATION_REQUIRED,
        }
    ),
    PaperState.BLOCKED: frozenset(),
    PaperState.CANCELLED: frozenset(),
    PaperState.EXPIRED: frozenset(),
    PaperState.STOPPED: frozenset(),
    PaperState.TARGETED: frozenset(),
    # Fail-closed R8 recovery only. A reconciliation-required entry must never
    # be filled later; it may only age out under the frozen entry-age contract.
    PaperState.RECONCILIATION_REQUIRED: frozenset({PaperState.EXPIRED}),
}


def transition_allowed(current: PaperState, target: PaperState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash_id(prefix: str, *parts: Any) -> str:
    raw = "|".join([CONTRACT_VERSION, prefix, *[str(part) for part in parts]])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _source_strategy(row: dict[str, Any]) -> tuple[str | None, str | None]:
    action = row.get("_action") or {}
    strategy = row.get("_strategy_payload") or {}
    strategy_id = action.get("strategy_id") or strategy.get("strategy_id")
    strategy_name = action.get("strategy_name") or strategy.get("strategy_name")
    if strategy_id is None and not row.get("_strategy"):
        strategy_id = "V7"
        strategy_name = "canonical-v7"
    return (
        str(strategy_id) if strategy_id is not None else None,
        str(strategy_name) if strategy_name is not None else None,
    )


def _decision_row(
    snapshot: dict[str, Any],
    row: dict[str, Any],
    *,
    disposition: str,
) -> dict[str, Any]:
    action = dict(row.get("_action") or {})
    run_id = str(snapshot.get("run_id") or "")
    observed_at = str(snapshot.get("collected_at_utc") or "")
    symbol = str(row.get("symbol") or "").upper()
    strategy_id, strategy_name = _source_strategy(row)
    identity = {
        "run_id": run_id,
        "symbol": symbol,
        "strategy_id": strategy_id,
        "direction": action.get("direction"),
        "status": action.get("status"),
        "entry": action.get("entry"),
        "stop": action.get("stop"),
        "target": action.get("target"),
        "blockers": action.get("blockers") or [],
        "disposition": disposition,
    }
    decision_id = _hash_id("decision", _canonical_json(identity))
    market = row.get("_market_row") if isinstance(row.get("_market_row"), dict) else row
    validation_identity = snapshot.get("validation_identity")
    if not isinstance(validation_identity, dict):
        validation_identity = {}
    run_source = str(validation_identity.get("run_source") or "").upper()
    runtime_role = str(validation_identity.get("runtime_role") or "").upper()
    paper_authority_source_ok = (
        run_source == "RENDER_CRON" and runtime_role == "RENDER_CRON"
    )

    instrument = market.get("instrument_constraints", {})
    if not isinstance(instrument, dict):
        instrument = {}
    return {
        "decision_id": decision_id,
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "observed_at_utc": observed_at,
        "symbol": symbol,
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "direction": str(action.get("direction") or "").upper() or None,
        "action_status": str(action.get("status") or "BLOCKED"),
        "disposition": disposition,
        "entry_price": safe_optional_float(action.get("entry")),
        "stop_price": safe_optional_float(action.get("stop")),
        "target_price": safe_optional_float(action.get("target")),
        "reward_risk": safe_optional_float(action.get("rr")),
        "best_bid": safe_optional_float(market.get("bid_price")),
        "best_ask": safe_optional_float(market.get("ask_price")),
        "best_bid_size": safe_optional_float(market.get("bid_size")),
        "best_ask_size": safe_optional_float(market.get("ask_size")),
        "public_maker_fee_bps": safe_optional_float(
            instrument.get("public_maker_fee_bps")
        ),
        "public_taker_fee_bps": safe_optional_float(
            instrument.get("public_taker_fee_bps")
        ),
        "cost_floor_pct": safe_optional_float(action.get("cost_floor_pct")),
        "blockers": action.get("blockers") or [],
        "evidence": {
            "action": action,
            "market_state": market.get("state"),
            "candidate_source_state": row.get("state"),
            "market_phase": market.get("market_phase"),
            "opportunity_timing": market.get("opportunity_timing"),
            "instrument_constraints": instrument,
            "funding_rate": safe_optional_float(market.get("funding_rate")),
            "funding_interval_hours": market.get("funding_interval_hours"),
            "next_funding_time_ms": market.get("next_funding_time_ms"),
            "canonical_market_freshness": snapshot.get("canonical_market_freshness"),
            "validation_identity": validation_identity,
            "paper_authority_source_gate": {
                "required_run_source": "RENDER_CRON",
                "required_runtime_role": "RENDER_CRON",
                "observed_run_source": run_source,
                "observed_runtime_role": runtime_role,
                "passed": paper_authority_source_ok,
            },
        },
        "paper_only": True,
        "paper_authority": action.get("status")
        in {"EXECUTE_NOW_PAPER", "PLACE_LIMIT_PAPER"}
        and disposition == "CANONICAL"
        and paper_authority_source_ok,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
    }


def _event(
    decision: dict[str, Any],
    sequence: int,
    state: PaperState,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_id": _hash_id("event", decision["decision_id"], sequence, state.value),
        "decision_id": decision["decision_id"],
        "sequence": sequence,
        "occurred_at_utc": decision["observed_at_utc"],
        "event_type": event_type,
        "state": state.value,
        "payload": payload,
        "paper_only": True,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
    }


def _initial_events(decision: dict[str, Any]) -> list[dict[str, Any]]:
    events = [
        _event(
            decision,
            1,
            PaperState.CREATED,
            "DECISION_CREATED",
            {
                "contract_version": CONTRACT_VERSION,
                "source_run_id": decision["run_id"],
                "disposition": decision["disposition"],
            },
        )
    ]
    status = decision["action_status"]
    if decision["paper_authority"]:
        target = PaperState.AUTHORIZED
        event_type = "PAPER_DECISION_AUTHORIZED"
    elif status == "WAIT_FOR_TRIGGER" and decision["disposition"] == "CANONICAL":
        target = PaperState.WATCHING
        event_type = "WATCH_STARTED"
    else:
        target = PaperState.BLOCKED
        event_type = "DECISION_BLOCKED"
    if not transition_allowed(PaperState.CREATED, target):
        raise ValueError(f"Invalid initial paper transition CREATED -> {target.value}")
    events.append(
        _event(
            decision,
            2,
            target,
            event_type,
            {
                "action_status": status,
                "blockers": decision["blockers"],
                "paper_authority": decision["paper_authority"],
                "exchange_authority": False,
            },
        )
    )
    return events


def build_initial_paper_lifecycle(
    snapshot: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bind final Action Queue evidence to a deterministic paper state machine.

    This function deliberately stops at AUTHORIZED/WATCHING/BLOCKED. Release 2.2
    owns simulated submission and fill behavior. No exchange-writing adapter is
    accepted or invoked here.
    """
    if not snapshot.get("run_id") or not snapshot.get("collected_at_utc"):
        raise ValueError("Paper lifecycle requires immutable run identity")
    canonical, blocked, suppressed = build_action_queue_rows(snapshot)
    classified = [
        *[(row, "CANONICAL") for row in canonical],
        *[(row, "BLOCKED") for row in blocked],
        *[(row, "SUPERSEDED") for row in suppressed],
    ]
    decisions = [
        _decision_row(snapshot, row, disposition=disposition)
        for row, disposition in classified
    ]
    events = [event for decision in decisions for event in _initial_events(decision)]
    return decisions, events
