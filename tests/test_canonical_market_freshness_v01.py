from datetime import datetime, timedelta, timezone

import pytest

from alpha_hunter.bitget import BitgetAPIError
from alpha_hunter.collector import validate_canonical_market_freshness


def _ms(value: datetime) -> str:
    return str(int(value.timestamp() * 1000))


def test_canonical_market_freshness_accepts_recent_exchange_timestamp():
    now = datetime(2026, 9, 21, 21, 30, tzinfo=timezone.utc)
    result = validate_canonical_market_freshness(
        [{"symbol": "BTCUSDT", "ts": _ms(now - timedelta(seconds=5))}],
        observed_at=now,
        max_age_seconds=120,
    )
    assert result["verified"] is True
    assert result["source"] == "BITGET_V2_USDT_FUTURES_TICKERS"
    assert result["age_seconds"] == pytest.approx(5.0)


def test_canonical_market_freshness_blocks_stale_payload():
    now = datetime(2026, 9, 21, 21, 30, tzinfo=timezone.utc)
    with pytest.raises(BitgetAPIError, match="stale"):
        validate_canonical_market_freshness(
            [{"symbol": "BTCUSDT", "ts": _ms(now - timedelta(minutes=5))}],
            observed_at=now,
            max_age_seconds=120,
        )


def test_canonical_market_freshness_blocks_missing_exchange_timestamp():
    now = datetime(2026, 9, 21, 21, 30, tzinfo=timezone.utc)
    with pytest.raises(BitgetAPIError, match="freshness unverified"):
        validate_canonical_market_freshness(
            [{"symbol": "BTCUSDT", "lastPr": "86656.35"}],
            observed_at=now,
            max_age_seconds=120,
        )
