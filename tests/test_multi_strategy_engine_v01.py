from alpha_hunter.strategy_engine import (
    STRATEGY_CATALOG,
    apply_multi_strategy_engine,
    build_multi_strategy_summary,
)


def base_record():
    return {
        "symbol": "TESTUSDT",
        "last_price": 105.0,
        "support": 100.0,
        "resistance": 112.0,
        "breakout_trigger": 104.0,
        "data_integrity_score": 100,
        "funding_history": {"extreme": False},
        "btc_change_24h_pct": 2.0,
        "trade_permission": False,
        "v7_trade_ready": False,
        "market_phase": "IGNITION",
        "opportunity_timing": "EARLY",
        "behaviour": {
            "spread_pct": 0.05,
            "relative_strength_vs_btc_pct": 3.0,
            "relative_strength_acceleration": 1.0,
        },
        "timeframes": {
            "15m": {
                "trend": "BULLISH",
                "support": 101.0,
                "resistance": 110.0,
                "latest_candle": {
                    "open": 103.0,
                    "high": 106.0,
                    "low": 102.0,
                    "close": 105.0,
                },
                "indicators": {},
            },
            "1H": {
                "trend": "BULLISH",
                "support": 100.0,
                "resistance": 112.0,
                "latest_candle": {
                    "open": 103.0,
                    "high": 106.0,
                    "low": 102.0,
                    "close": 105.0,
                },
                "compression": {"state": "MODERATE", "score": 6.0},
                "indicators": {
                    "ema_21": 102.0,
                    "atr_14": 2.0,
                    "rsi_14": 58.0,
                    "stoch_rsi": 55.0,
                    "macd": {"histogram": 0.3},
                    "bollinger": {
                        "upper": 110.0,
                        "middle": 104.0,
                        "lower": 98.0,
                    },
                    "volume_anomaly": {
                        "state": "HIGH",
                        "ratio": 2.0,
                    },
                },
            },
            "4H": {
                "trend": "BULLISH",
                "support": 95.0,
                "resistance": 130.0,
                "latest_candle": {
                    "open": 100.0,
                    "high": 108.0,
                    "low": 98.0,
                    "close": 105.0,
                },
                "indicators": {},
            },
        },
    }


def config():
    return {
        "minimum_reward_risk": 5.0,
        "candidate_quality": {
            "minimum_execution_reward_risk": 5.0,
            "minimum_data_integrity": 88,
        },
        "multi_strategy_engine": {
            "enabled": True,
            "shadow_only": True,
            "minimum_shadow_reward_risk": 5.0,
            "minimum_signal_score": 6.5,
            "maximum_spread_pct": 0.15,
        },
    }


def by_id(payload, strategy_id):
    return next(row for row in payload["strategies"] if row["strategy_id"] == strategy_id)


def test_engine_emits_all_ten_strategies_and_never_grants_trade_permission():
    record = base_record()
    payload = apply_multi_strategy_engine(record, None, config())

    assert payload["strategy_count"] == 10
    assert [row["strategy_id"] for row in payload["strategies"]] == [
        strategy_id for strategy_id, _ in STRATEGY_CATALOG
    ]
    assert payload["shadow_only"] is True
    assert payload["trade_permission"] is False
    assert all(row["shadow_only"] is True for row in payload["strategies"])
    assert all(row["trade_permission"] is False for row in payload["strategies"])
    assert record["trade_permission"] is False
    assert record["v7_trade_ready"] is False


def test_engine_preserves_existing_v7_authority_without_expanding_it():
    record = base_record()
    record["trade_permission"] = True
    record["v7_trade_ready"] = True

    apply_multi_strategy_engine(record, None, config())

    assert record["trade_permission"] is True
    assert record["v7_trade_ready"] is True
    assert record["multi_strategy_engine"]["trade_permission"] is False


def test_s3_trend_pullback_builds_strategy_specific_shadow_limit_geometry():
    record = base_record()
    payload = apply_multi_strategy_engine(record, None, config())
    s3 = by_id(payload, "S3")

    assert s3["status"] == "SHADOW_CANDIDATE"
    assert s3["action"] == "PLACE_LIMIT"
    assert s3["direction"] == "LONG"
    assert s3["entry"] == 102.0
    assert s3["stop"] == 100.0
    assert s3["target"] == 130.0
    assert s3["rr"] == 14.0
    assert s3["production_permission"] is False


def test_s6_sweep_reclaim_uses_previous_canonical_levels():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["latest_candle"] = {
        "open": 101.0,
        "high": 103.0,
        "low": 99.0,
        "close": 101.0,
    }
    record["timeframes"]["1H"]["last_closed_candle"] = dict(
        record["timeframes"]["1H"]["latest_candle"]
    )
    previous = {"support": 100.0, "resistance": 112.0}

    payload = apply_multi_strategy_engine(record, previous, config())
    _stamp_valid_s6_clock(record)
    s6 = by_id(payload, "S6")

    assert s6["direction"] == "LONG"
    assert s6["evidence"]["swept_level"] == 100.0
    assert s6["status"] == "SHADOW_CANDIDATE"
    assert s6["trade_permission"] is False


