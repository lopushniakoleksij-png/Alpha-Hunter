"""Nonfinite prior strategy metrics must not contaminate evidence annotations.

All rows are synthetic; these tests do not access canonical storage or trade paths.
"""
import math
import pytest

from alpha_hunter.strategy_persistence import annotate_strategy_persistence


def _record(prior_rr, prior_score):
    previous = {
        "symbol": "BTCUSDT",
        "collected_at_utc": "2026-11-03T13:00:00Z",
        "multi_strategy_engine": {"strategies": [{
            "strategy_id": "S1", "status": "WATCH", "direction": "LONG",
            "rr": prior_rr, "signal_score": prior_score,
            "persistence": {"consecutive_scans": 2, "first_seen_at_utc": "2026-11-03T12:00:00Z"},
        }]},
    }
    current = {
        "symbol": "BTCUSDT",
        "collected_at_utc": "2026-11-03T14:00:00Z",
        "multi_strategy_engine": {"strategies": [{
            "strategy_id": "S1", "status": "WATCH", "direction": "LONG",
        }]},
    }
    annotate_strategy_persistence(current, previous)
    return current["multi_strategy_engine"]["strategies"][0]["persistence"]


@pytest.mark.parametrize("bad", [
    float("nan"), float("inf"), -float("inf"),
    "NaN", "Infinity", "-Infinity", "1e10000",
])
def test_nonfinite_prior_metrics_are_not_published_as_numeric_evidence(bad):
    result = _record(bad, bad)
    assert result["previous_signal_score"] is None
    assert result["previous_rr"] is None


@pytest.mark.parametrize("good,expected", [
    (0, 0.0), ("1.25", 1.25), (-2.5, -2.5),
])
def test_finite_prior_metrics_remain_available(good, expected):
    result = _record(good, good)
    assert result["previous_signal_score"] == expected
    assert result["previous_rr"] == expected
    assert math.isfinite(result["previous_rr"])


def test_unparseable_prior_metrics_remain_unknown():
    result = _record("not-a-number", None)
    assert result["previous_rr"] is None
    assert result["previous_signal_score"] is None
