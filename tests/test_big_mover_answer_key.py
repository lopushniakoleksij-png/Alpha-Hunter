from __future__ import annotations

from datetime import datetime, timezone

from alpha_hunter.big_mover_answer_key import build_answer_key_rows


CONFIG = {
    "universe_scan": {
        "minimum_quote_volume": 100000,
        "crypto_only": True,
        "reject_rwa": True,
        "reject_reality": True,
    }
}


def test_answer_key_records_both_sides_and_all_crossed_thresholds():
    metadata = [
        {"symbol": "UPUSDT", "symbolType": "normal"},
        {"symbol": "DOWNUSDT", "symbolType": "normal"},
    ]
    tickers = [
        {"symbol": "UPUSDT", "lastPr": "1.20", "change24h": "0.22", "quoteVolume": "500000"},
        {"symbol": "DOWNUSDT", "lastPr": "0.80", "change24h": "-0.12", "quoteVolume": "400000"},
    ]

    rows, summary = build_answer_key_rows(
        contracts=metadata,
        instruments=[],
        tickers=tickers,
        product_type="usdt-futures",
        config=CONFIG,
        observed_at=datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc),
    )

    up = [row for row in rows if row["symbol"] == "UPUSDT"]
    down = [row for row in rows if row["symbol"] == "DOWNUSDT"]
    assert {row["threshold_pct"] for row in up} == {5.0, 10.0, 20.0}
    assert {row["threshold_pct"] for row in down} == {5.0, 10.0}
    assert all(row["trade_permission"] is False for row in rows)
    assert all(row["shadow_only"] is True for row in rows)
    assert summary["threshold_symbol_counts"]["UP_20"] == 1
    assert summary["threshold_symbol_counts"]["DOWN_10"] == 1


def test_sub_five_percent_coin_is_not_answer_key_mover():
    metadata = [{"symbol": "QUIETUSDT", "symbolType": "normal"}]
    rows, _ = build_answer_key_rows(
        contracts=metadata,
        instruments=[],
        tickers=[{"symbol": "QUIETUSDT", "lastPr": "1", "change24h": "0.049", "quoteVolume": "500000"}],
        product_type="usdt-futures",
        config=CONFIG,
        observed_at=datetime(2026, 9, 13, 8, 0, tzinfo=timezone.utc),
    )
    assert rows == []