def test_s7_fails_closed_without_true_absorption_evidence():
    record = base_record()
    previous = {"support": 100.0, "resistance": 104.0}
    payload = apply_multi_strategy_engine(record, previous, config())
    s7 = by_id(payload, "S7")

    assert s7["status"] == "DATA_INSUFFICIENT"
    assert s7["trade_permission"] is False
    assert "absorption" in " ".join(s7["reasons"]).lower()


def test_s9_fails_closed_without_validated_catalyst_source():
    payload = apply_multi_strategy_engine(base_record(), None, config())
    s9 = by_id(payload, "S9")

    assert s9["status"] == "DATA_INSUFFICIENT"
    assert s9["action"] == "NO_SAFE_TRADE"
    assert s9["trade_permission"] is False


def test_summary_proves_full_strategy_coverage():
    first = base_record()
    second = base_record()
    second["symbol"] = "SECONDUSDT"

    apply_multi_strategy_engine(first, None, config())
    apply_multi_strategy_engine(second, None, config())
    summary = build_multi_strategy_summary([first, second])

    assert summary["configured_strategy_count"] == 10
    assert summary["covered_symbol_count"] == 2
    assert summary["total_evaluations"] == 20
    assert all(count == 2 for count in summary["evaluations_by_strategy"].values())
    assert summary["trade_permission"] is False


def test_disabled_engine_still_cannot_grant_permission():
    record = base_record()
    settings = config()
    settings["multi_strategy_engine"]["enabled"] = False

    payload = apply_multi_strategy_engine(record, None, settings)

    assert payload["strategy_count"] == 10
    assert all(row["status"] == "DISABLED" for row in payload["strategies"])
    assert record["trade_permission"] is False
    assert payload["trade_permission"] is False


def _stamp_valid_s6_clock(record):
    """Bind the fixture to the actual canonical 15 Oct 12:23 UTC source clock."""
    record["collected_at_utc"] = "2026-10-15T12:20:24.956714+00:00"
    record["timeframes"]["1H"]["latest_candle"]["timestamp"] = 1792065600000
    closed = record["timeframes"]["1H"].get("last_closed_candle")
    if isinstance(closed, dict):
        closed["timestamp"] = 1792062000000


def test_s6_mmt_live_wick_does_not_confirm_closed_candle_reclaim():
    """15 Oct 2026 12:23 UTC: MMT was SHORT across 15m/1H/4H."""
    record = base_record()
    record.update(
        symbol="MMTUSDT",
        last_price=0.1412,
        support=0.1402,
        resistance=0.1758,
        market_phase="BREAKDOWN",
        opportunity_timing="LATE",
    )
    for timeframe in ("15m", "1H", "4H"):
        record["timeframes"][timeframe]["trend"] = "BEARISH"
    record["timeframes"]["1H"]["latest_candle"] = {
        "open": 0.1414, "high": 0.1416, "low": 0.1402, "close": 0.1412,
        "timestamp": 1792065600000,
    }
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 0.1431, "high": 0.1437, "low": 0.1406, "close": 0.1414,
        "timestamp": 1792062000000,
    }
    record["timeframes"]["1H"]["indicators"]["volume_anomaly"] = {
        "state": "HIGH", "ratio": 2.061, "source": "LAST_CLOSED",
    }

    _stamp_valid_s6_clock(record)
    s6 = by_id(
        apply_multi_strategy_engine(
            record, {"support": 0.1406, "resistance": 0.1758}, config()
        ), "S6"
    )
    assert s6["direction"] is None
    assert s6["status"] == "NO_SETUP"
    assert s6["action"] == "NO_SAFE_TRADE"
    assert s6["signal_score"] == 4.0
    assert s6["evidence"]["candle_basis"] == "LAST_FULLY_CLOSED_1H"
    assert s6["trade_permission"] is False


def test_s6_closed_countertrend_reclaim_is_watch_not_execute_now():
    record = base_record()
    record["last_price"] = 101.0
    record["market_phase"] = "BREAKDOWN"
    record["opportunity_timing"] = "LATE"
    for timeframe in ("15m", "1H", "4H"):
        record["timeframes"][timeframe]["trend"] = "BEARISH"
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 100.5, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    s6 = by_id(
        apply_multi_strategy_engine(
            record, {"support": 100.0, "resistance": 112.0}, config()
        ), "S6"
    )
    assert s6["direction"] == "LONG"
    assert s6["status"] == "WATCH"
    assert s6["action"] == "WAIT_FOR_TRIGGER"
    assert s6["signal_score"] == 6.0
    assert s6["checks"]["parent_direction_aligned"] is False
    assert s6["checks"]["timing_acceptable"] is False
    assert s6["trade_permission"] is False


