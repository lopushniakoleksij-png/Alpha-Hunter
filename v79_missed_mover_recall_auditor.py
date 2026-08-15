from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig


ROOT = Path(__file__).resolve().parent

UNIVERSE_TABLE = "alpha_hunter_universe_hourly"
LIFECYCLE_TABLE = "alpha_hunter_lifecycle_episodes"
DIRECTION_TABLE = "alpha_hunter_direction_state"
TIMING_TABLE = "alpha_hunter_timing_rr_shadow"
AUDIT_TABLE = "alpha_hunter_missed_mover_audit"

MODEL_VERSION = "7.9-missed-mover-recall-v1"

THRESHOLDS = (
    5.0,
    10.0,
    20.0,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def dt(
    value: Any,
) -> datetime | None:

    if value in (
        None,
        "",
    ):
        return None

    if isinstance(
        value,
        datetime,
    ):
        result = value

    else:
        try:
            result = datetime.fromisoformat(
                str(value)
                .strip()
                .replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError:
            return None

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=timezone.utc
        )

    return result.astimezone(
        timezone.utc
    )


def f(
    value: Any,
) -> float | None:

    try:
        if value in (
            None,
            "",
        ):
            return None

        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def headers(
    settings: SupabaseConfig,
    *,
    merge: bool = False,
) -> dict[str, str]:

    result = {
        "apikey":
            settings.key,

        "Authorization":
            f"Bearer {settings.key}",

        "Content-Type":
            "application/json",
    }

    if merge:
        result["Prefer"] = (
            "resolution=merge-duplicates,"
            "return=minimal"
        )

    return result


def audit_hour(
    value: datetime,
) -> datetime:

    return value.replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def audit_id(
    symbol: str,
    bucket: datetime,
    threshold: float,
) -> str:

    raw = (
        f"{symbol.upper()}|"
        f"{MODEL_VERSION}|"
        f"{bucket.isoformat()}|"
        f"{threshold:.2f}"
    ).encode("utf-8")

    return hashlib.sha256(
        raw
    ).hexdigest()[:24]


def get_rows(
    settings: SupabaseConfig,
    table: str,
    params: dict[str, str],
) -> list[dict[str, Any]]:

    response = requests.get(
        (
            f"{settings.url}"
            f"/rest/v1/{table}"
        ),
        params=params,
        headers=headers(
            settings
        ),
        timeout=settings.timeout_seconds,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"{table} load failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    payload = response.json()

    if not isinstance(
        payload,
        list,
    ):
        return []

    return [
        row
        for row in payload
        if isinstance(
            row,
            dict,
        )
    ]


def get_rows_paginated(
    settings: SupabaseConfig,
    table: str,
    params: dict[str, str],
    *,
    page_size: int = 500,
    max_pages: int = 100,
) -> list[dict[str, Any]]:

    rows: list[dict[str, Any]] = []
    offset = 0

    for _ in range(max_pages):
        page_params = dict(params)
        page_params["limit"] = str(page_size)
        page_params["offset"] = str(offset)

        batch = get_rows(
            settings,
            table,
            page_params,
        )

        rows.extend(batch)

        if len(batch) < page_size:
            return rows

        offset += page_size

    raise RuntimeError(
        f"{table} pagination exceeded "
        f"{max_pages} pages"
    )


def load_universe_history(
    settings: SupabaseConfig,
    now: datetime,
) -> list[dict[str, Any]]:

    start = (
        now
        - timedelta(
            hours=26
        )
    )

    return get_rows_paginated(
        settings,
        UNIVERSE_TABLE,
        {
            "select": "*",
            "hour_bucket_utc":
                f"gte.{start.isoformat()}",
            "order":
                "hour_bucket_utc.asc,symbol.asc",
        },
    )


def load_lifecycle(
    settings: SupabaseConfig,
) -> list[dict[str, Any]]:

    return get_rows(
        settings,
        LIFECYCLE_TABLE,
        {
            "select": "*",
            "limit": "10000",
        },
    )


def load_direction_states(
    settings: SupabaseConfig,
) -> dict[
    str,
    dict[str, Any],
]:

    rows = get_rows(
        settings,
        DIRECTION_TABLE,
        {
            "select": "*",
            "limit": "10000",
        },
    )

    return {
        str(
            row["episode_id"]
        ):
            row
        for row in rows
        if row.get(
            "episode_id"
        )
    }


def load_timing_rows(
    settings: SupabaseConfig,
) -> list[dict[str, Any]]:

    return get_rows(
        settings,
        TIMING_TABLE,
        {
            "select": "*",
            "limit": "10000",
        },
    )


def mover_class(
    absolute_move: float,
) -> str:

    if absolute_move >= 20:
        return "EXTREME_20_PLUS"

    if absolute_move >= 10:
        return "MAJOR_10_TO_20"

    return "MOVER_5_TO_10"


def threshold_first_seen(
    history: list[
        dict[str, Any]
    ],
    threshold: float,
) -> datetime | None:

    for row in history:
        move = f(
            row.get(
                "change_24h_pct"
            )
        )

        when = dt(
            row.get(
                "hour_bucket_utc"
            )
        )

        if (
            move is not None
            and when is not None
            and abs(move)
            >= threshold
        ):
            return when

    return None


def first_true_time(
    history: list[
        dict[str, Any]
    ],
    field: str,
) -> datetime | None:

    for row in history:
        if bool(
            row.get(field)
        ):
            when = dt(
                row.get(
                    "hour_bucket_utc"
                )
            )

            if when is not None:
                return when

    return None


def first_seen_time(
    history: list[
        dict[str, Any]
    ],
) -> datetime | None:

    if not history:
        return None

    return dt(
        history[0].get(
            "hour_bucket_utc"
        )
    )


def ledger_coverage_hours(
    history: list[
        dict[str, Any]
    ],
) -> float:

    times = [
        dt(
            row.get(
                "hour_bucket_utc"
            )
        )
        for row in history
    ]

    times = [
        value
        for value in times
        if value is not None
    ]

    if len(times) < 2:
        return 0.0

    return (
        max(times)
        - min(times)
    ).total_seconds() / 3600.0


def measurement_quality(
    history: list[
        dict[str, Any]
    ],
) -> str:

    coverage = ledger_coverage_hours(
        history
    )

    observations = len(
        history
    )

    if (
        coverage >= 23.0
        and observations >= 20
    ):
        return "FORWARD_24H_COMPLETE"

    if (
        coverage >= 6.0
        and observations >= 6
    ):
        return "PARTIAL_6H_PLUS"

    return "PARTIAL_HISTORY"


def choose_episode(
    symbol: str,
    episodes: list[
        dict[str, Any]
    ],
    reference_time:
        datetime | None,
) -> dict[str, Any] | None:

    candidates = []

    for episode in episodes:

        if str(
            episode.get(
                "symbol"
            )
            or ""
        ).upper() != symbol:
            continue

        detected = dt(
            episode.get(
                "first_detected_at_utc"
            )
        )

        if detected is None:
            continue

        if (
            reference_time
            is not None
            and detected
            > reference_time
        ):
            continue

        candidates.append(
            (
                detected,
                episode,
            )
        )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item:
            item[0]
    )

    return candidates[-1][1]


def timing_by_episode(
    rows: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    dict[
        str,
        dict[str, Any],
    ],
]:

    output: dict[
        str,
        dict[
            str,
            dict[str, Any],
        ],
    ] = defaultdict(
        dict
    )

    for row in rows:

        episode_id = str(
            row.get(
                "episode_id"
            )
            or ""
        )

        phase = str(
            row.get(
                "phase"
            )
            or ""
        ).upper()

        if (
            episode_id
            and phase
        ):
            output[
                episode_id
            ][
                phase
            ] = row

    return dict(
        output
    )


def determine_failure(
    *,
    quality: str,
    eligible_before:
        bool | None,
    selected_before:
        bool | None,
    episode:
        dict[str, Any] | None,
    direction_state:
        dict[str, Any] | None,
    frozen_confirmed_direction:
        str | None,
    mover_direction: str,
    rr_confirmed:
        float | None,
) -> tuple[str, str]:

    if quality != (
        "FORWARD_24H_COMPLETE"
    ):
        return (
            "DATA",
            "INSUFFICIENT_LEDGER_HISTORY",
        )

    if eligible_before is False:
        return (
            "PREFILTER",
            "NOT_ELIGIBLE_BEFORE_EXPANSION",
        )

    if selected_before is False:
        return (
            "SELECTION",
            "ELIGIBLE_NOT_DEEP_SCANNED",
        )

    if episode is None:
        return (
            "DISCOVERY",
            "SELECTED_WITHOUT_LIFECYCLE_EPISODE",
        )

    if direction_state is None:
        return (
            "DIRECTION",
            "NO_DIRECTION_STATE",
        )

    confirmed_at = dt(
        direction_state.get(
            "first_confirmed_at_utc"
        )
    )

    if confirmed_at is None:
        return (
            "DIRECTION",
            "NO_DIRECTION_CONFIRMATION",
        )

    confirmed_direction = str(
        frozen_confirmed_direction
        or ""
    ).upper()

    if confirmed_direction not in {
        "LONG",
        "SHORT",
    }:
        return (
            "DIRECTION",
            "CONFIRMED_DIRECTION_UNAVAILABLE",
        )

    expected = (
        "LONG"
        if mover_direction == "UP"
        else "SHORT"
    )

    if confirmed_direction != expected:
        return (
            "DIRECTION",
            "WRONG_DIRECTION",
        )

    if (
        rr_confirmed is None
        or rr_confirmed < 5.0
    ):
        return (
            "EXECUTION",
            "RR_BELOW_5_AT_CONFIRMATION",
        )

    return (
        "NONE",
        "SHADOW_FEASIBLE_NOT_EXECUTED",
    )


def build_audit_row(
    *,
    symbol: str,
    history: list[
        dict[str, Any]
    ],
    latest: dict[str, Any],
    threshold: float,
    episodes: list[
        dict[str, Any]
    ],
    direction_states: dict[
        str,
        dict[str, Any],
    ],
    timing_index: dict[
        str,
        dict[
            str,
            dict[str, Any],
        ],
    ],
    audited_at: datetime,
) -> dict[str, Any] | None:

    current_move = f(
        latest.get(
            "change_24h_pct"
        )
    )

    current_price = f(
        latest.get(
            "last_price"
        )
    )

    if (
        current_move is None
        or current_price in (
            None,
            0,
        )
        or abs(
            current_move
        ) < threshold
    ):
        return None

    direction = (
        "UP"
        if current_move > 0
        else "DOWN"
    )

    bucket = audit_hour(
        audited_at
    )

    threshold_at = (
        threshold_first_seen(
            history,
            threshold,
        )
    )

    first_seen = (
        first_seen_time(
            history
        )
    )

    first_eligible = (
        first_true_time(
            history,
            "prefilter_eligible",
        )
    )

    first_selected = (
        first_true_time(
            history,
            "deep_scan_selected",
        )
    )

    quality = (
        measurement_quality(
            history
        )
    )

    eligible_before = None
    selected_before = None

    if (
        threshold_at is not None
        and first_seen
        is not None
        and first_seen
        < threshold_at
    ):
        eligible_before = bool(
            first_eligible
            is not None
            and first_eligible
            < threshold_at
        )

        selected_before = bool(
            first_selected
            is not None
            and first_selected
            < threshold_at
        )

    episode = choose_episode(
        symbol,
        episodes,
        threshold_at
        or audited_at,
    )

    episode_id = (
        str(
            episode.get(
                "episode_id"
            )
        )
        if episode
        and episode.get(
            "episode_id"
        )
        else None
    )

    direction_state = (
        direction_states.get(
            episode_id
        )
        if episode_id
        else None
    )

    timing = (
        timing_index.get(
            episode_id,
            {},
        )
        if episode_id
        else {}
    )

    detection = timing.get(
        "DETECTION"
    )

    emerging = timing.get(
        "EMERGING"
    )

    confirmed = timing.get(
        "CONFIRMED"
    )

    rr_detection = (
        f(
            detection.get(
                "rr_to_structure"
            )
        )
        if detection
        else None
    )

    rr_emerging = (
        f(
            emerging.get(
                "rr_to_structure"
            )
        )
        if emerging
        else None
    )

    rr_confirmation = (
        f(
            confirmed.get(
                "rr_to_structure"
            )
        )
        if confirmed
        else None
    )

    frozen_confirmed_direction = (
        str(
            confirmed.get(
                "direction"
            )
            or ""
        ).upper()
        if confirmed
        else None
    )

    if frozen_confirmed_direction not in {
        "LONG",
        "SHORT",
    }:
        frozen_confirmed_direction = None

    failure_stage, failure_reason = (
        determine_failure(
            quality=quality,
            eligible_before=
                eligible_before,
            selected_before=
                selected_before,
            episode=episode,
            direction_state=
                direction_state,
            frozen_confirmed_direction=
                frozen_confirmed_direction,
            mover_direction=
                direction,
            rr_confirmed=
                rr_confirmation,
        )
    )

    selection_run_id = None

    if first_selected is not None:
        for item in history:
            when = dt(
                item.get(
                    "hour_bucket_utc"
                )
            )

            if (
                when == first_selected
                and item.get(
                    "deep_scan_selected"
                )
            ):
                selection_run_id = (
                    item.get(
                        "selection_run_id"
                    )
                )
                break

    confirmed_direction = (
        frozen_confirmed_direction
    )

    confirmed_at = None
    direction_state_name = None

    if direction_state:
        confirmed_at = dt(
            direction_state.get(
                "first_confirmed_at_utc"
            )
        )

        direction_state_name = (
            direction_state.get(
                "direction_state"
            )
        )

    latest_time = dt(
        latest.get(
            "hour_bucket_utc"
        )
    )

    window_start_price = None

    if history:
        window_start_price = f(
            history[0].get(
                "last_price"
            )
        )

    return {
        "audit_id":
            audit_id(
                symbol,
                bucket,
                threshold,
            ),

        "symbol":
            symbol,

        "audited_at_utc":
            audited_at.isoformat(),

        "audit_hour_utc":
            bucket.isoformat(),

        "mover_direction":
            direction,

        "current_price":
            current_price,

        "current_24h_move_pct":
            current_move,

        "mover_threshold_pct":
            threshold,

        "mover_class":
            mover_class(
                abs(
                    current_move
                )
            ),

        "window_start_utc":
            (
                first_seen.isoformat()
                if first_seen
                else None
            ),

        "window_start_price":
            window_start_price,

        "ledger_hours_covered":
            ledger_coverage_hours(
                history
            ),

        "ledger_observation_count":
            len(
                history
            ),

        "measurement_quality":
            quality,

        "first_seen_at_utc":
            (
                first_seen.isoformat()
                if first_seen
                else None
            ),

        "first_prefilter_eligible_at_utc":
            (
                first_eligible.isoformat()
                if first_eligible
                else None
            ),

        "first_deep_scan_selected_at_utc":
            (
                first_selected.isoformat()
                if first_selected
                else None
            ),

        "eligible_before_expansion":
            eligible_before,

        "selected_before_expansion":
            selected_before,

        "hours_from_first_eligible_to_audit":
            (
                (
                    audited_at
                    - first_eligible
                ).total_seconds()
                / 3600.0
                if first_eligible
                else None
            ),

        "hours_from_first_selected_to_audit":
            (
                (
                    audited_at
                    - first_selected
                ).total_seconds()
                / 3600.0
                if first_selected
                else None
            ),

        "selection_run_id":
            selection_run_id,

        "lifecycle_episode_id":
            episode_id,

        "direction_state":
            direction_state_name,

        "confirmed_direction":
            confirmed_direction,

        "direction_confirmed_at_utc":
            (
                confirmed_at.isoformat()
                if confirmed_at
                else None
            ),

        "rr_at_detection":
            rr_detection,

        "rr_at_emerging":
            rr_emerging,

        "rr_at_confirmation":
            rr_confirmation,

        "primary_failure_stage":
            failure_stage,

        "primary_failure_reason":
            failure_reason,

        "evidence": {
            "model_version":
                MODEL_VERSION,

            "first_threshold_observed_at_utc":
                (
                    threshold_at.isoformat()
                    if threshold_at
                    else None
                ),

            "latest_ledger_at_utc":
                (
                    latest_time.isoformat()
                    if latest_time
                    else None
                ),

            "threshold_crossing_is_ledger_observation":
                True,

            "not_exact_intrahour_crossing_time":
                True,

            "retrospective_audit":
                True,

            "trade_execution":
                "SHADOW_ONLY",

            "history_note":
                (
                    "Failure attribution is not "
                    "considered production-grade "
                    "until FORWARD_24H_COMPLETE."
                ),
        },

        "trade_permission":
            False,

        "updated_at":
            audited_at.isoformat(),
    }


def upsert_rows(
    settings: SupabaseConfig,
    rows: list[
        dict[str, Any]
    ],
) -> int:

    if not rows:
        return 0

    response = requests.post(
        (
            f"{settings.url}"
            f"/rest/v1/{AUDIT_TABLE}"
        ),
        params={
            "on_conflict":
                "audit_id",
        },
        headers=headers(
            settings,
            merge=True,
        ),
        data=json.dumps(
            rows,
            separators=(
                ",",
                ":",
            ),
        ),
        timeout=settings.timeout_seconds,
    )

    if response.status_code not in {
        200,
        201,
        204,
    }:
        raise RuntimeError(
            "V7.9 missed-mover audit save failed: "
            f"HTTP {response.status_code}: "
            f"{response.text[:800]}"
        )

    return len(
        rows
    )


def main() -> int:

    load_env_file(
        ROOT / ".env"
    )

    config = load_config(
        ROOT / "config.json"
    )

    settings = (
        SupabaseConfig
        .from_environment(
            config
        )
    )

    if settings is None:
        raise SystemExit(
            "Supabase is not configured"
        )

    audited_at = utc_now()

    universe_rows = (
        load_universe_history(
            settings,
            audited_at,
        )
    )

    lifecycle_rows = (
        load_lifecycle(
            settings
        )
    )

    direction_states = (
        load_direction_states(
            settings
        )
    )

    timing_rows = (
        load_timing_rows(
            settings
        )
    )

    timing_index = (
        timing_by_episode(
            timing_rows
        )
    )

    history_by_symbol: dict[
        str,
        list[
            dict[str, Any]
        ],
    ] = defaultdict(
        list
    )

    for row in universe_rows:

        symbol = str(
            row.get(
                "symbol"
            )
            or ""
        ).upper()

        if symbol:
            history_by_symbol[
                symbol
            ].append(
                row
            )

    audit_rows = []

    for symbol, history in (
        history_by_symbol.items()
    ):

        history.sort(
            key=lambda row:
                str(
                    row.get(
                        "hour_bucket_utc"
                    )
                    or ""
                )
        )

        latest = history[-1]

        move = f(
            latest.get(
                "change_24h_pct"
            )
        )

        if move is None:
            continue

        for threshold in THRESHOLDS:

            if abs(move) < threshold:
                continue

            row = build_audit_row(
                symbol=symbol,
                history=history,
                latest=latest,
                threshold=threshold,
                episodes=
                    lifecycle_rows,
                direction_states=
                    direction_states,
                timing_index=
                    timing_index,
                audited_at=
                    audited_at,
            )

            if row is not None:
                audit_rows.append(
                    row
                )

    saved = upsert_rows(
        settings,
        audit_rows,
    )

    print()
    print("=" * 126)
    print(
        "ALPHA HUNTER V7.9 "
        "MISSED-MOVER RECALL AUDITOR — SHADOW"
    )
    print("=" * 126)

    print(
        "Universe ledger rows loaded:",
        len(
            universe_rows
        ),
    )

    print(
        "Symbols with ledger history:",
        len(
            history_by_symbol
        ),
    )

    print(
        "Audit rows:",
        len(
            audit_rows
        ),
    )

    print(
        "Supabase rows upserted:",
        saved,
    )

    print()
    print(
        f"{'SYMBOL':<16}"
        f"{'MOVE':>9}"
        f"{'THR':>7}"
        f"{'QUAL':>18}"
        f"{'STAGE':>14}  "
        f"REASON"
    )

    print("-" * 126)

    ordered = sorted(
        audit_rows,
        key=lambda row:
            (
                -abs(
                    float(
                        row[
                            "current_24h_move_pct"
                        ]
                    )
                ),
                float(
                    row[
                        "mover_threshold_pct"
                    ]
                ),
            ),
    )

    for row in ordered[:40]:

        move = float(
            row[
                "current_24h_move_pct"
            ]
        )

        print(
            f"{row['symbol']:<16}"
            f"{move:>+8.2f}%"
            f"{row['mover_threshold_pct']:>6.0f}%"
            f"{row['measurement_quality']:>18}"
            f"{row['primary_failure_stage']:>14}  "
            f"{row['primary_failure_reason']}"
        )

    complete = sum(
        1
        for row in audit_rows
        if row[
            "measurement_quality"
        ]
        == "FORWARD_24H_COMPLETE"
    )

    partial = (
        len(
            audit_rows
        )
        - complete
    )

    print()
    print(
        "Forward 24H complete audits:",
        complete,
    )

    print(
        "Partial-history audits:",
        partial,
    )

    print()
    print(
        "IMPORTANT: PARTIAL_HISTORY rows "
        "are evidence collection only."
    )

    print(
        "Do not tune Alpha Hunter from "
        "partial-history failure labels."
    )

    print(
        "No trade permission was generated."
    )

    print()
    print(
        "V7.9 MISSED-MOVER RECALL AUDITOR: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
