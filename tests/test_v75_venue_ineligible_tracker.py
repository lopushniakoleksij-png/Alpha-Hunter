from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from alpha_hunter.lifecycle import LifecycleEpisode
from alpha_hunter.storage import SupabaseConfig
from v75_episode_market_tracker import (
    finalize_venue_ineligible_episode,
    load_latest_universe_symbols,
)


def _episode():
    return LifecycleEpisode(
        episode_id="episode-1",
        symbol="4USDT",
        path="REVERSAL",
        first_detected_at_utc="2026-09-20T00:00:00+00:00",
        last_detected_at_utc="2026-09-20T00:00:00+00:00",
        first_detection_price=1.0,
        latest_price=1.0,
        lifecycle_state="EXPANSION",
        measurement_quality="FORWARD_COMPLETE",
        provisional_classification="GOOD_DETECTION",
    )


def _response(payload, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = ""
    return response


def test_latest_universe_is_loaded_from_fresh_canonical_hour():
    settings = SupabaseConfig(
        url="https://example.supabase.co",
        key="service-key",
        timeout_seconds=5,
    )
    now = datetime(2026, 9, 20, 1, 46, tzinfo=timezone.utc)

    responses = [
        _response([{"hour_bucket_utc": "2026-09-20T01:00:00+00:00"}]),
        _response([{"symbol": "BTCUSDT"}, {"symbol": "ethusdt"}]),
    ]

    with patch(
        "v75_episode_market_tracker.requests.get",
        side_effect=responses,
    ) as get:
        symbols, hour = load_latest_universe_symbols(
            settings,
            now,
        )

    assert symbols == {"BTCUSDT", "ETHUSDT"}
    assert hour == datetime(
        2026, 9, 20, 1, 0, tzinfo=timezone.utc
    )
    assert get.call_count == 2
    assert (
        get.call_args_list[1].kwargs["params"]["hour_bucket_utc"]
        == "eq.2026-09-20T01:00:00+00:00"
    )


def test_stale_universe_fails_closed_before_symbol_classification():
    settings = SupabaseConfig(
        url="https://example.supabase.co",
        key="service-key",
        timeout_seconds=5,
    )
    now = datetime(2026, 9, 20, 5, 1, tzinfo=timezone.utc)

    with patch(
        "v75_episode_market_tracker.requests.get",
        return_value=_response(
            [{"hour_bucket_utc": "2026-09-20T01:00:00+00:00"}]
        ),
    ):
        with pytest.raises(
            RuntimeError,
            match="canonical universe is stale",
        ):
            load_latest_universe_symbols(
                settings,
                now,
            )


def test_venue_ineligible_episode_is_censored_not_false_failed():
    episode = _episode()
    observed_at = datetime(
        2026, 9, 20, 1, 46, tzinfo=timezone.utc
    )

    finalize_venue_ineligible_episode(
        episode,
        observed_at,
    )

    assert episode.previous_state == "EXPANSION"
    assert episode.lifecycle_state == "FINALIZED"
    assert episode.measurement_quality == (
        "VENUE_INELIGIBLE_UNOBSERVABLE"
    )
    assert episode.final_classification == (
        "VENUE_INELIGIBLE_UNOBSERVABLE"
    )
    assert episode.provisional_classification == "GOOD_DETECTION"
    assert episode.is_finalized is True
    assert episode.finalized_at_utc == observed_at.isoformat()
    assert episode.trade_permission is False


def test_tracker_filters_current_universe_before_bitget_candle_call():
    source = Path(
        "v75_episode_market_tracker.py"
    ).read_text(encoding="utf-8")

    filter_pos = source.index(
        "if episode.symbol.upper() not in current_universe"
    )
    candle_pos = source.index(
        "candles = client.candles("
    )

    assert filter_pos < candle_pos
    assert "Venue ineligible finalized:" in source
    assert "VENUE_INELIGIBLE_UNOBSERVABLE" in source


def test_unexpected_bitget_errors_still_fail_the_job():
    source = Path(
        "v75_episode_market_tracker.py"
    ).read_text(encoding="utf-8")

    assert "except (" in source
    assert "BitgetAPIError" in source
    assert "failed += 1" in source
    assert "if failed:" in source
    assert "V7.5 MARKET TRACKER FAILED" in source