def test_s6_valid_confirmed_closed_short_remains_discoverable():
    record = base_record()
    record["last_price"] = 99.0
    record["support"] = 85.0
    record["timeframes"]["1H"]["support"] = 85.0
    record["timeframes"]["4H"]["support"] = 85.0
    for timeframe in ("15m", "1H", "4H"):
        record["timeframes"][timeframe]["trend"] = "BEARISH"
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 99.5, "high": 100.5, "low": 97.0, "close": 99.0,
    }
    _stamp_valid_s6_clock(record)
    s6 = by_id(
        apply_multi_strategy_engine(
            record, {"support": 92.0, "resistance": 100.0}, config()
        ), "S6"
    )
    assert s6["direction"] == "SHORT"
    assert s6["status"] == "SHADOW_CANDIDATE"
    assert s6["action"] == "EXECUTE_NOW"
    assert s6["checks"]["parent_direction_aligned"] is True
    assert s6["signal_score"] == 10.0
    assert s6["trade_permission"] is False


def test_s6_outlier_geometry_stays_watch_before_paper_decision():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 101.0, "high": 103.0, "low": 100.0, "close": 101.0,
    }
    settings = config()
    settings["candidate_quality"]["maximum_action_reward_risk"] = 25.0
    _stamp_valid_s6_clock(record)
    s6 = by_id(
        apply_multi_strategy_engine(
            record, {"support": 100.5, "resistance": 112.0}, settings
        ), "S6"
    )
    assert s6["direction"] == "LONG"
    assert s6["rr"] == 29.0
    assert s6["status"] == "WATCH"
    assert s6["action"] == "WAIT_FOR_TRIGGER"
    assert s6["checks"]["rr_not_outlier"] is False
    assert s6["signal_score"] == 6.0


def test_s6_missing_closed_candle_fails_closed_even_with_live_sweep():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["latest_candle"] = {
        "open": 101.0, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    s6 = by_id(
        apply_multi_strategy_engine(
            record, {"support": 100.0, "resistance": 112.0}, config()
        ), "S6"
    )
    assert s6["status"] == "DATA_INSUFFICIENT"
    assert s6["action"] == "NO_SAFE_TRADE"
    assert s6["trade_permission"] is False


def test_s6_closed_reclaim_with_missing_parent_direction_stays_watch():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 101.0, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    for timeframe in ("15m", "1H", "4H"):
        record["timeframes"][timeframe]["trend"] = "DATA_UNAVAILABLE"
    _stamp_valid_s6_clock(record)
    s6 = by_id(
        apply_multi_strategy_engine(
            record, {"support": 100.0, "resistance": 112.0}, config()
        ), "S6"
    )
    assert s6["status"] == "WATCH"
    assert s6["action"] == "WAIT_FOR_TRIGGER"
    assert s6["checks"]["parent_direction_aligned"] is False
    assert s6["trade_permission"] is False


def test_s6_late_timing_blocks_immediate_even_when_direction_aligned():
    record = base_record()
    record["last_price"] = 101.0
    record["opportunity_timing"] = "LATE"
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 101.0, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    s6 = by_id(
        apply_multi_strategy_engine(
            record, {"support": 100.0, "resistance": 112.0}, config()
        ), "S6"
    )
    assert s6["direction"] == "LONG"
    assert s6["status"] == "WATCH"
    assert s6["action"] == "WAIT_FOR_TRIGGER"
    assert s6["checks"]["timing_acceptable"] is False


def test_s6_closed_candle_without_timestamp_never_executes():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 100.5, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    del record["timeframes"]["1H"]["last_closed_candle"]["timestamp"]
    s6 = by_id(apply_multi_strategy_engine(record, {"support": 100.0, "resistance": 112.0}, config()), "S6")
    assert s6["status"] == "DATA_INSUFFICIENT"
    assert s6["action"] == "NO_SAFE_TRADE"
    assert s6["trade_permission"] is False


def test_s6_stale_closed_candle_never_executes():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 100.5, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    record["timeframes"]["1H"]["last_closed_candle"]["timestamp"] -= 3600000
    s6 = by_id(apply_multi_strategy_engine(record, {"support": 100.0, "resistance": 112.0}, config()), "S6")
    assert s6["status"] == "DATA_INSUFFICIENT"
    assert s6["action"] == "NO_SAFE_TRADE"


def test_s6_future_closed_candle_never_executes():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 100.5, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    record["timeframes"]["1H"]["last_closed_candle"]["timestamp"] += 3600000
    s6 = by_id(apply_multi_strategy_engine(record, {"support": 100.0, "resistance": 112.0}, config()), "S6")
    assert s6["status"] == "DATA_INSUFFICIENT"
    assert s6["action"] == "NO_SAFE_TRADE"


def test_s6_source_snapshot_before_latest_candle_start_never_executes():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 100.5, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    record["collected_at_utc"] = "2026-10-15T11:20:24+00:00"
    s6 = by_id(apply_multi_strategy_engine(record, {"support": 100.0, "resistance": 112.0}, config()), "S6")
    assert s6["status"] == "DATA_INSUFFICIENT"
    assert s6["action"] == "NO_SAFE_TRADE"


def test_s6_missing_source_snapshot_clock_never_executes():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 100.5, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    del record["collected_at_utc"]
    s6 = by_id(apply_multi_strategy_engine(record, {"support": 100.0, "resistance": 112.0}, config()), "S6")
    assert s6["status"] == "DATA_INSUFFICIENT"
    assert s6["action"] == "NO_SAFE_TRADE"


def test_s6_missing_in_progress_candle_timestamp_never_executes():
    record = base_record()
    record["last_price"] = 101.0
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 100.5, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    del record["timeframes"]["1H"]["latest_candle"]["timestamp"]
    s6 = by_id(apply_multi_strategy_engine(record, {"support": 100.0, "resistance": 112.0}, config()), "S6")
    assert s6["status"] == "DATA_INSUFFICIENT"
    assert s6["action"] == "NO_SAFE_TRADE"


def test_s6_current_price_below_reclaimed_support_blocks_long():
    """A previously closed reclaim is invalid once the current price loses support."""
    record = base_record()
    record["last_price"] = 99.8
    record["timeframes"]["4H"]["resistance"] = 112.0
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 100.5, "high": 103.0, "low": 99.0, "close": 101.0,
    }
    _stamp_valid_s6_clock(record)
    s6 = by_id(apply_multi_strategy_engine(record, {"support": 100.0, "resistance": 112.0}, config()), "S6")
    assert s6["direction"] == "LONG"
    assert s6["rr"] is not None and 5.0 < s6["rr"] < 25.0
    assert s6["signal_score"] < 10
    assert s6["status"] == "WATCH"
    assert s6["action"] == "WAIT_FOR_TRIGGER"
    assert s6["checks"]["reclaim_accepted_now"] is False
    assert s6["trade_permission"] is False


