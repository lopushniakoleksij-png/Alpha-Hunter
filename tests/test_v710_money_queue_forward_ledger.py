import json

import pytest

from v710_money_queue_forward_ledger import (
    append_rows,
    build_ledger_row,
    capture,
    observation_id,
)


def candidate():
    return {
        "symbol":
            "SOLUSDT",

        "direction":
            "LONG",

        "current_price":
            96.244,

        "current_rr":
            1.77,

        "required_entry":
            94.26083333333334,

        "distance_from_current_pct":
            -2.06,

        "price_ready":
            False,

        "stop":
            92.555,

        "stop_timeframe":
            "15m",

        "target":
            102.79,

        "target_timeframe":
            "1H",

        "planned_rr":
            5.0,

        "planned_risk_pct":
            1.81,

        "planned_atr_x":
            2.44,

        "market_phase":
            "COMPRESSION",

        "opportunity_timing":
            "EARLY",

        "behaviour_score":
            4.99,

        "missing_non_rr_checks": [
            "participation_confirmed",
        ],

        "production_blockers": [
            "CURRENT_TRADE_PERMISSION_FALSE",
        ],

        "production_trade_permission":
            False,

        "production_v7_trade_ready":
            False,
    }


def test_observation_id_is_stable():
    one = observation_id(
        "run-1",
        candidate(),
    )

    two = observation_id(
        "run-1",
        candidate(),
    )

    assert one == two


def test_row_is_frozen_shadow():
    row = build_ledger_row(
        candidate(),
        "run-1",
        "2026-08-23T01:11:00+00:00",
        captured_at_utc=(
            "2026-08-23T01:12:00+00:00"
        ),
    )

    assert (
        row[
            "shadow_trade_permission"
        ]
        is False
    )

    assert (
        row[
            "shadow_only"
        ]
        is True
    )

    assert (
        row[
            "outcome"
        ]
        == "PENDING"
    )

    assert (
        row[
            "entry_touched_later"
        ]
        is None
    )


def test_append_is_idempotent(
    tmp_path,
):
    path = (
        tmp_path
        / "ledger.jsonl"
    )

    row = build_ledger_row(
        candidate(),
        "run-1",
        "2026-08-23T01:11:00+00:00",
        captured_at_utc=(
            "2026-08-23T01:12:00+00:00"
        ),
    )

    assert (
        append_rows(
            path,
            [row],
        )
        == 1
    )

    assert (
        append_rows(
            path,
            [row],
        )
        == 0
    )

    lines = (
        path
        .read_text()
        .splitlines()
    )

    assert len(lines) == 1

    saved = json.loads(
        lines[0]
    )

    assert (
        saved[
            "observation_id"
        ]
        == row[
            "observation_id"
        ]
    )


def test_capture_rejects_wrong_run():
    snapshot = {
        "production_run_id":
            "actual-run",

        "collected_at_utc":
            "2026-08-23T01:11:00+00:00",

        "symbols": [],
    }

    config = {
        "candidate_quality": {
            "minimum_execution_reward_risk":
                5.0,

            "minimum_execution_score":
                7.5,
        }
    }

    with pytest.raises(
        ValueError,
        match="does not match",
    ):
        capture(
            snapshot,
            config,
            "wrong-run",
        )


def test_capture_accepts_exact_run():
    snapshot = {
        "production_run_id":
            "run-1",

        "collected_at_utc":
            "2026-08-23T01:11:00+00:00",

        "symbols": [],
    }

    config = {
        "candidate_quality": {
            "minimum_execution_reward_risk":
                5.0,

            "minimum_execution_score":
                7.5,
        }
    }

    assert (
        capture(
            snapshot,
            config,
            "run-1",
        )
        == []
    )
