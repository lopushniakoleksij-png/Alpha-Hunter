from datetime import datetime, timezone
from pathlib import Path

from pglast import parse_sql

from alpha_hunter.paper_lifecycle import (
    PaperState,
    build_initial_paper_lifecycle,
    transition_allowed,
)
from alpha_hunter.paper_execution import build_initial_paper_execution


def _strategy(direction="LONG", *, strategy_id="S1"):
    return {
        "strategy_id": strategy_id,
        "strategy_name": "Paper regression",
        "status": "SHADOW_CANDIDATE",
        "action": "EXECUTE_NOW",
        "direction": direction,
        "entry": 10.0,
        "stop": 9.0 if direction == "LONG" else 11.0,
        "target": 15.0 if direction == "LONG" else 5.0,
        "rr": 5.0,
        "signal_score": 8.0,
        "shadow_only": True,
        "trade_permission": False,
    }


def _market(strategies):
    return {
        "symbol": "TESTUSDT",
        "last_price": 10.0,
        "bid_price": 9.99,
        "ask_price": 10.01,
        "instrument_constraints": {
            "price_place": 2,
            "price_end_step": "1",
            "public_taker_fee_bps": 6.0,
        },
        "state": "DIRECTION_EMERGING_LONG",
        "market_phase": "IGNITION",
        "opportunity_timing": "EARLY",
        "behaviour_score": 7.0,
        "v7_trade_ready": False,
        "execution_setup": {"checks": {}},
        "intelligence": {"huge_rr_score": 7.0},
        "multi_strategy_engine": {"strategies": strategies},
    }


def _snapshot(strategies):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "run_id": "run-release-2-1",
        "collected_at_utc": now,
        "canonical_market_freshness": {"verified": True},
        "validation_identity": {"run_source": "TEST"},
        "symbols": [_market(strategies)],
    }


def test_canonical_paper_action_becomes_authorized_without_exchange_authority():
    decisions, events = build_initial_paper_lifecycle(_snapshot([_strategy()]))

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["action_status"] == "EXECUTE_NOW_PAPER"
    assert decision["disposition"] == "CANONICAL"
    assert decision["paper_authority"] is True
    assert decision["exchange_authority"] is False
    assert decision["trade_permission"] is False
    assert decision["order_path"] == "NONE"
    assert [event["state"] for event in events] == ["CREATED", "AUTHORIZED"]
    assert all(event["exchange_authority"] is False for event in events)


def test_opposing_directions_are_preserved_as_blocked_decisions():
    decisions, events = build_initial_paper_lifecycle(
        _snapshot([_strategy("LONG", strategy_id="S1"), _strategy("SHORT", strategy_id="S2")])
    )

    assert len(decisions) == 2
    assert {decision["disposition"] for decision in decisions} == {"BLOCKED"}
    assert all(decision["paper_authority"] is False for decision in decisions)
    assert all("DIRECTION_CONFLICT" in decision["blockers"] for decision in decisions)
    assert [event["state"] for event in events] == [
        "CREATED",
        "BLOCKED",
        "CREATED",
        "BLOCKED",
    ]


def test_initial_lifecycle_is_deterministic_and_retry_safe():
    snapshot = _snapshot([_strategy()])
    first = build_initial_paper_lifecycle(snapshot)
    second = build_initial_paper_lifecycle(snapshot)

    assert first == second


def test_protective_outcomes_cannot_precede_entry_fill():
    assert not transition_allowed(PaperState.AUTHORIZED, PaperState.STOPPED)
    assert not transition_allowed(PaperState.SUBMITTED, PaperState.TARGETED)
    assert transition_allowed(PaperState.FILLED, PaperState.STOPPED)
    assert transition_allowed(PaperState.FILLED, PaperState.TARGETED)


def test_sql_ledger_is_append_only_private_and_has_no_live_path():
    sql = Path("ops/sql/paper_lifecycle_v01.sql").read_text(encoding="utf-8").lower()

    assert parse_sql(sql)
    assert "enable row level security" in sql
    assert "before update or delete" in sql
    assert "security_invoker=true" in sql
    assert "grant select,insert" in sql
    assert "exchange_authority=false" in sql
    assert "trade_permission=false" in sql
    assert "order_path='none'" in sql
    assert "blocked_direction_conflict" in sql
    assert "grant update" not in sql
    assert "grant delete" not in sql


def test_opposite_to_canonical_direction_cannot_create_a_paper_order():
    decisions, events = build_initial_paper_lifecycle(
        _snapshot([_strategy("SHORT", strategy_id="S6")])
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["disposition"] == "BLOCKED"
    assert decision["action_status"] == "BLOCKED_DIRECTION_CONFLICT"
    assert decision["paper_authority"] is False
    assert decision["blockers"] == ["CANONICAL_DIRECTION_CONFLICT"]
    assert decision["evidence"]["market_state"] == "DIRECTION_EMERGING_LONG"
    action = decision["evidence"]["action"]
    assert action["candidate_direction"] == "SHORT"
    assert action["canonical_direction"] == "LONG"
    assert [event["state"] for event in events] == ["CREATED", "BLOCKED"]

    orders, fills, execution_events = build_initial_paper_execution(decisions)
    assert orders == []
    assert fills == []
    assert execution_events == []
