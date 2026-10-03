from pathlib import Path

import pytest

from alpha_hunter.collector import load_config
from alpha_hunter.scientific_identity import build_scientific_fingerprint
from ops.r8_depth_shadow import classify_depth
from ops.runtime_release_fingerprint import runtime_release_paths


ROOT = Path(__file__).resolve().parents[1]


def _order(*, direction="LONG", limit_price=101.0, remaining_quantity=5.0):
    return {
        "order_id": "order-r8-shadow-test",
        "decision_id": "decision-r8-shadow-test",
        "symbol": "TESTUSDT",
        "direction": direction,
        "limit_price": limit_price,
        "remaining_quantity": remaining_quantity,
    }


def _depth(*, asks=None, bids=None):
    return {
        "asks": asks or [["100", "3"], ["101", "4"], ["102", "5"]],
        "bids": bids or [["99", "10"], ["98", "20"]],
        "ts": "1791012345678",
        "precision": "scale0",
        "scale": "0.1",
        "isMaxPrecision": "YES",
    }


def test_long_depth_can_be_sufficient_when_l1_is_not():
    row = classify_depth(
        order=_order(),
        depth=_depth(),
        strategy_id="S2",
        captured_at_utc="2026-10-03T08:00:00+00:00",
        request_time_ms=1791012345680,
    )

    assert row["crossed_limit"] is True
    assert row["top_side_size"] == pytest.approx(3.0)
    assert row["eligible_depth_quantity"] == pytest.approx(7.0)
    assert row["conservative_vwap"] == pytest.approx(100.4)
    assert row["diagnostic_verdict"] == (
        "DEPTH_SUFFICIENT_BUT_L1_INSUFFICIENT"
    )


def test_true_insufficient_depth_is_preserved():
    row = classify_depth(
        order=_order(remaining_quantity=10.0),
        depth=_depth(),
        strategy_id="S2",
        captured_at_utc="2026-10-03T08:00:00+00:00",
    )

    assert row["crossed_limit"] is True
    assert row["eligible_depth_quantity"] == pytest.approx(7.0)
    assert row["conservative_vwap"] is None
    assert row["diagnostic_verdict"] == "TRUE_INSUFFICIENT_DEPTH"


def test_short_uses_bid_depth_at_or_above_limit():
    row = classify_depth(
        order=_order(
            direction="SHORT",
            limit_price=99.0,
            remaining_quantity=6.0,
        ),
        depth=_depth(
            asks=[["101", "20"]],
            bids=[["100", "2"], ["99.5", "3"], ["99", "4"], ["98.5", "20"]],
        ),
        strategy_id="S4",
        captured_at_utc="2026-10-03T08:00:00+00:00",
    )

    assert row["crossed_limit"] is True
    assert row["top_side_size"] == pytest.approx(2.0)
    assert row["eligible_depth_quantity"] == pytest.approx(9.0)
    assert row["diagnostic_verdict"] == (
        "DEPTH_SUFFICIENT_BUT_L1_INSUFFICIENT"
    )
    assert row["conservative_vwap"] == pytest.approx(
        (100.0 * 2.0 + 99.5 * 3.0 + 99.0 * 1.0) / 6.0
    )


def test_non_cross_and_l1_sufficient_are_not_misclassified():
    not_crossed = classify_depth(
        order=_order(limit_price=99.0),
        depth=_depth(),
        strategy_id="S2",
        captured_at_utc="2026-10-03T08:00:00+00:00",
    )
    assert not_crossed["diagnostic_verdict"] == "NOT_CROSSED"

    l1_sufficient = classify_depth(
        order=_order(limit_price=101.0, remaining_quantity=2.0),
        depth=_depth(),
        strategy_id="S2",
        captured_at_utc="2026-10-03T08:00:00+00:00",
    )
    assert l1_sufficient["diagnostic_verdict"] == "L1_SUFFICIENT"


def test_shadow_row_cannot_claim_execution_authority():
    row = classify_depth(
        order=_order(),
        depth=_depth(),
        strategy_id="S2",
        captured_at_utc="2026-10-03T08:00:00+00:00",
    )

    assert row["shadow_only"] is True
    assert row["paper_only"] is True
    assert row["trade_permission"] is False
    assert row["production_promotion_permitted"] is False
    assert row["order_path"] == "NONE"
    assert row["evidence"]["r8_fill_model_changed"] is False
    assert row["evidence"]["historical_outcome_reinterpreted"] is False
    assert row["evidence"]["profitability_sample_eligible"] is False
    assert row["evidence"]["exchange_order_request_added"] is False


def test_depth_shadow_files_are_outside_sealed_scientific_fingerprint():
    config = load_config(ROOT / "config.json")
    result = build_scientific_fingerprint(config, root=ROOT)

    assert "ops/r8_depth_shadow.py" not in result["files"]
    assert "ops/sql/r8_depth_shadow_v01.sql" not in result["files"]


def test_depth_shadow_collector_is_outside_render_runtime_fingerprint():
    paths = {
        path.relative_to(ROOT).as_posix()
        for path in runtime_release_paths(ROOT)
    }
    assert "ops/r8_depth_shadow.py" not in paths
