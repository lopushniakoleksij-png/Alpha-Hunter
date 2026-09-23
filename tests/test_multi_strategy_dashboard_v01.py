from app import build_strategy_money_action, dashboard_payload


def legacy_blocked_row():
    return {
        "symbol": "TESTUSDT",
        "last_price": 105.0,
        "state": "DIRECTION_EMERGING_LONG",
        "market_phase": "IGNITION",
        "opportunity_timing": "EARLY",
        "behaviour_score": 7.0,
        "discovery_permission": True,
        "candidate_quality_status": "PASS",
        "rejection_reasons": [],
        "v7_trade_ready": False,
        "execution_setup": {
            "direction": "LONG",
            "entry": 105.0,
            "stop": 100.0,
            "target": 110.0,
            "rr": 1.0,
            "checks": {
                "direction_aligned": True,
                "structure_valid": True,
                "momentum_confirmed": False,
                "participation_confirmed": False,
                "funding_not_extreme": True,
                "data_integrity_min_88": True,
                "rr_minimum_met": False,
            },
        },
        "intelligence": {"huge_rr_score": 7.0, "confidence_estimate_pct": 60.0},
        "multi_strategy_engine": {
            "version": "0.1",
            "shadow_only": True,
            "trade_permission": False,
            "strategies": [
                {
                    "strategy_id": "S3",
                    "strategy_name": "Trend Pullback",
                    "status": "SHADOW_CANDIDATE",
                    "action": "PLACE_LIMIT",
                    "direction": "LONG",
                    "signal_score": 9.0,
                    "entry": 102.0,
                    "stop": 100.0,
                    "target": 130.0,
                    "rr": 14.0,
                    "reasons": [],
                    "shadow_only": True,
                    "trade_permission": False,
                }
            ],
        },
    }


def test_shadow_strategy_candidate_feeds_money_action_decision_support():
    snapshot = {
        "symbols": [legacy_blocked_row()],
        "universe": {"selected_count": 1},
        "private_account": {},
        "multi_strategy_summary": {
            "configured_strategy_count": 10,
            "covered_symbol_count": 1,
            "total_evaluations": 10,
            "shadow_candidate_count": 1,
            "evaluations_by_strategy": {f"S{i}": 1 for i in range(1, 11)},
            "candidates_by_strategy": {"S3": 1},
        },
    }

    data = dashboard_payload(snapshot)

    assert data["best_action"] is not None
    assert data["best_action"]["symbol"] == "TESTUSDT"
    action = data["best_action"]["_action"]
    assert action["status"] == "STRATEGY_LIMIT_READY"
    assert action["entry"] == 102.0
    assert action["stop"] == 100.0
    assert action["target"] == 130.0
    assert action["rr"] == 14.0
    assert action["execution_authority"] is False
    assert len(data["strategy_ready"]) == 1
    assert data["trade_ready"] == []
    assert data["strategy_shadow"][0]["strategy_id"] == "S3"
    assert data["strategy_shadow"][0]["status"] == "SHADOW_CANDIDATE"
    assert data["strategy_summary"]["configured_strategy_count"] == 10
    assert len(data["strategy_coverage"]) == 10


def test_watch_strategy_never_promotes_to_money_action():
    strategy = dict(legacy_blocked_row()["multi_strategy_engine"]["strategies"][0])
    strategy["status"] = "WATCH"
    strategy["action"] = "WAIT_FOR_TRIGGER"
    assert build_strategy_money_action(strategy) is None


def test_shadow_candidate_below_five_r_never_promotes():
    strategy = dict(legacy_blocked_row()["multi_strategy_engine"]["strategies"][0])
    strategy["rr"] = 4.99
    assert build_strategy_money_action(strategy) is None


def test_shadow_candidate_invalid_geometry_never_promotes():
    strategy = dict(legacy_blocked_row()["multi_strategy_engine"]["strategies"][0])
    strategy["stop"] = 103.0
    assert build_strategy_money_action(strategy) is None


def test_execute_now_shadow_candidate_becomes_ready_decision_support_only():
    strategy = dict(legacy_blocked_row()["multi_strategy_engine"]["strategies"][0])
    strategy["action"] = "EXECUTE_NOW"
    action = build_strategy_money_action(strategy)
    assert action is not None
    assert action["status"] == "STRATEGY_READY_NOW"
    assert action["execution_authority"] is False
