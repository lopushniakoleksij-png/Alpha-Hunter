from __future__ import annotations

from dataclasses import dataclass

from alpha_hunter.big_mover_priority import (
    is_early_entry_candidate,
    prioritize_early_money,
)


@dataclass
class Candidate:
    symbol: str
    research_status: str
    lifecycle: str
    directional_move_pct: float
    similarity_score: float
    feature_coverage: float = 1.0


def test_one_to_five_percent_ignition_beats_mature_ignition():
    mature = Candidate(
        symbol="MATUREUSDT",
        research_status="SHADOW_QUEUE",
        lifecycle="IGNITION",
        directional_move_pct=12.0,
        similarity_score=80.0,
    )
    early = Candidate(
        symbol="EARLYUSDT",
        research_status="SHADOW_QUEUE",
        lifecycle="IGNITION",
        directional_move_pct=2.5,
        similarity_score=45.0,
    )

    ranked = prioritize_early_money([mature, early])

    assert ranked[0].symbol == "EARLYUSDT"
    assert is_early_entry_candidate(early) is True
    assert is_early_entry_candidate(mature) is False


def test_pre_mover_beats_mature_ignition_after_early_ignition_bucket():
    pre = Candidate(
        symbol="PREUSDT",
        research_status="SHADOW_QUEUE",
        lifecycle="PRE_MOVER",
        directional_move_pct=0.4,
        similarity_score=35.0,
    )
    mature = Candidate(
        symbol="MATUREUSDT",
        research_status="SHADOW_QUEUE",
        lifecycle="IGNITION",
        directional_move_pct=8.0,
        similarity_score=70.0,
    )

    assert prioritize_early_money([mature, pre])[0].symbol == "PREUSDT"
