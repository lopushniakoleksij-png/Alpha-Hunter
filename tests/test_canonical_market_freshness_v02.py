from datetime import datetime, timedelta, timezone

import pytest

from alpha_hunter.bitget import BitgetAPIError
from alpha_hunter.collector import validate_canonical_market_freshness


def _ms(value: datetime) -> str:
    return str(int(value.timestamp() * 1000))


def test_canonical_market_freshness_accepts_recent_exchange_timestamp():
    now = datetime(2026, 9, 26, 15, 20, tzinfo=timezone.utc)
    result = validate_canonical_market_freshness(
        [
            {"symbol": "BTCUSDT", "ts": _ms(now - timedelta(seconds=5))},
            {"symbol": "ETHUSDT", "ts": _ms(now - timedelta(seconds=8))},
        ],
        observed_at=now,
        max_age_seconds=120,
    )
    assert result["verified"] is True
    assert result["source"] == "BITGET_V2_USDT_FUTURES_TICKERS"
    assert result["age_seconds"] == pytest.approx(5.0)
    assert result["ticker_count"] == 2


def test_canonical_market_freshness_blocks_stale_payload():
    now = datetime(2026, 9, 26, 15, 20, tzinfo=timezone.utc)
    with pytest.raises(BitgetAPIError, match="stale"):
        validate_canonical_market_freshness(
            [{"symbol": "BTCUSDT", "ts": _ms(now - timedelta(minutes=5))}],
            observed_at=now,
            max_age_seconds=120,
        )


def test_canonical_market_freshness_blocks_missing_exchange_timestamp():
    now = datetime(2026, 9, 26, 15, 20, tzinfo=timezone.utc)
    with pytest.raises(BitgetAPIError, match="freshness unverified"):
        validate_canonical_market_freshness(
            [{"symbol": "BTCUSDT", "lastPr": "86656.35"}],
            observed_at=now,
            max_age_seconds=120,
        )


def test_canonical_market_freshness_blocks_empty_payload():
    now = datetime(2026, 9, 26, 15, 20, tzinfo=timezone.utc)
    with pytest.raises(BitgetAPIError, match="empty"):
        validate_canonical_market_freshness(
            [],
            observed_at=now,
            max_age_seconds=120,
        )


def test_canonical_market_freshness_blocks_material_future_timestamp():
    now = datetime(2026, 9, 26, 15, 20, tzinfo=timezone.utc)
    with pytest.raises(BitgetAPIError, match="future"):
        validate_canonical_market_freshness(
            [{"symbol": "BTCUSDT", "ts": _ms(now + timedelta(seconds=90))}],
            observed_at=now,
            max_age_seconds=120,
        )


def test_freshness_contract_is_persisted_in_snapshot_source():
    from pathlib import Path

    source = Path("alpha_hunter/collector.py").read_text(encoding="utf-8")
    assert '"canonical_market_freshness":' in source
    assert "CANONICAL MARKET DATA: BLOCKED" in source
    assert "return 2" in source
