from alpha_hunter.microstructure import (
    build_microstructure_coverage,
    build_microstructure_snapshot,
    summarize_order_book,
    summarize_recent_trades,
)
from alpha_hunter.strategy_engine import apply_multi_strategy_engine
from alpha_hunter.strategy_persistence import annotate_strategy_persistence


def base_config():
    return {
        "minimum_reward_risk": 5.0,
        "candidate_quality": {
            "minimum_execution_reward_risk": 5.0,
            "minimum_data_integrity": 88,
        },
        "multi_strategy_engine": {
            "enabled": True,
            "minimum_shadow_reward_risk": 5.0,
            "minimum_signal_score": 6.5,
            "maximum_spread_pct": 0.15,
            "s7_acceptance": {
                "minimum_recent_trade_count": 20,
                "minimum_trade_imbalance_abs": 0.15,
                "minimum_depth_imbalance_abs": 0.05,
                "maximum_distance_from_level_pct": 3.0,
                "maximum_source_skew_ms": 60000,
            },
        },
    }


def base_record():
    return {
        "symbol": "TESTUSDT",
        "collected_at_utc": "2026-09-22T18:00:00+00:00",
        "last_price": 106.0,
        "support": 100.0,
        "resistance": 130.0,
        "breakout_trigger": 104.0,
        "data_integrity_score": 100,
        "funding_history": {"extreme": False},
        "btc_change_24h_pct": 1.5,
        "trade_permission": False,
        "v7_trade_ready": False,
        "market_phase": "IGNITION",
        "opportunity_timing": "EARLY",
        "behaviour": {
            "spread_pct": 0.03,
            "relative_strength_vs_btc_pct": 2.0,
            "relative_strength_acceleration": 0.5,
        },
        "timeframes": {
            "15m": {
                "trend": "BULLISH",
                "latest_candle": {"open": 105.0, "high": 107.0, "low": 104.0, "close": 106.0},
                "indicators": {},
            },
            "1H": {
                "trend": "BULLISH",
                "support": 100.0,
                "resistance": 130.0,
                "latest_candle": {"open": 104.0, "high": 107.0, "low": 103.0, "close": 106.0},
                "compression": {"state": "MODERATE", "score": 6.0},
                "indicators": {
                    "ema_21": 103.0,
                    "atr_14": 1.0,
                    "rsi_14": 58.0,
                    "stoch_rsi": 55.0,
                    "macd": {"histogram": 0.3},
                    "bollinger": {"upper": 112.0, "middle": 105.0, "lower": 98.0},
                    "volume_anomaly": {"state": "HIGH", "ratio": 2.0},
                },
            },
            "4H": {
                "trend": "BULLISH",
                "support": 95.0,
                "resistance": 140.0,
                "latest_candle": {"open": 100.0, "high": 108.0, "low": 98.0, "close": 106.0},
                "indicators": {},
            },
        },
    }


def test_order_book_summary_computes_depth_imbalance():
    result = summarize_order_book({
        "bids": [["105", "4"], ["104.5", "4"]],
        "asks": [["105.5", "1"], ["106", "1"]],
        "ts": "1000",
        "precision": "scale0",
        "scale": "0.1",
    })

    assert result["status"] == "COMPLETE"
    assert result["best_bid"] == 105.0
    assert result["best_ask"] == 105.5
    assert result["depth_imbalance"] > 0


def test_recent_trade_summary_computes_signed_notional_flow():
    rows = [
        {"tradeId": str(i), "price": "106", "size": "1", "side": "buy", "ts": str(1000 + i)}
        for i in range(30)
    ] + [
        {"tradeId": f"s{i}", "price": "106", "size": "0.2", "side": "sell", "ts": str(1100 + i)}
        for i in range(10)
    ]
    result = summarize_recent_trades(rows)

    assert result["status"] == "COMPLETE"
    assert result["trade_count"] == 40
    assert result["trade_imbalance"] > 0.5


def test_microstructure_snapshot_is_read_only_and_complete():
    depth = {
        "bids": [["105", "4"]],
        "asks": [["105.5", "1"]],
        "ts": "1000",
    }
    trades = [
        {"tradeId": "1", "price": "105.2", "size": "1", "side": "buy", "ts": "1010"}
    ]
    result = build_microstructure_snapshot(depth, trades, ticker_timestamp_ms=1020)

    assert result["status"] == "COMPLETE"
    assert result["read_only"] is True
    assert result["source_skew_ms"] == 10


def test_s7_can_form_acceptance_shadow_candidate_from_canonical_microstructure():
    record = base_record()
    record["microstructure"] = {
        "status": "COMPLETE",
        "source_skew_ms": 1000,
        "order_book": {
            "midpoint": 106.0,
            "depth_imbalance": 0.4,
        },
        "recent_trades": {
            "trade_count": 80,
            "trade_imbalance": 0.5,
        },
    }
    previous = {
        "support": 99.0,
        "resistance": 105.0,
    }

    payload = apply_multi_strategy_engine(record, previous, base_config())
    s7 = next(row for row in payload["strategies"] if row["strategy_id"] == "S7")

    assert s7["direction"] == "LONG"
    assert s7["action"] == "PLACE_LIMIT"
    assert s7["entry"] == 105.0
    assert s7["status"] == "SHADOW_CANDIDATE"
    assert s7["evidence"]["absorption_confirmed"] is False
    assert s7["trade_permission"] is False


def test_s7_fails_closed_when_microstructure_is_missing():
    payload = apply_multi_strategy_engine(base_record(), {"support": 99.0, "resistance": 105.0}, base_config())
    s7 = next(row for row in payload["strategies"] if row["strategy_id"] == "S7")

    assert s7["status"] == "DATA_INSUFFICIENT"
    assert s7["trade_permission"] is False


def test_strategy_persistence_tracks_continuing_candidate_without_granting_permission():
    first = base_record()
    first["microstructure"] = {
        "status": "COMPLETE",
        "source_skew_ms": 1000,
        "order_book": {"midpoint": 106.0, "depth_imbalance": 0.4},
        "recent_trades": {"trade_count": 80, "trade_imbalance": 0.5},
    }
    apply_multi_strategy_engine(first, {"support": 99.0, "resistance": 105.0}, base_config())
    annotate_strategy_persistence(first, None)

    second = base_record()
    second["collected_at_utc"] = "2026-09-22T19:00:00+00:00"
    second["microstructure"] = first["microstructure"]
    apply_multi_strategy_engine(second, {"support": 99.0, "resistance": 105.0}, base_config())
    summary = annotate_strategy_persistence(second, first)

    s7 = next(row for row in second["multi_strategy_engine"]["strategies"] if row["strategy_id"] == "S7")
    assert s7["persistence"]["state"] == "CONTINUING"
    assert s7["persistence"]["consecutive_scans"] == 2
    assert s7["trade_permission"] is False
    assert summary["continuing_count"] >= 1


def test_microstructure_coverage_reports_complete_and_insufficient_symbols():
    complete_record = {
        "symbol": "AUSDT",
        "microstructure": {"status": "COMPLETE"},
    }
    missing_record = {
        "symbol": "BUSDT",
        "microstructure": {"status": "DATA_INSUFFICIENT"},
    }
    summary = build_microstructure_coverage([complete_record, missing_record, {"symbol": "ERR", "error": "x"}])

    assert summary["eligible_symbol_count"] == 2
    assert summary["complete_count"] == 1
    assert summary["data_insufficient_count"] == 1
    assert summary["coverage_pct"] == 50.0
    assert summary["trade_permission"] is False
