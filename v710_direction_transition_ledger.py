from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import requests

from alpha_hunter.storage import SupabaseConfig


TABLE = "alpha_hunter_direction_transition_ledger"
MODEL_VERSION = "7.10-direction-transition-ledger-v1"


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def f(
    value: Any,
) -> float | None:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def i(
    value: Any,
) -> int | None:
    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def score_leader(
    long_score: float,
    short_score: float,
) -> str:
    if long_score > short_score:
        return "LONG"

    if short_score > long_score:
        return "SHORT"

    return "TIE"


def transition_snapshot_id(
    production_run_id: str,
    episode_id: str,
    evaluated_at_utc: str,
    source_shadow_id: str | None,
) -> str:
    raw = (
        f"{production_run_id}|"
        f"{episode_id}|"
        f"{evaluated_at_utc}|"
        f"{source_shadow_id or ''}|"
        f"{MODEL_VERSION}"
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        raw
    ).hexdigest()[:32]


def source_evidence(
    row: dict[str, Any],
) -> dict[str, Any]:
    value = row.get(
        "evidence"
    )

    if isinstance(
        value,
        dict,
    ):
        return dict(value)

    return {}


def build_transition_row(
    source: dict[str, Any],
    production_run_id: str,
    *,
    production_version: str | None = None,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    production_run_id = str(
        production_run_id
        or ""
    ).strip()

    if not production_run_id:
        raise ValueError(
            "production_run_id is required"
        )

    episode_id = str(
        source.get(
            "episode_id"
        )
        or ""
    ).strip()

    symbol = str(
        source.get(
            "symbol"
        )
        or ""
    ).strip()

    evaluated_at_utc = str(
        source.get(
            "evaluated_at_utc"
        )
        or ""
    ).strip()

    source_model_version = str(
        source.get(
            "model_version"
        )
        or ""
    ).strip()

    direction = str(
        source.get(
            "direction"
        )
        or ""
    ).upper()

    if not episode_id:
        raise ValueError(
            "episode_id is required"
        )

    if not symbol:
        raise ValueError(
            "symbol is required"
        )

    if not evaluated_at_utc:
        raise ValueError(
            "evaluated_at_utc is required"
        )

    if not source_model_version:
        raise ValueError(
            "source model_version is required"
        )

    if direction not in {
        "UNKNOWN",
        "LONG",
        "SHORT",
    }:
        raise ValueError(
            f"invalid direction: {direction}"
        )

    long_score = f(
        source.get(
            "long_score"
        )
    )

    short_score = f(
        source.get(
            "short_score"
        )
    )

    if (
        long_score is None
        or short_score is None
    ):
        raise ValueError(
            "long_score and short_score "
            "are required"
        )

    captured_at = (
        captured_at
        or utc_now()
    )

    evidence = source_evidence(
        source
    )

    source_shadow_id = (
        str(
            source.get(
                "shadow_id"
            )
            or ""
        ).strip()
        or None
    )

    leader = score_leader(
        long_score,
        short_score,
    )

    best_score = max(
        long_score,
        short_score,
    )

    score_margin = abs(
        long_score
        - short_score
    )

    confidence = f(
        source.get(
            "confidence"
        )
    )

    return {
        "snapshot_id":
            transition_snapshot_id(
                production_run_id,
                episode_id,
                evaluated_at_utc,
                source_shadow_id,
            ),

        "production_run_id":
            production_run_id,

        "episode_id":
            episode_id,

        "symbol":
            symbol,

        "path":
            source.get(
                "path"
            ),

        "source_shadow_id":
            source_shadow_id,

        "source_model_version":
            source_model_version,

        "evaluated_at_utc":
            evaluated_at_utc,

        "captured_at_utc":
            captured_at.isoformat(),

        "market_price":
            f(
                source.get(
                    "market_price"
                )
            ),

        "direction_verdict":
            direction,

        "confidence":
            confidence,

        "long_score":
            long_score,

        "short_score":
            short_score,

        "score_leader":
            leader,

        "best_score":
            best_score,

        "score_margin":
            score_margin,

        "ema_15m_bias":
            source.get(
                "ema_15m_bias"
            ),

        "ema_1h_bias":
            source.get(
                "ema_1h_bias"
            ),

        "momentum_15m":
            f(
                source.get(
                    "momentum_15m"
                )
            ),

        "momentum_1h":
            f(
                source.get(
                    "momentum_1h"
                )
            ),

        "structure_15m":
            source.get(
                "structure_15m"
            ),

        "structure_1h":
            source.get(
                "structure_1h"
            ),

        "lifecycle_state":
            evidence.get(
                "lifecycle_state"
            ),

        "v74_rank":
            i(
                evidence.get(
                    "v74_rank"
                )
            ),

        "v74_score":
            f(
                evidence.get(
                    "v74_score"
                )
            ),

        "v741_shadow_score":
            f(
                evidence.get(
                    "v741_shadow_score"
                )
            ),

        "first_detection_price":
            f(
                evidence.get(
                    "first_detection_price"
                )
            ),

        "max_up_excursion_pct":
            f(
                evidence.get(
                    "max_up_excursion_pct"
                )
            ),

        "max_down_excursion_pct":
            f(
                evidence.get(
                    "max_down_excursion_pct"
                )
            ),

        "evidence": {
            "audit_type":
                "IMMUTABLE_DIRECTION_TRANSITION",

            "source_evidence":
                evidence,

            "production_version":
                production_version,

            "source_direction_verdict":
                direction,

            "score_leader":
                leader,

            "score_margin":
                score_margin,

            "capture_before_source_overwrite":
                True,

            "immutable_transition_capture":
                True,
        },

        "model_version":
            MODEL_VERSION,

        "capture_mode":
            "SHADOW",

        "trade_permission":
            False,
    }


def build_transition_rows(
    source_rows: list[
        dict[str, Any]
    ],
    production_run_id: str,
    *,
    production_version: str | None = None,
    captured_at: datetime | None = None,
) -> list[
    dict[str, Any]
]:
    if not str(
        production_run_id
        or ""
    ).strip():
        raise ValueError(
            "production_run_id is required"
        )

    captured_at = (
        captured_at
        or utc_now()
    )

    result = []

    seen_episodes = set()

    for source in source_rows:
        episode_id = str(
            source.get(
                "episode_id"
            )
            or ""
        ).strip()

        if episode_id in seen_episodes:
            raise ValueError(
                "duplicate episode in "
                "production-run capture: "
                f"{episode_id}"
            )

        seen_episodes.add(
            episode_id
        )

        result.append(
            build_transition_row(
                source,
                production_run_id,
                production_version=
                    production_version,
                captured_at=
                    captured_at,
            )
        )

    return result


def insert_transition_rows(
    settings: SupabaseConfig,
    rows: list[
        dict[str, Any]
    ],
) -> int:
    if not rows:
        return 0

    for row in rows:
        if row.get(
            "trade_permission"
        ) is not False:
            raise ValueError(
                "V7.10 transition ledger "
                "cannot grant trade permission"
            )

    response = requests.post(
        (
            f"{settings.url}"
            f"/rest/v1/{TABLE}"
        ),
        headers={
            "apikey":
                settings.key,

            "Authorization":
                f"Bearer {settings.key}",

            "Content-Type":
                "application/json",

            "Prefer":
                "return=minimal",
        },
        data=json.dumps(
            rows,
            separators=(
                ",",
                ":",
            ),
        ),
        timeout=(
            settings.timeout_seconds
        ),
    )

    if response.status_code not in {
        200,
        201,
        204,
    }:
        raise RuntimeError(
            "V7.10 immutable direction "
            "transition save failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    return len(rows)
