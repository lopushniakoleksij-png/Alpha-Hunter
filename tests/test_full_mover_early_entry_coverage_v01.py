from alpha_hunter.collector import select_market_universe


def _ticker(symbol: str, move_pct: float, volume: float = 1_000_000):
    return {
        "symbol": symbol,
        "lastPr": "1.0",
        "quoteVolume": str(volume),
        "change24h": str(move_pct / 100.0),
    }


def _meta(symbol: str):
    return {"symbol": symbol, "symbolType": "crypto"}


def test_mandatory_movers_are_selected_before_quiet_and_liquidity_buckets():
    symbols = [
        "MOVE1USDT",
        "MOVE2USDT",
        "MOVE3USDT",
        "EARLY1USDT",
        "EARLY2USDT",
        "QUIET1USDT",
        "LIQUID1USDT",
    ]
    contracts = [_meta(s) for s in symbols]
    instruments = [_meta(s) for s in symbols]
    tickers = [
        _ticker("MOVE1USDT", 14.0),
        _ticker("MOVE2USDT", -12.0),
        _ticker("MOVE3USDT", 9.0),
        _ticker("EARLY1USDT", 6.0),
        _ticker("EARLY2USDT", -4.0),
        _ticker("QUIET1USDT", 0.5),
        _ticker("LIQUID1USDT", 0.2, volume=50_000_000),
    ]
    config = {
        "universe_scan": {
            "deep_scan_limit": 5,
            "minimum_quote_volume": 100_000,
            "maximum_24h_extension_pct": 25,
            "mandatory_mover_abs_change_min_pct": 8,
            "mandatory_mover_limit": 3,
            "pre_move_bucket_size": 2,
            "pre_move_min_abs_change_pct": 1,
            "pre_move_max_abs_change_pct": 8,
            "quiet_bucket_size": 10,
            "movement_bucket_size": 10,
            "liquidity_bucket_size": 10,
            "preserve_previous_candidates": False,
        }
    }

    selected, summary = select_market_universe(
        contracts,
        instruments,
        tickers,
        None,
        config,
    )

    assert selected == [
        "MOVE1USDT",
        "MOVE2USDT",
        "MOVE3USDT",
        "EARLY1USDT",
        "EARLY2USDT",
    ]
    assert summary["mandatory_mover_selected_count"] == 3
    assert summary["pre_move_selected_count"] == 2


def test_overextended_coin_is_not_forced_into_deep_scan():
    symbols = ["CHASEUSDT", "VALIDUSDT"]
    contracts = [_meta(s) for s in symbols]
    instruments = [_meta(s) for s in symbols]
    tickers = [
        _ticker("CHASEUSDT", 35.0),
        _ticker("VALIDUSDT", 12.0),
    ]
    config = {
        "universe_scan": {
            "deep_scan_limit": 10,
            "minimum_quote_volume": 100_000,
            "maximum_24h_extension_pct": 25,
            "mandatory_mover_abs_change_min_pct": 8,
            "mandatory_mover_limit": 10,
            "pre_move_bucket_size": 0,
            "quiet_bucket_size": 0,
            "movement_bucket_size": 0,
            "liquidity_bucket_size": 0,
            "preserve_previous_candidates": False,
        }
    }

    selected, _ = select_market_universe(
        contracts,
        instruments,
        tickers,
        None,
        config,
    )

    assert "VALIDUSDT" in selected
    assert "CHASEUSDT" not in selected


def test_configured_deep_scan_limit_is_not_weakened_by_priority_buckets():
    symbols = [f"M{i}USDT" for i in range(20)]
    contracts = [_meta(s) for s in symbols]
    instruments = [_meta(s) for s in symbols]
    tickers = [_ticker(s, 8 + i * 0.1) for i, s in enumerate(symbols)]
    config = {
        "universe_scan": {
            "deep_scan_limit": 7,
            "minimum_quote_volume": 100_000,
            "maximum_24h_extension_pct": 25,
            "mandatory_mover_abs_change_min_pct": 8,
            "mandatory_mover_limit": 20,
            "pre_move_bucket_size": 20,
            "quiet_bucket_size": 20,
            "movement_bucket_size": 20,
            "liquidity_bucket_size": 20,
            "preserve_previous_candidates": False,
        }
    }

    selected, _ = select_market_universe(
        contracts,
        instruments,
        tickers,
        None,
        config,
    )

    assert len(selected) == 7
