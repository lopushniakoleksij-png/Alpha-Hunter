from datetime import datetime, timezone

from alpha_hunter.universe_ledger import build_rows_from_existing_scan


def test_build_rows_uses_existing_payload_and_preserves_safety():
    config = {
        "universe_scan": {
            "minimum_quote_volume": 100000,
            "maximum_24h_extension_pct": 25,
            "crypto_only": True,
            "reject_rwa": True,
            "reject_reality": True,
        }
    }
    contracts = [{"symbol": "AAAUSDT", "symbolType": "crypto"}]
    instruments = [{"symbol": "AAAUSDT", "symbolType": "crypto"}]
    tickers = [{
        "symbol": "AAAUSDT",
        "lastPr": "1.25",
        "quoteVolume": "250000",
        "change24h": "0.03",
    }]
    observed = datetime(2026, 9, 16, 16, 0, tzinfo=timezone.utc)

    rows = build_rows_from_existing_scan(
        contracts=contracts,
        instruments=instruments,
        tickers=tickers,
        selected_symbols={"AAAUSDT"},
        selection_snapshot_at_utc=observed.isoformat(),
        selection_run_id="run-1",
        product_type="usdt-futures",
        config=config,
        observed_at=observed,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "AAAUSDT"
    assert row["liquidity_pass"] is True
    assert row["extension_pass"] is True
    assert row["prefilter_eligible"] is True
    assert row["deep_scan_selected"] is True
    assert row["selection_run_id"] == "run-1"
    assert row["trade_permission"] is False
    assert row["source"] == "PRIMARY_SCANNER_CACHED_TICKERS"


def test_observation_identity_is_hour_stable_to_prevent_duplicate_hourly_rows():
    base = datetime(2026, 9, 16, 16, 7, tzinfo=timezone.utc)
    later = datetime(2026, 9, 16, 16, 47, tzinfo=timezone.utc)
    kwargs = dict(
        contracts=[{"symbol": "AAAUSDT", "symbolType": "crypto"}],
        instruments=[{"symbol": "AAAUSDT", "symbolType": "crypto"}],
        tickers=[{"symbol": "AAAUSDT", "lastPr": "1", "quoteVolume": "250000", "change24h": "0.01"}],
        selected_symbols=set(),
        selection_snapshot_at_utc="2026-09-16T16:00:00+00:00",
        selection_run_id="run-1",
        product_type="usdt-futures",
        config={"universe_scan": {"minimum_quote_volume": 100000, "maximum_24h_extension_pct": 25}},
    )
    first = build_rows_from_existing_scan(observed_at=base, **kwargs)[0]
    second = build_rows_from_existing_scan(observed_at=later, **kwargs)[0]
    assert first["observation_id"] == second["observation_id"]
    assert first["hour_bucket_utc"] == second["hour_bucket_utc"]
