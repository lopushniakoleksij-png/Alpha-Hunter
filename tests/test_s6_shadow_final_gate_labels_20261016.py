"""Regression: an S6 shadow EXECUTE_NOW must not appear as a permitted action.

The sealed 30-day paper test, database and trading authority are untouched.
"""
from datetime import datetime, timezone

import app


def candidate(symbol, entry, stop, target):
    rr = (target - entry) / (entry - stop)
    strategy = {
        "strategy_id": "S6",
        "strategy_name": "Liquidity Sweep / Reclaim",
        "status": "SHADOW_CANDIDATE",
        "action": "EXECUTE_NOW",
        "proposed_action": "EXECUTE_NOW",
        "direction": "LONG",
        "signal_score": 10.0,
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": rr,
        "shadow_only": True,
        "trade_permission": False,
        "checks": {"signal_present": True, "geometry_valid": True},
        "reasons": [],
    }
    return {
        "symbol": symbol,
        "last_price": entry,
        "bid_price": entry - (entry * .0001),
        "ask_price": entry + (entry * .0001),
        "instrument_constraints": {
            "price_place": 5,
            "price_end_step": "1",
            "public_maker_fee_bps": 2.0,
            "public_taker_fee_bps": 6.0,
            "fee_rate_source": "BITGET_V3_PUBLIC_INSTRUMENT_METADATA",
        },
        "state": "DIRECTION_EMERGING_LONG",
        "market_phase": "IGNITION",
        "opportunity_timing": "EARLY",
        "behaviour_score": 8.0,
        "discovery_permission": True,
        "candidate_quality_status": "PASS",
        "rejection_reasons": [],
        "v7_trade_ready": False,
        "execution_setup": {
            "direction": "LONG", "entry": entry, "stop": stop,
            "target": target, "rr": rr,
            "checks": {
                "direction_aligned": True, "structure_valid": True,
                "momentum_confirmed": False, "participation_confirmed": False,
                "funding_not_extreme": True, "data_integrity_min_88": True,
                "rr_minimum_met": True,
            },
        },
        "intelligence": {"huge_rr_score": 10.0},
        "multi_strategy_engine": {
            "shadow_only": True,
            "trade_permission": False,
            "strategies": [strategy],
        },
    }


def build_snapshot(rows):
    return {
        "run_id": "isolated-s6-display-test",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_market_freshness": {"verified": True},
        "validation_identity": {"run_source": "RENDER_CRON"},
        "symbols": rows,
        "universe": {"selected_count": len(rows)},
        "private_account": {},
    }


def test_s6_extreme_reward_risk_is_finally_blocked_but_raw_intent_retained():
    rows = [
        candidate("REDUSDT", 0.1433, 0.1422, 0.1863),
        candidate("WCTUSDT", 0.03619, 0.03597, 0.0436),
    ]
    result = app.dashboard_payload(build_snapshot(rows))
    shadow = {s["symbol"]: s for s in result["strategy_shadow"]}
    assert set(shadow) == {"REDUSDT", "WCTUSDT"}
    for symbol in shadow:
        s = shadow[symbol]
        assert s["status"] == "SHADOW_CANDIDATE"  # original evidence not rewritten
        assert s["action"] == "EXECUTE_NOW"         # raw provenance retained
        assert s["_display_setup_intent"] == "SHADOW_EXECUTE_NOW"
        assert s["_display_gate_action"] == "BLOCKED"
        assert "EXECUTION_RR_OUTLIER" in s["_display_warning"]
        assert s["trade_permission"] is False
    assert result["trade_ready"] == []
    assert {r["symbol"] for r in result["blocked_actions"]} >= set(shadow)


def test_unapproved_watch_intent_stays_watch_only():
    row = candidate("TESTUSDT", 0.1433, 0.1422, 0.1863)
    strategy = row["multi_strategy_engine"]["strategies"][0]
    strategy["status"] = "WATCH"
    result = app.dashboard_payload(build_snapshot([row]))
    item = result["strategy_shadow"][0]
    assert item["_display_gate_action"] == "WAIT_FOR_TRIGGER"
    assert item["_display_setup_intent"] == "WATCH_ONLY"
    assert item["trade_permission"] is False
    assert result["trade_ready"] == []


def test_matrix_disclaims_uncalibrated_shadow_action_without_removing_safety():
    with app.app.test_request_context("/"):
        html = app.render_template_string(
            app.PAGE,
            data=app.dashboard_payload(build_snapshot([candidate("REDUSDT",0.1433,0.1422,0.1863)])),
        )
    assert "Raw shadow intent (not executable)" in html
    assert "SHADOW_EXECUTE_NOW" in html
    assert "EXECUTION_RR_OUTLIER" in html
    assert "Candidate status and 10/10 scores do not override blocks" in html
