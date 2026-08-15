from __future__ import annotations

import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any


LIFECYCLE_VERSION = "7.5"

EPISODE_GAP_HOURS = 3.0


VALID_STATES = (
    "NORMAL",
    "ANOMALY_DETECTED",
    "PRE_MOVE_DETECTED",
    "UNDER_SURVEILLANCE",
    "DIRECTION_EMERGING",
    "TRADE_READY",
    "EXPANSION",
    "EXTENDED",
    "FAILED",
)


STATE_ORDER = {
    state: index
    for index, state in enumerate(
        VALID_STATES
    )
}


def _f(
    value: Any,
) -> float | None:
    try:
        if value in (
            None,
            "",
            "N/A",
            "—",
        ):
            return None

        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def _dt(
    value: Any,
) -> datetime:
    if isinstance(
        value,
        datetime,
    ):
        dt = value

    else:
        text = str(
            value
        ).strip()

        if text.endswith("Z"):
            text = (
                text[:-1]
                + "+00:00"
            )

        if "." in text:
            left, right = (
                text.split(
                    ".",
                    1,
                )
            )

            timezone_suffix = ""

            plus_index = right.find("+")
            minus_index = right.find("-")

            split_index = -1

            if plus_index >= 0:
                split_index = plus_index

            elif minus_index >= 0:
                split_index = minus_index

            if split_index >= 0:
                fraction = right[
                    :split_index
                ]

                timezone_suffix = right[
                    split_index:
                ]

            else:
                fraction = right

            fraction = (
                fraction[:6]
                .ljust(
                    6,
                    "0",
                )
            )

            text = (
                left
                + "."
                + fraction
                + timezone_suffix
            )

        dt = datetime.fromisoformat(
            text
        )

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(
        timezone.utc
    )


def make_episode_id(
    symbol: str,
    path: str,
    first_detected_at_utc: Any,
) -> str:
    timestamp = _dt(
        first_detected_at_utc
    )

    raw = (
        f"{symbol.upper()}|"
        f"{path.upper()}|"
        f"{timestamp.isoformat()}"
    ).encode(
        "utf-8"
    )

    return (
        hashlib.sha256(
            raw
        )
        .hexdigest()[:24]
    )


@dataclass
class LifecycleEpisode:
    episode_id: str
    symbol: str
    path: str

    first_detected_at_utc: str
    last_detected_at_utc: str

    first_detection_price: float | None
    latest_price: float | None

    detections: int = 1

    lifecycle_state: str = (
        "PRE_MOVE_DETECTED"
    )

    previous_state: str | None = None

    v74_score: float | None = None
    v74_rank: int | None = None
    v74_tier: str | None = None

    v741_shadow_score: float | None = None
    v741_shadow_rank: int | None = None

    direction: str | None = None

    trade_permission: bool = False
    v7_trade_ready: bool = False

    max_favorable_excursion_pct: float = 0.0
    max_adverse_excursion_pct: float = 0.0

    expansion_3_hit: bool = False
    expansion_5_hit: bool = False
    expansion_10_hit: bool = False

    first_3pct_at_utc: str | None = None
    first_5pct_at_utc: str | None = None
    first_10pct_at_utc: str | None = None

    market_tracking_started_at_utc: str | None = None
    measurement_quality: str | None = None

    last_market_check_at_utc: str | None = None
    market_checks: int = 0

    max_up_excursion_pct: float = 0.0
    max_down_excursion_pct: float = 0.0

    expansion_direction: str | None = None

    finalized_at_utc: str | None = None
    is_finalized: bool = False

    final_classification: str | None = None

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return asdict(
            self
        )


def same_episode(
    episode: LifecycleEpisode,
    symbol: str,
    path: str,
    detected_at_utc: Any,
    gap_hours: float = EPISODE_GAP_HOURS,
) -> bool:
    if (
        episode.symbol.upper()
        != str(symbol).upper()
    ):
        return False

    if (
        episode.path.upper()
        != str(path).upper()
    ):
        return False

    current_time = _dt(
        detected_at_utc
    )

    last_time = _dt(
        episode.last_detected_at_utc
    )

    gap_seconds = (
        current_time
        - last_time
    ).total_seconds()

    return (
        0
        <= gap_seconds
        <= gap_hours * 3600
    )


