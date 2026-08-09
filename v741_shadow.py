from __future__ import annotations

from typing import Any


VERSION = "7.4.1-shadow"


def f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def reversal_shadow_score(
    item: dict[str, Any],
) -> dict[str, Any]:

    pre_move = (
        item.get("pre_move")
        or {}
    )

    features = (
        pre_move.get("features")
        or {}
    )

    behaviour = (
        item.get("behaviour")
        or {}
    )

    base = f(
        item.get(
            "pre_move_score"
        )
    ) or 0.0

    if (
        item.get("pre_move_path")
        != "REVERSAL"
    ):
        return {
            "version": VERSION,
            "eligible": False,
            "score": 0.0,
            "reasons": [],
        }

    score = 0.0
    reasons = []

    behaviour_score = f(
        item.get(
            "behaviour_score"
        )
    )

    if behaviour_score is None:
        behaviour_score = f(
            behaviour.get("score")
        )

    volatility = f(
        features.get(
            "volatility_pct"
        )
    )

    compression = f(
        features.get(
            "compression_score"
        )
    )

    rsi15 = f(
        features.get(
            "rsi_15m"
        )
    )

    rsi1 = f(
        features.get(
            "rsi_1h"
        )
    )

    rsi4 = f(
        features.get(
            "rsi_4h"
        )
    )

    trend15 = features.get(
        "trend_15m"
    )

    trend1 = features.get(
        "trend_1h"
    )

    ema1 = features.get(
        "ema_1h"
    )

    ema4 = features.get(
        "ema_4h"
    )

    # -----------------------------------------
    # STRUCTURE
    # -----------------------------------------

    if ema4 == "BULLISH":
        score += 2.0
        reasons.append(
            "EMA4_BULL"
        )

    if ema1 == "MIXED":
        score += 1.5
        reasons.append(
            "EMA1_MIXED"
        )

    if trend1 == "BEARISH":
        score += 1.5
        reasons.append(
            "TREND1_BEARISH"
        )

    elif trend1 == "NEUTRAL":
        score += 0.5
        reasons.append(
            "TREND1_NEUTRAL"
        )

    if trend15 == "BEARISH":
        score += 1.0
        reasons.append(
            "TREND15_BEARISH"
        )

    # -----------------------------------------
    # RSI RESET PROFILE
    # -----------------------------------------

    if (
        rsi15 is not None
        and 32 <= rsi15 <= 44
    ):
        score += 2.0
        reasons.append(
            "RSI15_WIN_ZONE"
        )

    elif (
        rsi15 is not None
        and 44 < rsi15 <= 50
    ):
        score += 0.5
        reasons.append(
            "RSI15_ACCEPTABLE"
        )

    if (
        rsi1 is not None
        and 38 <= rsi1 <= 46
    ):
        score += 1.5
        reasons.append(
            "RSI1_WIN_ZONE"
        )

    if (
        rsi4 is not None
        and 50 <= rsi4 <= 60
    ):
        score += 0.75
        reasons.append(
            "RSI4_STRUCTURE"
        )

    # -----------------------------------------
    # PARTICIPATION / ENERGY
    # -----------------------------------------

    if (
        behaviour_score is not None
        and behaviour_score >= 4.2
    ):
        score += 1.5
        reasons.append(
            "BEHAVIOUR_STRONG"
        )

    elif (
        behaviour_score is not None
        and behaviour_score >= 3.8
    ):
        score += 0.75
        reasons.append(
            "BEHAVIOUR_OK"
        )

    if (
        volatility is not None
        and 3.0 <= volatility <= 8.0
    ):
        score += 2.0
        reasons.append(
            "VOL_WIN_ZONE"
        )

    elif (
        volatility is not None
        and 2.0 <= volatility < 3.0
    ):
        score += 0.5
        reasons.append(
            "VOL_ACCEPTABLE"
        )

    # Extreme volatility was associated with
    # several downside cases.
    if (
        volatility is not None
        and volatility > 10
    ):
        score -= 2.0
        reasons.append(
            "VOL_EXTREME_PENALTY"
        )

    # -----------------------------------------
    # COMPRESSION
    # -----------------------------------------

    if (
        compression is not None
        and 4 <= compression <= 7.5
    ):
        score += 1.0
        reasons.append(
            "COMP_BALANCED"
        )

    elif (
        compression is not None
        and compression >= 8.5
    ):
        score -= 0.75
        reasons.append(
            "COMP_OVERCOMPRESSED"
        )

    # Preserve some information from the
    # original V7.4 score without allowing
    # it to dominate.
    score += min(
        base / 10,
        1.5,
    )

    return {
        "version":
            VERSION,

        "eligible":
            True,

        "score":
            round(
                score,
                2,
            ),

        "reasons":
            reasons,

        "source_v74_score":
            base,
    }


def apply_shadow_scores(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    candidates = []

    for item in records:
        result = (
            reversal_shadow_score(
                item
            )
        )

        item[
            "v741_shadow"
        ] = result

        item[
            "v741_shadow_score"
        ] = result[
            "score"
        ]

        item[
            "v741_shadow_rank"
        ] = None

        if result[
            "eligible"
        ]:
            candidates.append(
                item
            )

    candidates.sort(
        key=lambda row:
            row.get(
                "v741_shadow_score"
            )
            or 0,
        reverse=True,
    )

    for rank, item in enumerate(
        candidates,
        1,
    ):
        item[
            "v741_shadow_rank"
        ] = rank

    return candidates
