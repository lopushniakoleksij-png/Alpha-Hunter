from __future__ import annotations

from datetime import datetime, timezone

from alpha_hunter.lifecycle import LifecycleEpisode
from v75_episode_market_tracker import (
    active_contract_symbols,
    finalize_venue_ineligible_episode,
)


def test_active_contract_symbols_normalizes_and_ignores_invalid_rows():
    assert active_contract_symbols([
        {"symbol": "ethusdt"},
        {"symbol": ""},
        {},
        "bad-row",
    ]) == {"ETHUSDT"}


def test_inactive_episode_is_finalized_without_trade_permission():
    episode = LifecycleEpisode(
        episode_id="episode-4usdt",
        symbol="4USDT",
        path="CONTINUATION",
        first_detected_at_utc="2026-09-01T00:00:00+00:00",
        last_detected_at_utc="2026-09-08T00:00:00+00:00",
        first_detection_price=0.02,
        latest_price=0.03,
        lifecycle_state="DIRECTION_EMERGING",
        trade_permission=False,
        v7_trade_ready=False,
    )
    observed_at = datetime(
        2026, 9, 9, 7, 0,
        tzinfo=timezone.utc,
    )

    finalize_venue_ineligible_episode(
        episode,
        observed_at,
    )

    assert episode.previous_state == "DIRECTION_EMERGING"
    assert episode.lifecycle_state == "VENUE_INELIGIBLE"
    assert episode.final_classification == "VENUE_INELIGIBLE_UNOBSERVABLE"
    assert episode.measurement_quality == "VENUE_INELIGIBLE_UNOBSERVABLE"
    assert episode.is_finalized is True
    assert episode.finalized_at_utc == observed_at.isoformat()
    assert episode.trade_permission is False
    assert episode.v7_trade_ready is False
