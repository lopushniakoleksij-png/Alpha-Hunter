from __future__ import annotations

from alpha_hunter.big_mover_evidence import (
    build_forward_evidence,
    build_live_candidates,
    extract_numeric_features,
    summarize_evidence,
)


def feature(
    symbol: str,
    captured: str,
    move: float,
    *,
    direction: str | None = None,
    state: str | None = None,
    volume: float = 1.0,
    rs: float = 0.0,
):
    return {
        "symbol": symbol,
        "captured_at_utc": captured,
        "direction": direction,
        "state": state,
        "volume_ratio": volume,
        "relative_strength_btc": rs,
        "source_payload": {
            "change_24h_pct": move,
            "behaviour": {
                "score": 4.2,
                "spread_pct": 0.05,
                "funding_change_pct": 12.0,
                "components": {
                    "volume_acceleration": 0.8,
                    "trend_acceleration": 1.0,
                },
            },
        },
    }


def audit(
    symbol: str,
    at: str,
    direction: str,
    threshold: float,
):
    return {
        "symbol": symbol,
        "audited_at_utc": at,
        "mover_direction": direction,
        "mover_threshold_pct": threshold,
        "current_24h_move_pct": threshold,
    }


def test_forward_label_uses_future_major_mover_without_legacy_direction_gate():
    rows = [
        feature(
            "EARLYUSDT",
            "2026-09-01T00:00:00+00:00",
            1.5,
            direction=None,
            volume=3.0,
            rs=2.0,
        )
    ]
    audits = [
        audit("EARLYUSDT", "2026-09-01T08:00:00+00:00", "UP", 5.0),
        audit("EARLYUSDT", "2026-09-01T12:00:00+00:00", "UP", 10.0),
    ]

    evidence = build_forward_evidence(rows, audits)
    long_rows = [row for row in evidence if row["direction"] == "LONG"]
    short_rows = [row for row in evidence if row["direction"] == "SHORT"]

    assert len(long_rows) == 1
    assert long_rows[0]["label"] == "MOVER"
    assert long_rows[0]["is_pre_expansion"] is True
    assert long_rows[0]["scanner_direction"] is None

    assert len(short_rows) == 1
    assert short_rows[0]["label"] == "CONTROL"


def test_grey_zone_is_excluded_from_training():
    rows = [feature("GREYUSDT", "2026-09-01T00:00:00+00:00", 2.0)]
    audits = [audit("GREYUSDT", "2026-09-01T06:00:00+00:00", "UP", 5.0)]

    evidence = build_forward_evidence(rows, audits)

    assert not [
        row
        for row in evidence
        if row["direction"] == "LONG"
    ]
    assert [
        row
        for row in evidence
        if row["direction"] == "SHORT"
        and row["label"] == "CONTROL"
    ]


def test_snapshot_already_at_five_percent_is_not_pre_expansion_training_data():
    rows = [feature("LATEUSDT", "2026-09-01T00:00:00+00:00", 5.0)]
    audits = [audit("LATEUSDT", "2026-09-01T04:00:00+00:00", "UP", 10.0)]

    assert build_forward_evidence(rows, audits) == []


def test_major_event_after_horizon_does_not_turn_control_into_mover():
    rows = [feature("SLOWUSDT", "2026-09-01T00:00:00+00:00", 1.0)]
    audits = [audit("SLOWUSDT", "2026-09-02T02:00:00+00:00", "UP", 10.0)]

    evidence = build_forward_evidence(rows, audits, horizon_hours=24)
    long_row = next(row for row in evidence if row["direction"] == "LONG")

    assert long_row["label"] == "CONTROL"


def test_live_rows_are_scored_both_long_and_short():
    rows = [
        feature(
            "BOTHUSDT",
            "2026-09-13T08:00:00+00:00",
            0.7,
            direction="LONG",
            state="DIRECTION_EMERGING_LONG",
            volume=2.5,
            rs=1.2,
        )
    ]

    candidates = build_live_candidates(rows)

    assert len(candidates) == 2
    assert {row["direction"] for row in candidates} == {"LONG", "SHORT"}
    assert all(row["scanner_direction"] == "LONG" for row in candidates)
    assert all(row["features"]["volume_ratio"] == 2.5 for row in candidates)


def test_numeric_feature_extraction_keeps_observed_extra_components():
    row = feature(
        "FEATUREUSDT",
        "2026-09-13T08:00:00+00:00",
        0.3,
        volume=4.0,
        rs=2.5,
    )

    features = extract_numeric_features(row)

    assert features["volume_ratio"] == 4.0
    assert features["relative_strength_btc"] == 2.5
    assert features["behaviour_score"] == 4.2
    assert features["funding_change_pct"] == 12.0
    assert features["volume_acceleration_component"] == 0.8


def test_summary_preserves_direction_and_false_positive_counts():
    evidence = [
        {
            "symbol": "AUSDT",
            "direction": "LONG",
            "label": "MOVER",
        },
        {
            "symbol": "BUSDT",
            "direction": "LONG",
            "label": "CONTROL",
        },
        {
            "symbol": "CUSDT",
            "direction": "SHORT",
            "label": "MOVER",
        },
    ]

    summary = summarize_evidence(evidence)

    assert summary["rows"] == 3
    assert summary["counts"]["LONG"] == {"MOVER": 1, "CONTROL": 1}
    assert summary["counts"]["SHORT"] == {"MOVER": 1, "CONTROL": 0}
    assert summary["unique_symbols"]["LONG"]["MOVER"] == 1
