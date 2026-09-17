from datetime import datetime, timezone
from pathlib import Path

from alpha_hunter.universe_ledger import build_rows_from_existing_scan

SQL = Path('public_fee_evidence_v01.sql').read_text()


def test_universe_rows_capture_public_fee_rates_from_existing_instruments():
    observed = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
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
        selection_run_id="run-fee-1",
        product_type="usdt-futures",
        config={"universe_scan": {"minimum_quote_volume": 100000, "maximum_24h_extension_pct": 25}},
        observed_at=observed,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["public_maker_fee_bps"] == 2.0
    assert row["public_taker_fee_bps"] == 6.0
    assert row["fee_rate_source"] == "BITGET_V3_INSTRUMENT_PUBLIC"
    assert row["trade_permission"] is False


def test_missing_or_invalid_fee_rates_remain_missing_not_invented():
    observed = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    rows = build_rows_from_existing_scan(
        contracts=[{"symbol": "AAAUSDT", "symbolType": "crypto"}],
        instruments=[{"symbol": "AAAUSDT", "symbolType": "crypto", "makerFeeRate": None, "takerFeeRate": "bad"}],
        tickers=[{"symbol": "AAAUSDT", "lastPr": "1", "quoteVolume": "250000", "change24h": "0.01"}],
        selected_symbols=set(),
        selection_snapshot_at_utc=observed.isoformat(),
        selection_run_id="run-fee-2",
        product_type="usdt-futures",
        config={"universe_scan": {"minimum_quote_volume": 100000, "maximum_24h_extension_pct": 25}},
        observed_at=observed,
    )
    row = rows[0]
    assert row["public_maker_fee_bps"] is None
    assert row["public_taker_fee_bps"] is None
    assert row["fee_rate_source"] is None


def test_database_binding_is_forward_only_fee_evidence_not_cost_model():
    lower = SQL.lower()
    assert "before insert on public.alpha_hunter_execution_cost_evidence" in lower
    assert "u.selection_run_id=new.source_run_id" in lower
    assert "u.hour_bucket_utc=date_trunc('hour',new.captured_at_utc)" in lower
    assert "fee_evidence_is_not_cost_model" in SQL
    assert "fee_evidence_does_not_permit_realistic_net_r" in SQL
    assert "account_specific_fee_verified',false" in SQL
    assert "new.cost_model_id :=" not in lower
    assert "new.realistic_net_r :=" not in lower
    assert "trade_permission=true" not in lower
    assert "production_execution_enabled=true" not in lower


def test_no_exchange_or_cron_path_added_by_sql_migration():
    lower = SQL.lower()
    for forbidden in ["http_get(", "http_post(", "net.http", "cron.schedule", "place-order", "place_order"]:
        assert forbidden not in lower
