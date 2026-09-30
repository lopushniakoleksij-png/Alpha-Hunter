from datetime import datetime, timedelta, timezone

from app import dashboard_payload


def _strategy(
    direction,
    entry,
    stop,
    target,
    *,
    strategy_id="S1",
    action="EXECUTE_NOW",
):
    risk = abs(entry - stop)
    reward = abs(target - entry)
    return {
        "strategy_id": strategy_id,
        "strategy_name": "Regression strategy",
        "status": "SHADOW_CANDIDATE",
        "action": action,
        "proposed_action": action,
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "rr": reward / risk,
        "distance_to_entry_pct": 0.0,
        "signal_score": 8.5,
        "shadow_only": True,
        "trade_permission": False,
    }


def _market(symbol, price, strategies, *, price_place=6, spread_pct=0.01):
    half_spread = price * spread_pct / 200.0
    return {
        "symbol": symbol,
        "last_price": price,
        "bid_price": price - half_spread,
        "ask_price": price + half_spread,
        "instrument_constraints": {
            "price_place": price_place,
            "price_end_step": "1",
            "public_maker_fee_bps": 2.0,
            "public_taker_fee_bps": 6.0,
            "fee_rate_source": "BITGET_V3_PUBLIC_INSTRUMENT_METADATA",
        },
        "state": "DIRECTION_EMERGING_LONG",
        "market_phase": "IGNITION",
        "opportunity_timing": "EARLY",
        "behaviour_score": 7.0,
        "discovery_permission": True,
        "rejection_reasons": [],
        "v7_trade_ready": False,
        "execution_setup": {"checks": {}},
        "intelligence": {"huge_rr_score": 7.0},
        "multi_strategy_engine": {"strategies": strategies},
    }


def _snapshot(rows, *, age=timedelta(seconds=30)):
    return {
        "collected_at_utc": (
            datetime.now(timezone.utc) - age
        ).isoformat(),
        "canonical_market_freshness": {
            "verified": True,
            "source": "BITGET_V2_USDT_FUTURES_TICKERS",
        },
        "symbols": rows,
        "universe": {"selected_count": len(rows)},
        "private_account": {},
    }


def _blockers(data, symbol):
    return [
        blocker
        for row in data["blocked_actions"]
        if row["symbol"] == symbol
        for blocker in row["_action"]["blockers"]
    ]


def test_brusdt_280r_is_quarantined_as_geometry_outlier():
    br = _market(
        "BRUSDT",
        0.74263,
        [_strategy("LONG", 0.74263, 0.74112, 1.16571)],
    )

    data = dashboard_payload(_snapshot([br]))

    assert data["actionable"] == []
    assert "EXECUTION_RR_OUTLIER" in _blockers(data, "BRUSDT")


def test_river_opposing_ready_sides_are_both_quarantined():
    river = _market(
        "RIVERUSDT",
        1.224,
        [
            _strategy("SHORT", 1.224, 1.2324689617702642, 1.1454, strategy_id="S2"),
            _strategy(
                "LONG",
                1.223,
                1.2052199983893457,
                1.336,
                strategy_id="S3",
                action="PLACE_LIMIT",
            ),
        ],
    )

    data = dashboard_payload(_snapshot([river]))

    assert data["actionable"] == []
    assert _blockers(data, "RIVERUSDT").count("DIRECTION_CONFLICT") == 2


def test_valid_single_side_is_paper_only_and_bitget_normalized():
    row = _market(
        "GOODUSDT",
        1.224,
        [_strategy("SHORT", 1.22404, 1.2324689617, 1.1818951915)],
        price_place=4,
    )

    data = dashboard_payload(_snapshot([row]))

    assert len(data["actionable"]) == 1
    action = data["actionable"][0]["_action"]
    assert action["status"] == "EXECUTE_NOW_PAPER"
    assert action["entry"] == 1.224
    assert action["stop"] == 1.2325
    assert action["target"] == 1.1819
    assert action["execution_authority"] is False


def test_stale_snapshot_cannot_produce_paper_action():
    row = _market(
        "STALEUSDT",
        10.0,
        [_strategy("LONG", 10.0, 9.5, 12.5)],
    )

    data = dashboard_payload(_snapshot([row], age=timedelta(hours=2)))

    assert data["actionable"] == []
    assert "SNAPSHOT_STALE_FOR_ACTION" in _blockers(data, "STALEUSDT")


def test_cost_floor_that_consumes_stop_blocks_action():
    row = _market(
        "COSTUSDT",
        1.0,
        [_strategy("LONG", 1.0, 0.999, 1.01)],
        spread_pct=0.05,
    )

    data = dashboard_payload(_snapshot([row]))

    assert data["actionable"] == []
    assert "EXECUTION_COST_FLOOR_CONSUMES_STOP" in _blockers(data, "COSTUSDT")


def test_same_side_duplicates_reduce_to_one_canonical_decision():
    row = _market(
        "ONEUSDT",
        10.0,
        [
            _strategy("LONG", 10.0, 9.5, 12.5, strategy_id="S1"),
            _strategy("LONG", 10.0, 9.5, 13.0, strategy_id="S2"),
        ],
    )

    data = dashboard_payload(_snapshot([row]))

    assert len(data["actionable"]) == 1
    assert data["actionable"][0]["symbol"] == "ONEUSDT"
    assert len(data["suppressed_actions"]) == 1
    assert data["suppressed_actions"][0]["_action"]["blockers"] == [
        "SUPERSEDED_BY_CANONICAL_SYMBOL_DECISION"
    ]
