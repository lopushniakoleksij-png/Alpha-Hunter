from __future__ import annotations

from v74_tracking_job import (
    active_contract_symbols,
    venue_ineligible_outcome,
)


def test_active_contract_symbols_normalizes_and_ignores_invalid_rows():
    assert active_contract_symbols([
        {"symbol": "btcusdt"},
        {"symbol": ""},
        {},
        "bad-row",
    ]) == {"BTCUSDT"}


def test_inactive_contract_is_terminal_and_excluded_from_performance():
    row = venue_ineligible_outcome(
        {
            "signal_id": "signal-4usdt",
            "symbol": "4USDT",
            "reference_price": "0.033785",
        },
        24,
        "2026-09-09T06:50:00+00:00",
    )

    assert row["outcome_class"] == "VENUE_INELIGIBLE_UNOBSERVABLE"
    assert row["evaluation_price"] == 0.033785
    assert row["return_pct"] is None
    assert row["direction_adjusted_return_pct"] is None
    assert row["target_hit"] is None
    assert row["stop_hit"] is None
    assert row["payload"]["venue_eligibility"] == "INACTIVE_OR_DELISTED"
    assert row["payload"]["excluded_from_performance"] is True
    assert row["payload"]["trade_permission"] is False
