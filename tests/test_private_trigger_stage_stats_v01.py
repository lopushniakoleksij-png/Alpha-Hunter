"""Unit checks for private-only trigger-statistics delta parser; no database access."""
import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "ops/local/qa_private_trigger_stage_stats_v01.py"
spec = importlib.util.spec_from_file_location("qa_private_trigger_stats", MODULE_PATH)
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def test_parse_stats_empty_baseline():
    assert qa.parse_stats("[]") == {}


def test_delta_accepts_newly_visible_functions():
    after = {name: (3, 24.0, 12.0) for name in qa.STAGES}
    result = qa.delta({}, after)
    assert len(result) == len(qa.STAGES)
    assert all(row["calls"] == 3 and row["mean_self_ms_per_call"] == 4.0 for row in result)


@pytest.mark.parametrize("bad", [
    '[{"function":"alpha_hunter_capture_strategy_observations_v01","calls":true,"total_ms":1,"self_ms":1}]',
    '[{"function":"alpha_hunter_capture_strategy_observations_v01","calls":1,"total_ms":1,"self_ms":2}]',
    '[{"function":"unknown","calls":1,"total_ms":1,"self_ms":1}]',
    '{}',
])
def test_parse_stats_rejects_invalid(bad):
    with pytest.raises(ValueError):
        qa.parse_stats(bad)


def test_delta_fails_if_one_nested_stage_missing():
    after = {name: (1, 1.0, 1.0) for name in qa.STAGES}
    after.pop("alpha_hunter_capture_shadow_decision_quote_v01")
    with pytest.raises(ValueError, match="Missing expected"):
        qa.delta({}, after)


def test_delta_rejects_no_increment():
    same = {name: (1, 1.0, 1.0) for name in qa.STAGES}
    with pytest.raises(ValueError, match="No trustworthy"):
        qa.delta(same, same)
