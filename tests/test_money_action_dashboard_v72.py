from app import build_money_action, dashboard_payload, required_entry_for_rr


def base_row(direction="LONG", current=110.0, stop=100.0, target=130.0, rr=2.0):
    return {
        "symbol": "TESTUSDT",
        "last_price": current,
        "state": f"DIRECTION_EMERGING_{direction}",
        "market_phase": "IGNITION",
        "opportunity_timing": "EARLY",
        "behaviour_score": 7.0,
        "discovery_permission": True,
        "candidate_quality_status": "PASS",
        "rejection_reasons": [],
        "v7_trade_ready": False,
        "execution_setup": {
            "direction": direction,
            "entry": current,
            "stop": stop,
            "target": target,
            "rr": rr,
            "checks": {
                "direction_aligned": True,
                "structure_valid": True,
                "momentum_confirmed": True,
                "participation_confirmed": True,
                "funding_not_extreme": True,
                "data_integrity_min_88": True,
                "rr_minimum_met": False,
            },
        },
        "intelligence": {"huge_rr_score": 7.0, "confidence_estimate_pct": 65.0},
    }


def test_required_entry_math_for_five_r():
    entry = required_entry_for_rr(100.0, 130.0, 5.0)
    assert entry == 105.0
    assert (130.0 - entry) / (entry - 100.0) == 5.0


def test_late_long_becomes_retest_plan_not_ready_now():
    action = build_money_action(base_row())
    assert action["status"] == "RETEST_PLAN"
    assert action["entry"] == 105.0
    assert action["stop"] == 100.0
    assert action["target"] == 130.0
    assert action["rr"] == 5.0


def test_short_retest_math_is_symmetric():
    row = base_row(direction="SHORT", current=90.0, stop=100.0, target=70.0, rr=2.0)
    action = build_money_action(row)
    assert action["status"] == "RETEST_PLAN"
    assert action["entry"] == 95.0
    assert (action["entry"] - 70.0) / (100.0 - action["entry"]) == 5.0


def test_missing_momentum_stays_research_only():
    row = base_row()
    row["execution_setup"]["checks"]["momentum_confirmed"] = False
    action = build_money_action(row)
    assert action["status"] == "RESEARCH_ONLY"
    assert "momentum" in action["reason"]


def test_bad_phase_does_not_create_passive_falling_knife_plan():
    row = base_row()
    row["market_phase"] = "DISTRIBUTION_RISK"
    row["rejection_reasons"] = ["STOCH_RSI_OVEREXTENDED", "PHASE_DISTRIBUTION_RISK"]
    action = build_money_action(row)
    assert action["status"] == "RESEARCH_ONLY"


def test_existing_v7_ready_remains_ready_now():
    row = base_row(current=105.0, stop=100.0, target=130.0, rr=5.0)
    row["v7_trade_ready"] = True
    row["execution_setup"]["checks"]["rr_minimum_met"] = True
    action = build_money_action(row)
    assert action["status"] == "READY_NOW"
    assert action["entry"] == 105.0


def test_dashboard_does_not_promote_research_to_action_queue():
    good = base_row()
    bad = base_row()
    bad["symbol"] = "BADUSDT"
    bad["execution_setup"]["checks"]["participation_confirmed"] = False
    snapshot = {
        "symbols": [bad, good],
        "universe": {"selected_count": 2},
        "private_account": {},
    }
    data = dashboard_payload(snapshot)
    assert [row["symbol"] for row in data["actionable"]] == ["TESTUSDT"]
    assert data["best_action"]["symbol"] == "TESTUSDT"
    assert any(row["symbol"] == "BADUSDT" for row in data["research"])
