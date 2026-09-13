from __future__ import annotations

import pytest

from alpha_hunter.big_mover_signature import (
    build_directional_signature,
    classify_lifecycle,
    rank_candidates,
    score_candidate,
)


UNIVERSE_CFG = {
    "quiet_24h_abs_change_max_pct": 3.0,
    "early_ignition_min_abs_change_pct": 1.0,
    "early_ignition_max_abs_change_pct": 15.0,
    "maximum_24h_extension_pct": 25.0,
}


def example(
    *,
    label: str,
    direction: str,
    volume_ratio: float,
    oi: float,
    rs: float,
    pre: bool = True,
):
    return {
        "label": label,
        "direction": direction,
        "is_pre_expansion": pre,
        "features": {
            "volume_ratio": volume_ratio,
            "open_interest_change_pct": oi,
            "relative_strength_btc": rs,
        },
    }


def long_training():
    return [
        example(label="MOVER", direction="LONG", volume_ratio=4.0, oi=12.0, rs=4.0),
        example(label="MOVER", direction="LONG", volume_ratio=5.0, oi=15.0, rs=5.0),
        example(label="MOVER", direction="LONG", volume_ratio=6.0, oi=18.0, rs=6.0),
        example(label="CONTROL", direction="LONG", volume_ratio=1.0, oi=1.0, rs=0.2),
        example(label="CONTROL", direction="LONG", volume_ratio=1.2, oi=2.0, rs=0.4),
        example(label="CONTROL", direction="LONG", volume_ratio=1.4, oi=3.0, rs=0.6),
    ]


def short_training():
    return [
        example(label="MOVER", direction="SHORT", volume_ratio=3.5, oi=10.0, rs=-5.0),
        example(label="MOVER", direction="SHORT", volume_ratio=4.0, oi=13.0, rs=-6.0),
        example(label="MOVER", direction="SHORT", volume_ratio=4.5, oi=16.0, rs=-7.0),
        example(label="CONTROL", direction="SHORT", volume_ratio=1.0, oi=1.0, rs=-0.2),
        example(label="CONTROL", direction="SHORT", volume_ratio=1.1, oi=2.0, rs=-0.4),
        example(label="CONTROL", direction="SHORT", volume_ratio=1.2, oi=3.0, rs=-0.6),
    ]


def live(symbol: str, direction: str, move: float, volume: float, oi: float, rs: float):
    return {
        "symbol": symbol,
        "direction": direction,
        "change_24h_pct": move,
        "features": {
            "volume_ratio": volume,
            "open_interest_change_pct": oi,
            "relative_strength_btc": rs,
        },
    }


def test_signature_weights_are_learned_from_movers_vs_controls():
    signature = build_directional_signature(
        long_training(),
        "LONG",
        feature_names=(
            "volume_ratio",
            "open_interest_change_pct",
            "relative_strength_btc",
        ),
    )

    assert signature.direction == "LONG"
    assert signature.mover_examples == 3
    assert signature.control_examples == 3
    assert signature.total_weight > 0
    assert signature.edge_state == "UNPROVEN"
    assert signature.shadow_only is True
    assert signature.trade_permission is False

    by_name = {item.name: item for item in signature.feature_profiles}
    assert by_name["volume_ratio"].mover_median == 5.0
    assert by_name["volume_ratio"].control_median == 1.2
    assert all(item.weight > 0 for item in signature.feature_profiles)


def test_post_expansion_winner_cannot_train_the_profile():
    records = [
        example(
            label="MOVER",
            direction="LONG",
            volume_ratio=8.0,
            oi=30.0,
            rs=10.0,
            pre=False,
        ),
        example(label="CONTROL", direction="LONG", volume_ratio=1.0, oi=1.0, rs=0.0),
    ]

    with pytest.raises(ValueError, match="no pre-expansion LONG mover examples"):
        build_directional_signature(records, "LONG")


def test_false_positive_controls_are_required():
    movers_only = [row for row in long_training() if row["label"] == "MOVER"]

    with pytest.raises(ValueError, match="no pre-expansion LONG control examples"):
        build_directional_signature(movers_only, "LONG")


