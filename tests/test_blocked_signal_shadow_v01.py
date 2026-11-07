from datetime import datetime, timedelta, timezone

from alpha_hunter.blocked_signal_shadow_v01 import evaluate_blocked_shadow

T = datetime(2026, 11, 7, 10, 15, tzinfo=timezone.utc)
BASE = dict(final_gate_outcome="BLOCKED", block_reasons=["EXECUTION_RR_OUTLIER"],
            direction="LONG", decision_at=T, entry="100", stop="95",
            target="110", tick_size="0.5")


def candles(*pairs):
    start = T.replace(minute=0) + timedelta(hours=1)
    return [dict(open_at=start + timedelta(hours=i),
                 closed_at=start + timedelta(hours=i + 1),
                 known_at=start + timedelta(hours=i + 1),
                 verified=True, fully_closed=True, low=lo, high=hi)
            for i, (lo, hi) in enumerate(pairs)]


def classify(rows, signal=None):
    return evaluate_blocked_shadow(signal or BASE, rows, horizon_hours=len(rows))["classification"]


def test_long_target_first_only_after_entry_candle():
    assert classify(candles((99, 101), (101, 111))) == "TARGET_FIRST"


def test_long_stop_first():
    assert classify(candles((99, 101), (94, 101))) == "STOP_FIRST"


def test_entry_candle_barrier_is_ambiguous():
    assert classify(candles((99, 111))) == "BOTH_SAME_CANDLE_AMBIGUOUS"


def test_both_barriers_after_fill_ambiguous():
    assert classify(candles((99, 101), (94, 111))) == "BOTH_SAME_CANDLE_AMBIGUOUS"


def test_no_fill_and_expiry():
    assert classify(candles((101, 109))) == "NO_FILL"
    assert classify(candles((99, 101))) == "EXPIRED"


def test_short_direction():
    short = {**BASE, "direction": "SHORT", "stop": "105", "target": "90"}
    assert classify(candles((99, 101), (89, 101)), short) == "TARGET_FIRST"
    assert classify(candles((99, 101), (99, 106)), short) == "STOP_FIRST"


def test_gaps_and_unverified_candles_fail_closed():
    rows = candles((99, 101), (101, 111))
    rows[1]["open_at"] += timedelta(hours=1)
    assert classify(rows) == "INSUFFICIENT_DATA"
    rows = candles((99, 101))
    rows[0]["verified"] = False
    assert classify(rows) == "INSUFFICIENT_DATA"


def test_invalid_geometry_tick_and_gate_fail_closed():
    for signal in ({**BASE, "entry": "100.1"},
                   {**BASE, "stop": "105"},
                   {**BASE, "final_gate_outcome": "ELIGIBLE"},
                   {**BASE, "block_reasons": []}):
        assert classify(candles((99, 101)), signal) == "INSUFFICIENT_DATA"


def test_no_net_profit_or_verified_fill_claim():
    result = evaluate_blocked_shadow(BASE, candles((99, 101), (101, 111)),
                                     horizon_hours=2)
    assert result["gross_only"] is True
    assert result["net_return"] is None
    assert result["fill_verified"] is False


def test_later_missing_candle_cannot_be_hidden_by_early_target():
    rows = candles((99, 101), (101, 111), (100, 102))
    rows[2]["verified"] = False
    assert classify(rows) == "INSUFFICIENT_DATA"


def test_later_chronology_conflict_cannot_be_hidden_by_early_stop():
    rows = candles((99, 101), (94, 101), (100, 102))
    rows[2]["known_at"] = rows[2]["closed_at"] - timedelta(minutes=1)
    assert classify(rows) == "INSUFFICIENT_DATA"


def test_complete_window_still_classifies_early_target():
    assert classify(candles((99, 101), (101, 111), (100, 102))) == "TARGET_FIRST"