def infer_state(
    record: dict[str, Any],
    previous_state: str | None = None,
) -> str:
    state = str(
        record.get(
            "state"
        )
        or ""
    ).upper()

    decision = str(
        record.get(
            "decision_state"
        )
        or ""
    ).upper()

    phase = str(
        record.get(
            "phase"
        )
        or ""
    ).upper()

    pre_move_state = str(
        record.get(
            "pre_move_state"
        )
        or ""
    ).upper()

    trade_permission = bool(
        record.get(
            "trade_permission"
        )
    )

    v7_trade_ready = bool(
        record.get(
            "v7_trade_ready"
        )
    )

    if (
        trade_permission
        or v7_trade_ready
        or state
        in {
            "LONG_READY",
            "SHORT_READY",
            "TRADE_READY",
        }
    ):
        candidate = "TRADE_READY"

    elif state.startswith(
        "DIRECTION_EMERGING"
    ):
        candidate = (
            "DIRECTION_EMERGING"
        )

    elif phase in {
        "EXPANSION",
        "BREAKDOWN",
    }:
        candidate = "EXPANSION"

    elif pre_move_state.startswith(
        "PRE_IGNITION_"
    ):
        candidate = (
            "PRE_MOVE_DETECTED"
        )

    elif decision in {
        "ANOMALY_DETECTED",
        "UNDER_SURVEILLANCE",
    }:
        candidate = (
            "UNDER_SURVEILLANCE"
            if decision
            == "UNDER_SURVEILLANCE"
            else "ANOMALY_DETECTED"
        )

    elif state.startswith(
        "WATCH_"
    ):
        candidate = (
            "UNDER_SURVEILLANCE"
        )

    else:
        candidate = "NORMAL"

    if previous_state is None:
        return candidate

    previous_state = (
        previous_state.upper()
    )

    if previous_state not in STATE_ORDER:
        return candidate

    if candidate not in STATE_ORDER:
        return previous_state

    # FAILED and EXTENDED are terminal unless
    # a new episode is created.
    if previous_state in {
        "FAILED",
        "EXTENDED",
    }:
        return previous_state

    # Do not allow accidental regression from
    # an advanced lifecycle state to NORMAL.
    if (
        STATE_ORDER[
            candidate
        ]
        < STATE_ORDER[
            previous_state
        ]
        and candidate
        in {
            "NORMAL",
            "ANOMALY_DETECTED",
            "PRE_MOVE_DETECTED",
        }
    ):
        return previous_state

    return candidate


def create_episode(
    record: dict[str, Any],
    detected_at_utc: Any,
) -> LifecycleEpisode:
    symbol = str(
        record.get(
            "symbol"
        )
        or ""
    ).upper()

    path = str(
        record.get(
            "pre_move_path"
        )
        or ""
    ).upper()

    if not symbol:
        raise ValueError(
            "Lifecycle episode requires symbol"
        )

    if path not in {
        "REVERSAL",
        "CONTINUATION",
    }:
        raise ValueError(
            "Lifecycle episode requires "
            "REVERSAL or CONTINUATION path"
        )

    timestamp = _dt(
        detected_at_utc
    ).isoformat()

    price = _f(
        record.get(
            "last_price"
        )
        or record.get(
            "reference_price"
        )
    )

    rank = record.get(
        "pre_move_rank"
    )

    try:
        rank = (
            int(rank)
            if rank is not None
            else None
        )

    except (
        TypeError,
        ValueError,
    ):
        rank = None

    shadow_rank = record.get(
        "v741_shadow_rank"
    )

    try:
        shadow_rank = (
            int(shadow_rank)
            if shadow_rank is not None
            else None
        )

    except (
        TypeError,
        ValueError,
    ):
        shadow_rank = None

    lifecycle_state = infer_state(
        record
    )

    return LifecycleEpisode(
        episode_id=make_episode_id(
            symbol,
            path,
            timestamp,
        ),

        symbol=symbol,
        path=path,

        first_detected_at_utc=timestamp,
        last_detected_at_utc=timestamp,

        first_detection_price=price,
        latest_price=price,

        lifecycle_state=lifecycle_state,

        v74_score=_f(
            record.get(
                "pre_move_score"
            )
        ),

        v74_rank=rank,

        v74_tier=record.get(
            "pre_move_tier"
        ),

        v741_shadow_score=_f(
            record.get(
                "v741_shadow_score"
            )
        ),

        v741_shadow_rank=shadow_rank,

        direction=record.get(
            "direction"
        ),

        trade_permission=bool(
            record.get(
                "trade_permission"
            )
        ),

        v7_trade_ready=bool(
            record.get(
                "v7_trade_ready"
            )
        ),
    )


