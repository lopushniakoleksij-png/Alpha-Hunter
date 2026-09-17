from datetime import datetime, timezone

import pytest

from alpha_hunter.universe_ledger import build_rows_from_existing_scan


def test_live_universe_rows_preserve_cached_public_fee_evidence():
    observed = datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc)
    rows = build_rows_from_existing_scan(
        contracts=[{"symbol": "AAAUSDT", "symbolType": "crypto"}],
        instruments=[{
            "symbol": "AAAUSDT",
            "symbolType": "crypto",
            "makerFeeRate": "0.0002",
            "takerFeeRate": "0.0006",
        }],
        tickers=[{
            "symbol": "AAAUSDT",
            "lastPr": "1.25",
            "quoteVolume": "250000",
            "change24h": "0.03",
        }],
        selected_symbols={"AAAUSDT"},
        selection_snapshot_at_utc=observed.isoformat(),
        selection_run_id="live-fee-run-1",
        product_type="usdt-futures",
        config={"universe_scan": {"minimum_quote_volume": 100000, "maximum_24h_extension_pct": 25}},
        observed_at=observed,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["public_maker_fee_bps"] == pytest.approx(2.0)
    assert row["public_taker_fee_bps"] == pytest.approx(6.0)
    assert row["fee_rate_source"] == "BITGET_V3_INSTRUMENT_PUBLIC"
    assert row["trade_permission"] is False


def test_live_missing_fee_fields_remain_missing():
    observed = datetime(2026, 9, 17, 13, 0, tzinfo=timezone.utc)
    row = build_rows_from_existing_scan(
        contracts=[{"symbol": "AAAUSDT", "symbolType": "crypto"}],
        instruments=[{"symbol": "AAAUSDT", "symbolType": "crypto"}],
        tickers=[{"symbol": "AAAUSDT", "lastPr": "1", "quoteVolume": "250000", "change24h": "0.01"}],
        selected_symbols=set(),
        selection_snapshot_at_utc=observed.isoformat(),
        selection_run_id="live-fee-run-2",
        product_type="usdt-futures",
        config={"universe_scan": {"minimum_quote_volume": 100000, "maximum_24h_extension_pct": 25}},
        observed_at=observed,
    )[0]
    assert row["public_maker_fee_bps"] is None
    assert row["public_taker_fee_bps"] is None
    assert row["fee_rate_source"] is None
    assert row["trade_permission"] is False