def test_candidate_close_to_mover_signature_scores_above_control_like_candidate():
    signature = build_directional_signature(
        long_training(),
        "LONG",
        feature_names=(
            "volume_ratio",
            "open_interest_change_pct",
            "relative_strength_btc",
        ),
    )

    mover_like = score_candidate(
        live("AUSDT", "LONG", 2.0, 5.2, 14.5, 5.1),
        signature,
        universe_scan_config=UNIVERSE_CFG,
    )
    control_like = score_candidate(
        live("BUSDT", "LONG", 2.0, 1.2, 2.0, 0.4),
        signature,
        universe_scan_config=UNIVERSE_CFG,
    )

    assert mover_like.similarity_score is not None
    assert control_like.similarity_score is not None
    assert mover_like.similarity_score > control_like.similarity_score
    assert mover_like.lifecycle == "IGNITION"
    assert mover_like.research_status == "SHADOW_QUEUE"
    assert mover_like.trade_permission is False


def test_long_and_short_profiles_are_kept_separate():
    long_signature = build_directional_signature(long_training(), "LONG")
    short_signature = build_directional_signature(short_training(), "SHORT")

    ranked = rank_candidates(
        [
            live("LONGUSDT", "LONG", 2.0, 5.0, 15.0, 5.0),
            live("SHORTUSDT", "SHORT", -3.0, 4.0, 13.0, -6.0),
        ],
        [long_signature, short_signature],
        universe_scan_config=UNIVERSE_CFG,
    )

    assert {item.direction for item in ranked} == {"LONG", "SHORT"}
    assert all(item.research_status == "SHADOW_QUEUE" for item in ranked)
    assert all(item.trade_permission is False for item in ranked)


def test_lifecycle_uses_existing_universe_configuration():
    assert classify_lifecycle(0.5, "LONG", UNIVERSE_CFG)[0] == "PRE_MOVER"
    assert classify_lifecycle(4.0, "LONG", UNIVERSE_CFG)[0] == "IGNITION"
    assert classify_lifecycle(20.0, "LONG", UNIVERSE_CFG)[0] == "EXPANSION"
    assert classify_lifecycle(30.0, "LONG", UNIVERSE_CFG)[0] == "EXTENDED"

    assert classify_lifecycle(-4.0, "SHORT", UNIVERSE_CFG)[0] == "IGNITION"
    assert classify_lifecycle(-20.0, "SHORT", UNIVERSE_CFG)[0] == "EXPANSION"
    assert classify_lifecycle(-30.0, "SHORT", UNIVERSE_CFG)[0] == "EXTENDED"


def test_extended_candidate_is_never_a_new_shadow_entry_queue():
    signature = build_directional_signature(long_training(), "LONG")
    result = score_candidate(
        live("CHASEUSDT", "LONG", 31.0, 5.0, 15.0, 5.0),
        signature,
        universe_scan_config=UNIVERSE_CFG,
    )

    assert result.lifecycle == "EXTENDED"
    assert result.research_status == "RESEARCH_ONLY"
    assert "EXTENDED_NO_CHASE" in result.blockers
    assert result.trade_permission is False


def test_opposite_direction_move_is_flagged_even_when_signature_matches():
    signature = build_directional_signature(long_training(), "LONG")
    result = score_candidate(
        live("WRONGWAYUSDT", "LONG", -8.0, 5.0, 15.0, 5.0),
        signature,
        universe_scan_config=UNIVERSE_CFG,
    )

    assert "CURRENT_MOVE_OPPOSES_DIRECTION" in result.blockers
    assert result.research_status == "WATCH"


def test_missing_live_features_fail_closed_to_watch():
    signature = build_directional_signature(long_training(), "LONG")
    result = score_candidate(
        {
            "symbol": "EMPTYUSDT",
            "direction": "LONG",
            "change_24h_pct": 2.0,
            "features": {},
        },
        signature,
        universe_scan_config=UNIVERSE_CFG,
    )

    assert result.similarity_score is None
    assert result.feature_coverage == 0.0
    assert "NO_SIGNATURE_FEATURES_AVAILABLE" in result.blockers
    assert result.research_status == "WATCH"
    assert result.trade_permission is False


def test_missing_lifecycle_config_never_creates_entry_permission():
    signature = build_directional_signature(long_training(), "LONG")
    result = score_candidate(
        live("CFGUSDT", "LONG", 2.0, 5.0, 15.0, 5.0),
        signature,
        universe_scan_config={},
    )

    assert result.research_status == "WATCH"
    assert any(blocker.startswith("MISSING_CONFIG_") for blocker in result.blockers)
    assert result.trade_permission is False