def test_s6_current_price_above_rejected_resistance_blocks_short():
    """A formerly closed rejection is invalid once current price recovers resistance."""
    record = base_record()
    record["last_price"] = 100.2
    record["support"] = 85.0
    record["timeframes"]["1H"]["support"] = 85.0
    record["timeframes"]["4H"]["support"] = 85.0
    for timeframe in ("15m", "1H", "4H"):
        record["timeframes"][timeframe]["trend"] = "BEARISH"
    record["timeframes"]["1H"]["last_closed_candle"] = {
        "open": 99.5, "high": 101.0, "low": 97.0, "close": 99.0,
    }
    _stamp_valid_s6_clock(record)
    s6 = by_id(apply_multi_strategy_engine(record, {"support": 92.0, "resistance": 100.0}, config()), "S6")
    assert s6["direction"] == "SHORT"
    assert s6["rr"] is not None and 5.0 < s6["rr"] < 25.0
    assert s6["signal_score"] < 10
    assert s6["status"] == "WATCH"
    assert s6["action"] == "WAIT_FOR_TRIGGER"
    assert s6["checks"]["reclaim_accepted_now"] is False
    assert s6["trade_permission"] is False


def test_s6_current_price_equal_swept_level_fails_closed_both_sides():
    for direction in ("LONG", "SHORT"):
        record = base_record()
        record["last_price"] = 100.0
        if direction == "LONG":
            record["timeframes"]["1H"]["last_closed_candle"] = {
                "open": 100.5, "high": 103.0, "low": 99.0, "close": 101.0,
            }
        else:
            record["support"] = 85.0
            record["timeframes"]["1H"]["support"] = 85.0
            record["timeframes"]["4H"]["support"] = 85.0
            for timeframe in ("15m", "1H", "4H"):
                record["timeframes"][timeframe]["trend"] = "BEARISH"
            record["timeframes"]["1H"]["last_closed_candle"] = {
                "open": 99.5, "high": 101.0, "low": 97.0, "close": 99.0,
            }
        _stamp_valid_s6_clock(record)
        s6 = by_id(apply_multi_strategy_engine(record, {"support": 100.0 if direction == "LONG" else 92.0, "resistance": 100.0 if direction == "SHORT" else 112.0}, config()), "S6")
        assert s6["direction"] == direction
        assert s6["status"] == "WATCH"
        assert s6["action"] == "WAIT_FOR_TRIGGER"
        assert s6["checks"]["reclaim_accepted_now"] is False
