from app import dashboard_payload, position_protection_view


def test_blank_fields_are_unknown_when_protection_observer_failed():
    view = position_protection_view(
        {
            "symbol": "QNTUSDT",
            "take_profit": None,
            "stop_loss": None,
            "protection_observation_status": "FAILED",
            "protection_orders": [],
        },
        "2026-10-02T17:30:00+00:00",
    )

    assert view["_protection_state"] == "UNKNOWN"
    assert view["_take_profit_display"] == "Unknown"
    assert view["_stop_loss_display"] == "Unknown"
    assert "do not infer no SL/TP" in view["_protection_warning"]


def test_none_observed_requires_completed_protection_observer():
    view = position_protection_view(
        {
            "symbol": "QNTUSDT",
            "take_profit": None,
            "stop_loss": None,
            "protection_observation_status": "CONNECTED",
            "protection_orders": [],
        }
    )

    assert view["_protection_state"] == "NONE_OBSERVED"
    assert view["_take_profit_display"] == "None observed"
    assert view["_stop_loss_display"] == "None observed"


def test_pending_tpsl_levels_render_as_observed_protection():
    view = position_protection_view(
        {
            "symbol": "QNTUSDT",
            "take_profit": "270",
            "stop_loss": "234.29",
            "protection_observation_status": "CONNECTED",
            "protection_orders": [
                {
                    "plan_type": "pos_profit",
                    "trigger_price": "270",
                },
                {
                    "plan_type": "pos_loss",
                    "trigger_price": "234.29",
                },
            ],
        }
    )

    assert view["_protection_state"] == "OBSERVED"
    assert view["_take_profit_levels"] == ["270"]
    assert view["_stop_loss_levels"] == ["234.29"]
    assert view["_take_profit_display"] == "270"
    assert view["_stop_loss_display"] == "234.29"
    assert view["_protection_warning"] is None


def test_multiple_take_profit_levels_are_shown_not_collapsed():
    view = position_protection_view(
        {
            "symbol": "QNTUSDT",
            "take_profit": None,
            "stop_loss": "234.29",
            "protection_observation_status": "CONNECTED",
            "protection_orders": [
                {
                    "plan_type": "profit_plan",
                    "trigger_price": "257.40",
                },
                {
                    "plan_type": "pos_profit",
                    "trigger_price": "270",
                },
                {
                    "plan_type": "pos_loss",
                    "trigger_price": "234.29",
                },
            ],
        }
    )

    assert view["_protection_state"] == "OBSERVED"
    assert view["_take_profit_display"] == "257.40, 270"
    assert view["_stop_loss_display"] == "234.29"


def test_dashboard_projection_preserves_protection_observation_time():
    snapshot = {
        "collected_at_utc": "2026-10-02T17:45:00+00:00",
        "symbols": [],
        "universe": {},
        "private_account": {
            "status": "CONNECTED",
            "open_positions": [
                {
                    "symbol": "QNTUSDT",
                    "hold_side": "long",
                    "total": "0.06",
                    "take_profit": "270",
                    "stop_loss": "234.29",
                    "protection_observation_status": "CONNECTED",
                    "protection_orders": [],
                }
            ],
        },
    }

    data = dashboard_payload(snapshot)
    position = data["positions"][0]

    assert data["account_status"] == "CONNECTED"
    assert position["_protection_state"] == "OBSERVED"
    assert position["_protection_observed_at_utc"] == snapshot["collected_at_utc"]
