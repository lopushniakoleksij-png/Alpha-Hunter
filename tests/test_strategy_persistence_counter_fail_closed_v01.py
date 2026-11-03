"""Isolated read-only shadow-strategy persistence provenance regressions."""
import pytest
from alpha_hunter.strategy_persistence import annotate_strategy_persistence


def _current():
    return {
        "symbol": "BTCUSDT",
        "collected_at_utc": "2026-11-03T14:00:00Z",
        "multi_strategy_engine": {
            "strategies": [{
                "strategy_id": "S1", "status": "WATCH",
                "direction": "LONG", "action": "WAIT_FOR_TRIGGER",
            }],
        },
    }


def _previous(counter):
    return {
        "multi_strategy_engine": {
            "strategies": [{
                "strategy_id": "S1", "status": "WATCH",
                "direction": "LONG", "action": "WAIT_FOR_TRIGGER",
                "persistence": {
                    "consecutive_scans": counter,
                    "first_seen_at_utc": "2026-11-03T13:00:00Z",
                },
            }],
        },
    }


@pytest.mark.parametrize("counter", [None, "", "bad", -1, -500, True, 1.5, float("nan"), float("inf"), {}, []])
def test_invalid_prior_counter_cannot_crash_or_inflate_shadow_continuity(counter):
    record = _current()
    summary = annotate_strategy_persistence(record, _previous(counter))
    row = record["multi_strategy_engine"]["strategies"][0]["persistence"]
    assert summary["continuing_count"] == 0
    assert row["consecutive_scans"] == 1
    assert row["state"] in ("NEW", "CHANGED")
    assert row["first_seen_at_utc"] == record["collected_at_utc"]


@pytest.mark.parametrize("counter,expected", [(1, 2), (4, 5)])
def test_valid_prior_counter_continues_without_reset(counter, expected):
    record = _current()
    summary = annotate_strategy_persistence(record, _previous(counter))
    row = record["multi_strategy_engine"]["strategies"][0]["persistence"]
    assert summary["continuing_count"] == 1
    assert row["state"] == "CONTINUING"
    assert row["consecutive_scans"] == expected
    assert row["first_seen_at_utc"] == "2026-11-03T13:00:00Z"
