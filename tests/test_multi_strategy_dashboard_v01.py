from app import dashboard_payload


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


def test_shadow_strategy_candidate_never_leaks_into_money_action():
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

    assert data["best_action"] is None
    assert data["actionable"] == []
    assert data["strategy_shadow"][0]["strategy_id"] == "S3"
    assert data["strategy_shadow"][0]["status"] == "SHADOW_CANDIDATE"
    assert data["strategy_summary"]["configured_strategy_count"] == 10
    assert len(data["strategy_coverage"]) == 10
