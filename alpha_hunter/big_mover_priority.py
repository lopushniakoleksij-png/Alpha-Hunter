from __future__ import annotations

from typing import Any, Iterable


EARLY_MOVER_CEILING_PCT = 5.0


def _maturity_tier(candidate: Any) -> int:
    move = getattr(candidate, "directional_move_pct", None)
    lifecycle = str(getattr(candidate, "lifecycle", "") or "")

    if move is not None and 1.0 <= float(move) < EARLY_MOVER_CEILING_PCT:
        return 0
    if lifecycle == "PRE_MOVER":
        return 1
    if lifecycle == "IGNITION":
        return 2
    if lifecycle == "EXPANSION":
        return 3
    return 4


def prioritize_early_money(candidates: Iterable[Any]) -> list[Any]:
    """Put 1-5% ignition and true pre-movers ahead of mature ignition.

    Five percent is not a new trading threshold: it is the first canonical mover
    boundary already used by the missed-mover auditor and the mover/control labels.
    Similarity still ranks candidates inside the same maturity tier.
    """
    status_priority = {
        "SHADOW_QUEUE": 0,
        "WATCH": 1,
        "RETEST_ONLY": 2,
        "RESEARCH_ONLY": 3,
    }

    return sorted(
        candidates,
        key=lambda item: (
            status_priority.get(str(getattr(item, "research_status", "")), 9),
            _maturity_tier(item),
            -(
                float(getattr(item, "similarity_score", -1.0))
                if getattr(item, "similarity_score", None) is not None
                else -1.0
            ),
            -float(getattr(item, "feature_coverage", 0.0) or 0.0),
            str(getattr(item, "symbol", "")),
        ),
    )


def is_early_entry_candidate(candidate: Any) -> bool:
    move = getattr(candidate, "directional_move_pct", None)
    if move is None:
        return False
    return (
        str(getattr(candidate, "research_status", "")) == "SHADOW_QUEUE"
        and float(move) < EARLY_MOVER_CEILING_PCT
        and str(getattr(candidate, "lifecycle", "")) in {"PRE_MOVER", "IGNITION"}
    )
