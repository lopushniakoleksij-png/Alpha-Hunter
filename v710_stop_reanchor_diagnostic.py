from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

from alpha_hunter.bitget import BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig

from v77_execution_feasibility_shadow import (
    atr,
    f,
    stop_distance_pct,
)

from v710_early_execution_rr_shadow import (
    load_v78_rows,
    phase_evidence_from_v78_row,
)

from v710_execution_replay_diagnostic import (
    candidate_stop,
    future_path,
    historical_range,
    parse_dt,
    replay,
    target_for_5r,
    target_levels,
)


ROOT = Path(__file__).resolve().parent

REANCHOR_WINDOWS = (
    2,
    3,
    4,
    6,
)

MAX_WAIT_MINUTES = 180

# RESEARCH THRESHOLDS ONLY.
# NOT production rules.
MAX_STOP_PCT = 2.0
MAX_STOP_ATR = 3.0


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def closed_before(
    rows: list[dict[str, float | int]],
    as_of: datetime,
    interval_minutes: int,
) -> list[dict[str, float | int]]:
    cutoff = int(
        as_of.timestamp() * 1000
    )

    duration_ms = (
        interval_minutes
        * 60
        * 1000
    )

    return [
        row
        for row in rows
        if (
            int(row["timestamp"])
            + duration_ms
            <= cutoff
        )
    ]


def stop_metrics(
    entry: float,
    stop: float | None,
    atr15: float | None,
) -> tuple[
    float | None,
    float | None,
]:
    risk_pct = stop_distance_pct(
        entry,
        stop,
    )

    if (
        stop is None
        or atr15 in (
            None,
            0,
        )
    ):
        atr_x = None
    else:
        atr_x = (
            abs(
                entry - stop
            )
            / float(atr15)
        )

    return (
        risk_pct,
        atr_x,
    )


def admissible_stop(
    risk_pct: float | None,
    atr_x: float | None,
) -> bool:
    return bool(
        risk_pct is not None
        and atr_x is not None
        and risk_pct > 0
        and risk_pct <= MAX_STOP_PCT
        and atr_x <= MAX_STOP_ATR
    )


def build_reanchor_candidates(
    direction: str,
    entry: float,
    candles_15m: list[
        dict[str, float | int]
    ],
    candles_1h: list[
        dict[str, float | int]
    ],
) -> list[dict[str, Any]]:
    atr15 = atr(
        candles_15m
    )

    if atr15 in (
        None,
        0,
    ):
        return []

    levels = target_levels(
        direction,
        entry,
        candles_1h,
    )

    candidates = []

    seen = set()

    for window in REANCHOR_WINDOWS:
        stop = candidate_stop(
            direction,
            entry,
            candles_15m,
            window,
            atr15,
        )

        if stop is None:
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
            risk_pct,
            atr_x,
        ) = stop_metrics(
            entry,
            stop,
            atr15,
        )

        if not admissible_stop(
            risk_pct,
            atr_x,
        ):
            continue

        (
            target_source,
            target,
            setup_rr,
        ) = target_for_5r(
            direction,
            entry,
            float(risk_pct),
            levels,
        )

        if (
            target is None
            or setup_rr is None
        ):
            continue

        candidates.append(
            {
                "window":
                    window,

                "entry":
                    entry,

                "stop":
                    stop,

                "stop_pct":
                    risk_pct,

                "stop_atr":
                    atr_x,

                "target_source":
                    target_source,

                "target":
                    target,

                "rr":
                    setup_rr,
            }
        )

    # Deterministic rule:
    # among stops becoming admissible at
    # the SAME checkpoint, prefer the
    # WIDEST admissible structural stop
    # that still has >=5R.
    candidates.sort(
        key=lambda row: (
            -float(
                row["stop_pct"]
            ),
            -int(
                row["window"]
            ),
        )
    )

    return candidates