def update_excursion(
    episode: LifecycleEpisode,
    current_price: Any,
    detected_at_utc: Any,
) -> None:
    price = _f(
        current_price
    )

    reference = (
        episode.first_detection_price
    )

    if (
        price is None
        or reference in (
            None,
            0,
        )
    ):
        return

    move_pct = (
        (
            price
            - reference
        )
        / reference
        * 100
    )

    episode.latest_price = price

    episode.max_favorable_excursion_pct = max(
        episode.max_favorable_excursion_pct,
        move_pct,
    )

    episode.max_adverse_excursion_pct = min(
        episode.max_adverse_excursion_pct,
        move_pct,
    )

    timestamp = _dt(
        detected_at_utc
    ).isoformat()

    abs_move = abs(
        move_pct
    )

    if (
        abs_move >= 3
        and not episode.expansion_3_hit
    ):
        episode.expansion_3_hit = True
        episode.first_3pct_at_utc = timestamp

    if (
        abs_move >= 5
        and not episode.expansion_5_hit
    ):
        episode.expansion_5_hit = True
        episode.first_5pct_at_utc = timestamp

    if (
        abs_move >= 10
        and not episode.expansion_10_hit
    ):
        episode.expansion_10_hit = True
        episode.first_10pct_at_utc = timestamp


def update_episode(
    episode: LifecycleEpisode,
    record: dict[str, Any],
    detected_at_utc: Any,
) -> LifecycleEpisode:
    timestamp = _dt(
        detected_at_utc
    ).isoformat()

    episode.last_detected_at_utc = timestamp

    episode.detections += 1

    episode.previous_state = (
        episode.lifecycle_state
    )

    episode.lifecycle_state = infer_state(
        record,
        previous_state=(
            episode.lifecycle_state
        ),
    )

    episode.direction = (
        record.get(
            "direction"
        )
        or episode.direction
    )

    episode.trade_permission = bool(
        record.get(
            "trade_permission"
        )
    )

    episode.v7_trade_ready = bool(
        record.get(
            "v7_trade_ready"
        )
    )

    update_excursion(
        episode,
        record.get(
            "last_price"
        )
        or record.get(
            "reference_price"
        ),
        timestamp,
    )

    if (
        episode.expansion_3_hit
        and episode.lifecycle_state
        not in {
            "TRADE_READY",
            "FAILED",
            "EXTENDED",
        }
    ):
        episode.previous_state = (
            episode.lifecycle_state
        )

        episode.lifecycle_state = (
            "EXPANSION"
        )

    return episode


def classify_episode(
    episode: LifecycleEpisode,
) -> str:
    if (
        episode.trade_permission
        and episode.expansion_5_hit
    ):
        return "TRADEABLE_WINNER"

    if (
        episode.expansion_5_hit
        and not episode.trade_permission
    ):
        return "NON_TRADEABLE_EXPANSION"

    if episode.expansion_3_hit:
        return "GOOD_DETECTION"

    if episode.lifecycle_state == "FAILED":
        return "FALSE_POSITIVE"

    if episode.lifecycle_state == "EXTENDED":
        return "LATE_DETECTION"

    if episode.lifecycle_state in {
        "DIRECTION_EMERGING",
        "TRADE_READY",
        "UNDER_SURVEILLANCE",
        "PRE_MOVE_DETECTED",
        "ANOMALY_DETECTED",
    }:
        return "ACTIVE"

    return "EARLY_DETECTION"

