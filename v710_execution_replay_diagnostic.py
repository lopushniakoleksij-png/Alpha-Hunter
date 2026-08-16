from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from alpha_hunter.bitget import BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig

from v77_execution_feasibility_shadow import (
    STOP_BUFFER_ATR_FRACTION,
    atr,
    f,
    rr,
    stop_distance_pct,
    structural_reward_pct,
    swing_levels,
)

from v710_early_execution_rr_shadow import (
    group_v78_rows,
    load_v78_rows,
    phase_evidence_from_v78_row,
)


ROOT = Path(__file__).resolve().parent

STOP_WINDOWS = (
    4,
    6,
    8,
    12,
)

TARGET_WINDOWS = (
    12,
    24,
    48,
)

MIN_RR = 5.0
HORIZON_HOURS = 24


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def parse_dt(
    value: Any,
) -> datetime | None:
    if value in (
        None,
        "",
    ):
        return None

    try:
        result = datetime.fromisoformat(
            str(value)
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


def floor_time(
    value: datetime,
    minutes: int,
) -> datetime:
    value = value.astimezone(
        timezone.utc
    )

    minute = (
        value.minute
        // minutes
        * minutes
    )

    return value.replace(
        minute=minute,
        second=0,
        microsecond=0,
    )


def ceil_time(
    value: datetime,
    minutes: int,
) -> datetime:
    floored = floor_time(
        value,
        minutes,
    )

    if value == floored:
        return floored

    return (
        floored
        + timedelta(
            minutes=minutes
        )
    )


def milliseconds(
    value: datetime,
) -> int:
    return int(
        value.timestamp()
        * 1000
    )


def history_request(
    client: BitgetClient,
    symbol: str,
    product_type: str,
    granularity: str,
    start: datetime,
    end: datetime,
    limit: int = 200,
) -> list[Any]:
    if end <= start:
        return []

    time.sleep(
        0.055
    )

    return (
        client._get(
            (
                "/api/v2/mix/market/"
                "history-candles"
            ),
            {
                "symbol":
                    symbol,

                "productType":
                    product_type,

                "granularity":
                    granularity,

                "startTime":
                    str(
                        milliseconds(
                            start
                        )
                    ),

                "endTime":
                    str(
                        milliseconds(
                            end
                        )
                    ),

                "limit":
                    str(limit),
            },
        )
        or []
    )


def parse_candles(
    rows: list[Any],
) -> list[dict[str, float | int]]:
    parsed = {}

    for row in rows:
        if (
            not isinstance(
                row,
                list,
            )
            or len(row) < 5
        ):
            continue

        try:
            timestamp = int(
                row[0]
            )

            parsed[
                timestamp
            ] = {
                "timestamp":
                    timestamp,

                "open":
                    float(
                        row[1]
                    ),

                "high":
                    float(
                        row[2]
                    ),

                "low":
                    float(
                        row[3]
                    ),

                "close":
                    float(
                        row[4]
                    ),
            }

        except (
            TypeError,
            ValueError,
            IndexError,
        ):
            continue

    return [
        parsed[key]
        for key in sorted(
            parsed
        )
    ]


def historical_range(
    client: BitgetClient,
    symbol: str,
    product_type: str,
    granularity: str,
    start: datetime,
    end: datetime,
    interval_minutes: int,
) -> list[
    dict[str, float | int]
]:
    rows = []

    cursor = floor_time(
        start,
        interval_minutes,
    )

    end = floor_time(
        end,
        interval_minutes,
    )

    max_span = timedelta(
        minutes=(
            interval_minutes
            * 190
        )
    )

    while cursor < end:
        chunk_end = min(
            cursor
            + max_span,
            end,
        )

        raw = history_request(
            client,
            symbol,
            product_type,
            granularity,
            cursor,
            chunk_end,
            200,
        )

        rows.extend(
            raw
        )

        cursor = chunk_end

    parsed = parse_candles(
        rows
    )

    start_ms = milliseconds(
        start
    )

    end_ms = milliseconds(
        end
    )

    return [
        row
        for row in parsed
        if (
            int(
                row[
                    "timestamp"
                ]
            )
            >= start_ms
            and
            int(
                row[
                    "timestamp"
                ]
            )
            < end_ms
        )
    ]


def candidate_stop(
    direction: str,
    entry: float,
    candles: list[
        dict[str, float | int]
    ],
    window: int,
    atr15: float | None,
) -> float | None:
    if len(candles) < window:
        return None

    low, high = swing_levels(
        candles,
        window,
    )

    buffer = (
        (atr15 or 0.0)
        * STOP_BUFFER_ATR_FRACTION
    )

    if (
        direction == "LONG"
        and low is not None
        and low < entry
    ):
        return (
            low
            - buffer
        )

    if (
        direction == "SHORT"
        and high is not None
        and high > entry
    ):
        return (
            high
            + buffer
        )

    return None


def target_levels(
    direction: str,
    entry: float,
    candles: list[
        dict[str, float | int]
    ],
) -> list[
    tuple[str, float]
]:
    levels = {}

    for window in TARGET_WINDOWS:
        if len(candles) < window:
            continue

        low, high = swing_levels(
            candles,
            window,
        )

        level = None

        if (
            direction == "LONG"
            and high is not None
            and high > entry
        ):
            level = high

        elif (
            direction == "SHORT"
            and low is not None
            and low < entry
        ):
            level = low

        if level is not None:
            levels[
                float(level)
            ] = (
                f"1H_{window}"
            )

    result = [
        (
            source,
            level,
        )
        for level, source
        in levels.items()
    ]

    if direction == "LONG":
        result.sort(
            key=lambda item:
                item[1]
        )
    else:
        result.sort(
            key=lambda item:
                -item[1]
        )

    return result


def target_for_5r(
    direction: str,
    entry: float,
    stop_pct: float,
    levels: list[
        tuple[str, float]
    ],
) -> tuple[
    str | None,
    float | None,
    float | None,
]:
    for source, target in levels:
        reward = (
            structural_reward_pct(
                direction,
                entry,
                target,
            )
        )

        candidate_rr = rr(
            reward,
            stop_pct,
        )

        if (
            candidate_rr is not None
            and candidate_rr
            >= MIN_RR
        ):
            return (
                source,
                target,
                candidate_rr,
            )

    return (
        None,
        None,
        None,
    )


def build_setup_candidates(
    direction: str,
    entry: float,
    current_stop: float | None,
    pre15: list[
        dict[str, float | int]
    ],
    pre1h: list[
        dict[str, float | int]
    ],
) -> list[dict[str, Any]]:
    atr15 = atr(
        pre15
    )

    stops = []

    if current_stop is not None:
        stops.append(
            (
                "CURRENT_V78",
                current_stop,
            )
        )

    for window in STOP_WINDOWS:
        stop = candidate_stop(
            direction,
            entry,
            pre15,
            window,
            atr15,
        )

        if stop is not None:
            stops.append(
                (
                    f"15M_{window}",
                    stop,
                )
            )

    levels = target_levels(
        direction,
        entry,
        pre1h,
    )

    candidates = []

    seen = set()

    for source, stop in stops:
        stop_pct = (
            stop_distance_pct(
                entry,
                stop,
            )
        )

        if stop_pct in (
            None,
            0,
        ):
            continue

        key = round(
            float(stop),
            12,
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        (
            target_source,
            target,
            candidate_rr,
        ) = target_for_5r(
            direction,
            entry,
            stop_pct,
            levels,
        )

        if (
            target is None
            or candidate_rr is None
        ):
            continue

        candidates.append(
            {
                "stop_source":
                    source,

                "stop":
                    stop,

                "stop_pct":
                    stop_pct,

                "target_source":
                    target_source,

                "target":
                    target,

                "rr":
                    candidate_rr,
            }
        )

    # Deterministic rule:
    # use the widest structural stop
    # that still has a PRE-EXISTING >=5R target.
    candidates.sort(
        key=lambda row: (
            -float(
                row["stop_pct"]
            ),
            str(
                row["stop_source"]
            ),
        )
    )

    return candidates


def replay(
    direction: str,
    stop: float,
    target: float,
    future: list[
        dict[str, float | int]
    ],
) -> tuple[
    str,
    int | None,
]:
    for candle in future:
        high = float(
            candle["high"]
        )

        low = float(
            candle["low"]
        )

        if direction == "LONG":
            stop_hit = (
                low <= stop
            )

            target_hit = (
                high >= target
            )

        else:
            stop_hit = (
                high >= stop
            )

            target_hit = (
                low <= target
            )

        if (
            stop_hit
            and target_hit
        ):
            return (
                "AMBIGUOUS_SAME_BAR",
                int(
                    candle[
                        "timestamp"
                    ]
                ),
            )

        if target_hit:
            return (
                "TARGET_FIRST",
                int(
                    candle[
                        "timestamp"
                    ]
                ),
            )

        if stop_hit:
            return (
                "STOP_FIRST",
                int(
                    candle[
                        "timestamp"
                    ]
                ),
            )

    return (
        "UNRESOLVED",
        None,
    )


def future_path(
    client: BitgetClient,
    symbol: str,
    product_type: str,
    phase_at: datetime,
) -> tuple[
    list[dict[str, float | int]],
    bool,
]:
    now = utc_now()

    horizon = min(
        phase_at
        + timedelta(
            hours=HORIZON_HOURS
        ),
        now,
    )

    complete = (
        now
        >= phase_at
        + timedelta(
            hours=HORIZON_HOURS
        )
    )

    one_minute_start = ceil_time(
        phase_at,
        1,
    )

    one_minute_end = min(
        one_minute_start
        + timedelta(
            minutes=180
        ),
        horizon,
    )

    first = historical_range(
        client,
        symbol,
        product_type,
        "1m",
        one_minute_start,
        one_minute_end,
        1,
    )

    five_start = ceil_time(
        one_minute_end,
        5,
    )

    second = []

    if five_start < horizon:
        second = historical_range(
            client,
            symbol,
            product_type,
            "5m",
            five_start,
            horizon,
            5,
        )

    rows = {
        int(
            row[
                "timestamp"
            ]
        ): row
        for row
        in (
            first
            + second
        )
    }

    return (
        [
            rows[key]
            for key
            in sorted(
                rows
            )
        ],
        complete,
    )


def text_number(
    value: Any,
) -> str:
    number = f(
        value
    )

    if number is None:
        return "—"

    return f"{number:.2f}"


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

    product_type = str(
        config.get(
            "product_type",
            "usdt-futures",
        )
    )

    client = (
        BitgetClient
        .from_environment(
            timeout=int(
                config.get(
                    "request_timeout_seconds",
                    12,
                )
            ),
            max_retries=int(
                config.get(
                    "max_retries",
                    3,
                )
            ),
        )
    )

    rows = load_v78_rows(
        settings
    )

    grouped = group_v78_rows(
        rows
    )

    results = []
    failures = 0

    for (
        episode_id,
        phase_rows,
    ) in grouped.items():
        by_phase = {
            str(
                row.get(
                    "phase"
                )
                or ""
            ).upper():
                row
            for row
            in phase_rows
        }

        emerging_row = (
            by_phase.get(
                "EMERGING"
            )
        )

        if emerging_row is None:
            continue

        emerging = (
            phase_evidence_from_v78_row(
                emerging_row,
                "EMERGING",
            )
        )

        if (
            not emerging
            .direction_available
            or not emerging
            .measurement_complete
            or emerging
            .phase_price
            in (
                None,
                0,
            )
        ):
            continue

        symbol = str(
            emerging_row.get(
                "symbol"
            )
            or ""
        )

        direction = str(
            emerging
            .observed_direction
            or ""
        ).upper()

        phase_at = parse_dt(
            emerging_row.get(
                "phase_at_utc"
            )
        )

        entry = emerging.phase_price

        current_stop = f(
            emerging_row.get(
                "stop_price"
            )
        )

        if (
            not symbol
            or phase_at is None
            or direction
            not in {
                "LONG",
                "SHORT",
            }
        ):
            continue

        try:
            pre15 = historical_range(
                client,
                symbol,
                product_type,
                "15m",
                phase_at
                - timedelta(
                    hours=12
                ),
                phase_at,
                15,
            )

            pre1h = historical_range(
                client,
                symbol,
                product_type,
                "1H",
                phase_at
                - timedelta(
                    hours=60
                ),
                phase_at,
                60,
            )

            candidates = (
                build_setup_candidates(
                    direction,
                    entry,
                    current_stop,
                    pre15,
                    pre1h,
                )
            )

            direction_ok = (
                emerging
                .direction_consistent_with_confirmed
            )

            if not candidates:
                results.append(
                    {
                        "symbol":
                            symbol,

                        "dir":
                            direction,

                        "dir_ok":
                            direction_ok,

                        "stop_source":
                            None,

                        "stop_pct":
                            None,

                        "target_source":
                            None,

                        "rr":
                            None,

                        "outcome":
                            "NO_PREEXISTING_5R_SETUP",

                        "complete":
                            False,
                    }
                )

                continue

            setup = candidates[0]

            future, complete = (
                future_path(
                    client,
                    symbol,
                    product_type,
                    phase_at,
                )
            )

            outcome, _ = replay(
                direction,
                float(
                    setup[
                        "stop"
                    ]
                ),
                float(
                    setup[
                        "target"
                    ]
                ),
                future,
            )

            results.append(
                {
                    "symbol":
                        symbol,

                    "dir":
                        direction,

                    "dir_ok":
                        direction_ok,

                    "stop_source":
                        setup[
                            "stop_source"
                        ],

                    "stop_pct":
                        setup[
                            "stop_pct"
                        ],

                    "target_source":
                        setup[
                            "target_source"
                        ],

                    "rr":
                        setup[
                            "rr"
                        ],

                    "outcome":
                        outcome,

                    "complete":
                        complete,
                }
            )

        except Exception as exc:
            failures += 1

            print(
                "FAILED",
                symbol,
                str(exc)[:250],
            )

    print()
    print("=" * 140)
    print(
        "ALPHA HUNTER V7.10 "
        "EARLY 5R EXECUTION REPLAY — SHADOW"
    )
    print("=" * 140)

    print(
        f"{'SYMBOL':<14}"
        f"{'DIR':<7}"
        f"{'OK?':<6}"
        f"{'STOP':<14}"
        f"{'STOP%':>8}"
        f"{'TARGET':<10}"
        f"{'RR':>8}"
        f"{'24H?':<7}"
        f"OUTCOME"
    )

    print("-" * 140)

    for row in results:
        direction_ok = (
            "Y"
            if row[
                "dir_ok"
            ] is True
            else (
                "N"
                if row[
                    "dir_ok"
                ] is False
                else "—"
            )
        )

        print(
            f"{row['symbol']:<14}"
            f"{row['dir']:<7}"
            f"{direction_ok:<6}"
            f"{str(row['stop_source'] or '—'):<14}"
            f"{text_number(row['stop_pct']):>8}"
            f"{str(row['target_source'] or '—'):<10}"
            f"{text_number(row['rr']):>8}"
            f"{('Y' if row['complete'] else 'N'):<7}"
            f"{row['outcome']}"
        )

    counts = {}

    correct_direction_counts = {}

    for row in results:
        outcome = row[
            "outcome"
        ]

        counts[
            outcome
        ] = (
            counts.get(
                outcome,
                0,
            )
            + 1
        )

        if row[
            "dir_ok"
        ] is True:
            correct_direction_counts[
                outcome
            ] = (
                correct_direction_counts
                .get(
                    outcome,
                    0,
                )
                + 1
            )

    print()
    print("ALL EPISODES")

    for name in sorted(
        counts
    ):
        print(
            f"{name:<32}"
            f"{counts[name]}"
        )

    print()
    print(
        "CORRECT EARLY DIRECTION ONLY"
    )

    for name in sorted(
        correct_direction_counts
    ):
        print(
            f"{name:<32}"
            f"{correct_direction_counts[name]}"
        )

    print()
    print(
        "Evaluated:",
        len(results),
    )

    print(
        "Failures:",
        failures,
    )

    print()
    print(
        "SETUP SELECTION USES ONLY "
        "PRE-EMERGING STRUCTURE."
    )

    print(
        "REPLAY USES 1M FOR FIRST 3H, "
        "THEN 5M."
    )

    print(
        "SAME-BAR STOP/TARGET EVENTS "
        "ARE MARKED AMBIGUOUS."
    )

    print(
        "PARTIAL <24H EPISODES ARE "
        "NOT FINAL FAILURE LABELS."
    )

    print(
        "READ ONLY — NO SUPABASE WRITES "
        "— NO TRADE PERMISSION."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