def number(
    value: Any,
) -> str:
    value = f(
        value
    )

    if value is None:
        return "—"

    return f"{value:.2f}"


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

    emerging_rows = [
        row
        for row in rows
        if (
            str(
                row.get(
                    "phase"
                )
                or ""
            ).upper()
            == "EMERGING"
        )
    ]

    results = []
    failures = 0

    for row in emerging_rows:
        try:
            evidence = (
                phase_evidence_from_v78_row(
                    row,
                    "EMERGING",
                )
            )

            if (
                not evidence
                .direction_available
                or not evidence
                .measurement_complete
                or evidence.phase_price
                in (
                    None,
                    0,
                )
            ):
                continue

            symbol = str(
                row.get(
                    "symbol"
                )
                or ""
            )

            # IMPORTANT:
            # use the direction that was
            # actually observable at
            # EMERGING, not later confirmed
            # direction.
            direction = str(
                evidence
                .observed_direction
                or ""
            ).upper()

            phase_at = parse_dt(
                row.get(
                    "phase_at_utc"
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

            current_stop_pct = f(
                row.get(
                    "stop_distance_pct"
                )
            )

            current_stop_atr = f(
                row.get(
                    "stop_distance_atr"
                )
            )

            current_admissible = (
                admissible_stop(
                    current_stop_pct,
                    current_stop_atr,
                )
            )

            now = utc_now()

            wait_end = min(
                phase_at
                + timedelta(
                    minutes=
                        MAX_WAIT_MINUTES
                ),
                now,
            )

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

            pre15 = closed_before(
                pre15,
                phase_at,
                15,
            )

            post15 = []

            all1h = []

            if wait_end > phase_at:
                post15 = historical_range(
                    client,
                    symbol,
                    product_type,
                    "15m",
                    phase_at,
                    wait_end,
                    15,
                )

                all1h = historical_range(
                    client,
                    symbol,
                    product_type,
                    "1H",
                    phase_at
                    - timedelta(
                        hours=60
                    ),
                    wait_end,
                    60,
                )

            running15 = list(
                pre15
            )

            chosen = None
            chosen_at = None

            for candle in post15:
                running15.append(
                    candle
                )

                candle_open = (
                    datetime
                    .fromtimestamp(
                        int(
                            candle[
                                "timestamp"
                            ]
                        )
                        / 1000,
                        tz=timezone.utc,
                    )
                )

                checkpoint = (
                    candle_open
                    + timedelta(
                        minutes=15
                    )
                )

                if checkpoint > wait_end:
                    continue

                c15 = closed_before(
                    running15,
                    checkpoint,
                    15,
                )

                c1h = closed_before(
                    all1h,
                    checkpoint,
                    60,
                )

                entry = float(
                    candle[
                        "close"
                    ]
                )

                candidates = (
                    build_reanchor_candidates(
                        direction,
                        entry,
                        c15,
                        c1h,
                    )
                )

                if candidates:
                    chosen = (
                        candidates[0]
                    )

                    chosen_at = (
                        checkpoint
                    )

                    break

            outcome = (
                "NO_REANCHOR_3H"
            )

            complete = False

            if (
                chosen is not None
                and chosen_at
                is not None
            ):
                (
                    future,
                    complete,
                ) = future_path(
                    client,
                    symbol,
                    product_type,
                    chosen_at,
                )

                (
                    outcome,
                    _,
                ) = replay(
                    direction,
                    float(
                        chosen[
                            "stop"
                        ]
                    ),
                    float(
                        chosen[
                            "target"
                        ]
                    ),
                    future,
                )

            wait_minutes = (
                (
                    chosen_at
                    - phase_at
                ).total_seconds()
                / 60.0
                if chosen_at
                is not None
                else None
            )

            results.append(
                {
                    "symbol":
                        symbol,

                    "direction":
                        direction,

                    "direction_ok":
                        evidence
                        .direction_consistent_with_confirmed,

                    "current_pct":
                        current_stop_pct,

                    "current_atr":
                        current_stop_atr,

                    "current_ok":
                        current_admissible,

                    "wait_minutes":
                        wait_minutes,

                    "window":
                        (
                            chosen[
                                "window"
                            ]
                            if chosen
                            else None
                        ),

                    "new_pct":
                        (
                            chosen[
                                "stop_pct"
                            ]
                            if chosen
                            else None
                        ),

                    "new_atr":
                        (
                            chosen[
                                "stop_atr"
                            ]
                            if chosen
                            else None
                        ),

                    "rr":
                        (
                            chosen[
                                "rr"
                            ]
                            if chosen
                            else None
                        ),

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
                str(
                    row.get(
                        "symbol"
                    )
                    or ""
                ),
                str(exc)[:250],
            )

    print()
    print("=" * 145)

    print(
        "ALPHA HUNTER V7.10 "
        "LOCAL STOP RE-ANCHOR "
        "DIAGNOSTIC — SHADOW"
    )

    print("=" * 145)

    print(
        f"{'SYMBOL':<14}"
        f"{'DIR':<7}"
        f"{'OK?':<6}"
        f"{'OLD%':>8}"
        f"{'OLDATR':>8}"
        f"{'OLDOK':<7}"
        f"{'WAIT':>8}"
        f"{'WIN':>6}"
        f"{'NEW%':>8}"
        f"{'NEWATR':>8}"
        f"{'RR':>8}"
        f"  OUTCOME"
    )

    print("-" * 145)

    for result in results:
        direction_ok = (
            "Y"
            if result[
                "direction_ok"
            ] is True
            else (
                "N"
                if result[
                    "direction_ok"
                ] is False
                else "—"
            )
        )

        print(
            f"{result['symbol']:<14}"
            f"{result['direction']:<7}"
            f"{direction_ok:<6}"
            f"{number(result['current_pct']):>8}"
            f"{number(result['current_atr']):>8}"
            f"{('Y' if result['current_ok'] else 'N'):<7}"
            f"{number(result['wait_minutes']):>8}"
            f"{str(result['window'] or '—'):>6}"
            f"{number(result['new_pct']):>8}"
            f"{number(result['new_atr']):>8}"
            f"{number(result['rr']):>8}"
            f"  {result['outcome']}"
        )

    correct = [
        result
        for result in results
        if result[
            "direction_ok"
        ] is True
    ]

    found = [
        result
        for result in correct
        if result[
            "window"
        ] is not None
    ]

    waits = [
        float(
            result[
                "wait_minutes"
            ]
        )
        for result in found
        if result[
            "wait_minutes"
        ] is not None
    ]

    counts = Counter(
        result[
            "outcome"
        ]
        for result in correct
    )

    provisional_r = 0.0
    resolved = 0

    for result in correct:
        if (
            result[
                "outcome"
            ]
            == "STOP_FIRST"
        ):
            provisional_r -= 1.0
            resolved += 1

        elif (
            result[
                "outcome"
            ]
            == "TARGET_FIRST"
        ):
            provisional_r += float(
                result[
                    "rr"
                ]
            )

            resolved += 1

    print()
    print("=" * 145)

    print(
        "CORRECT EARLY DIRECTION "
        "— RE-ANCHOR SUMMARY"
    )

    print("=" * 145)

    print(
        "Correct direction:",
        len(correct),
    )

    print(
        "Re-anchor found:",
        len(found),
    )

    print(
        "No re-anchor <=3H:",
        counts[
            "NO_REANCHOR_3H"
        ],
    )

    print(
        "TARGET_FIRST:",
        counts[
            "TARGET_FIRST"
        ],
    )

    print(
        "STOP_FIRST:",
        counts[
            "STOP_FIRST"
        ],
    )

    print(
        "UNRESOLVED:",
        counts[
            "UNRESOLVED"
        ],
    )

    print(
        "AMBIGUOUS_SAME_BAR:",
        counts[
            "AMBIGUOUS_SAME_BAR"
        ],
    )

    print(
        "Resolved:",
        resolved,
    )

    print(
        "Provisional resolved R:",
        f"{provisional_r:+.2f}",
    )

    print(
        "Median wait minutes:",
        (
            f"{median(waits):.2f}"
            if waits
            else "—"
        ),
    )

    print()
    print(
        "RESEARCH THRESHOLDS:"
    )

    print(
        f"stop <= {MAX_STOP_PCT:.2f}% "
        f"AND <= {MAX_STOP_ATR:.2f} ATR"
    )

    print(
        "Thresholds are diagnostic "
        "only — NOT production rules."
    )

    print(
        "Direction uses live-observable "
        "EMERGING direction."
    )

    print(
        "Each re-anchor uses only candles "
        "closed by that checkpoint."
    )

    print(
        "READ ONLY — NO SUPABASE WRITES "
        "— NO TRADE PERMISSION."
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

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
