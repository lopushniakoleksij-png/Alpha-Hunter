from alpha_hunter.catalyst import (
    bind_official_catalyst,
    build_catalyst_summary,
)
from alpha_hunter.strategy_engine import apply_multi_strategy_engine


def config():
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
        },
    }


def record():
    return {
        "symbol": "HYPEUSDT",
        "collected_at_utc": "2026-09-22T18:00:00+00:00",
        "exchange_timestamp_ms": 1_800_000_000_000,
        "last_price": 105.0,
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
                "latest_candle": {"open": 103.0, "high": 106.0, "low": 102.0, "close": 105.0},
                "indicators": {},
            },
            "1H": {
                "trend": "BULLISH",
                "support": 100.0,
                "resistance": 130.0,
                "latest_candle": {"open": 103.0, "high": 106.0, "low": 102.0, "close": 105.0},
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
                "latest_candle": {"open": 100.0, "high": 108.0, "low": 98.0, "close": 105.0},
                "indicators": {},
            },
        },
    }


def notice(title="Bitget Will List HYPE/USDT Perpetual Futures", published_ms=1_799_999_000_000):
    return {
        "annId": "123",
        "annTitle": title,
        "annUrl": "https://www.bitget.com/support/articles/123",
        "annType": "coin_listings",
        "annSubType": "futures",
        "language": "en_US",
        "cTime": str(published_ms),
    }


def test_official_notice_binds_exact_symbol_and_is_fresh():
    catalyst = bind_official_catalyst(
        symbol="HYPEUSDT",
        base_coin="HYPE",
        notices=[notice()],
        exchange_timestamp_ms=1_800_000_000_000,
        freshness_hours=48,
    )

    assert catalyst is not None
    assert catalyst["validated"] is True
    assert catalyst["source"] == "BITGET_OFFICIAL_ANNOUNCEMENT_API"
    assert catalyst["fresh"] is True
    assert catalyst["matched_on"] == "HYPE/USDT"
    assert catalyst["direction"] == "MARKET_CONFIRMED"
    assert catalyst["trade_permission"] is False


def test_short_base_coin_does_not_match_common_word():
    catalyst = bind_official_catalyst(
        symbol="INUSDT",
        base_coin="IN",
        notices=[notice(title="Bitget introduces improvements in futures trading")],
        exchange_timestamp_ms=1_800_000_000_000,
        freshness_hours=48,
    )

    assert catalyst is None


def test_s9_uses_market_confirmation_instead_of_inventing_announcement_direction():
    row = record()
    row["catalyst"] = bind_official_catalyst(
        symbol="HYPEUSDT",
        base_coin="HYPE",
        notices=[notice()],
        exchange_timestamp_ms=row["exchange_timestamp_ms"],
        freshness_hours=48,
    )

    payload = apply_multi_strategy_engine(row, None, config())
    s9 = next(item for item in payload["strategies"] if item["strategy_id"] == "S9")

    assert s9["direction"] == "LONG"
    assert s9["evidence"]["direction_source"] == "MARKET_CONFIRMED_TRENDS"
    assert s9["evidence"]["title"].startswith("Bitget Will List HYPE")
    assert s9["status"] == "SHADOW_CANDIDATE"
    assert s9["trade_permission"] is False
    assert row["trade_permission"] is False


def test_s9_stale_official_notice_does_not_become_shadow_candidate():
    row = record()
    old = notice(published_ms=row["exchange_timestamp_ms"] - 72 * 3600 * 1000)
    row["catalyst"] = bind_official_catalyst(
        symbol="HYPEUSDT",
        base_coin="HYPE",
        notices=[old],
        exchange_timestamp_ms=row["exchange_timestamp_ms"],
        freshness_hours=48,
    )

    payload = apply_multi_strategy_engine(row, None, config())
    s9 = next(item for item in payload["strategies"] if item["strategy_id"] == "S9")

    assert s9["status"] != "SHADOW_CANDIDATE"
    assert s9["checks"]["catalyst_fresh"] is False
    assert s9["trade_permission"] is False


def test_catalyst_summary_counts_bound_and_fresh_symbols():
    fresh = record()
    fresh["catalyst"] = bind_official_catalyst(
        symbol="HYPEUSDT",
        base_coin="HYPE",
        notices=[notice()],
        exchange_timestamp_ms=fresh["exchange_timestamp_ms"],
        freshness_hours=48,
    )
    no_match = {"symbol": "BTCUSDT"}

    summary = build_catalyst_summary(
        [fresh, no_match],
        fetched_notice_count=5,
        categories=["coin_listings"],
    )

    assert summary["fetched_notice_count"] == 5
    assert summary["eligible_symbol_count"] == 2
    assert summary["bound_symbol_count"] == 1
    assert summary["fresh_bound_symbol_count"] == 1
    assert summary["trade_permission"] is False
