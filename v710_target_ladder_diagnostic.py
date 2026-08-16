from __future__ import annotations

from pathlib import Path
from typing import Any

from alpha_hunter.bitget import BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig

from v77_execution_feasibility_shadow import (
    dt,
    f,
    parse_closed_candles,
    rr,
    structural_reward_pct,
    swing_levels,
)

from v710_early_execution_rr_shadow import (
    group_v78_rows,
    load_v78_rows,
    phase_evidence_from_v78_row,
)


ROOT = Path(__file__).resolve().parent

WINDOWS = (
    12,
    24,
    48,
)


def target_for_window(
    direction: str,
    entry: float,
    candles: list[dict[str, float | int]],
    window: int,
) -> float | None:
    if len(candles) < window:
        return None

    low, high = swing_levels(
        candles,
        window,
    )

    if (
        direction == "LONG"
        and high is not None
        and high > entry
    ):
        return high

    if (
        direction == "SHORT"
        and low is not None
        and low < entry
    ):
        return low

    return None


def number(
    value: Any,
) -> str:
    value = f(value)

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

    grouped = group_v78_rows(
        rows
    )

    results = []
    failures = 0

    for episode_id, phase_rows in grouped.items():
        by_phase = {
            str(
                row.get("phase")
                or ""
            ).upper(): row
            for row in phase_rows
        }

        row = by_phase.get(
            "EMERGING"
        )

        if row is None:
            continue

        evidence = (
            phase_evidence_from_v78_row(
                row,
                "EMERGING",
            )
        )

        if (
            not evidence.direction_available
            or not evidence.measurement_complete
            or evidence.phase_price
            in (
                None,
                0,
            )
        ):
            continue

        symbol = str(
            row.get("symbol")
            or ""
        )

        direction = str(
            evidence.observed_direction
            or ""
        ).upper()

        entry = evidence.phase_price

        phase_at = dt(
            row.get(
                "phase_at_utc"
            )
        )

        stop_pct = f(
            row.get(
                "stop_distance_pct"
            )
        )

        local_reward = f(
            row.get(
                "structural_reward_pct"
            )
        )

        local_rr = f(
            row.get(
                "rr_to_structure"
            )
        )

        if (
            not symbol
            or phase_at is None
            or stop_pct
            in (
                None,
                0,
            )
        ):
            continue

        try:
            raw = (
                client.candles(
                    symbol,
                    product_type,
                    "1H",
                    120,
                )
                or []
            )

            candles = (
                parse_closed_candles(
                    raw,
                    phase_at,
                    60,
                )
            )

            window_rr = {}

            for window in WINDOWS:
                target = (
                    target_for_window(
                        direction,
                        entry,
                        candles,
                        window,
                    )
                )

                reward = (
                    structural_reward_pct(
                        direction,
                        entry,
                        target,
                    )
                )

                window_rr[window] = rr(
                    reward,
                    stop_pct,
                )

            rr5_scenario = rr(
                5.0,
                stop_pct,
            )

            rr10_scenario = rr(
                10.0,
                stop_pct,
            )

            best_external_rr = max(
                (
                    value
                    for value
                    in window_rr.values()
                    if value is not None
                ),
                default=None,
            )

            if (
                local_rr is not None
                and local_rr >= 5
            ):
                diagnosis = (
                    "LOCAL_STRUCTURE_ALREADY_5R"
                )

            elif (
                best_external_rr
                is not None
                and best_external_rr >= 5
            ):
                diagnosis = (
                    "FARTHER_STRUCTURE_RESTORES_5R"
                )

            elif (
                rr10_scenario
                is not None
                and rr10_scenario < 5
            ):
                diagnosis = (
                    "STOP_TOO_WIDE_EVEN_FOR_10PCT"
                )

            elif (
                rr10_scenario
                is not None
                and rr10_scenario >= 5
            ):
                diagnosis = (
                    "TARGET_OR_STRUCTURE_BOTTLENECK"
                )

            else:
                diagnosis = (
                    "INSUFFICIENT_GEOMETRY"
                )

            results.append(
                {
                    "symbol":
                        symbol,

                    "direction":
                        direction,

                    "stop":
                        stop_pct,

                    "local_reward":
                        local_reward,

                    "local_rr":
                        local_rr,

                    "rr12":
                        window_rr[12],

                    "rr24":
                        window_rr[24],

                    "rr48":
                        window_rr[48],

                    "rr5":
                        rr5_scenario,

                    "rr10":
                        rr10_scenario,

                    "diagnosis":
                        diagnosis,
                }
            )

        except Exception as exc:
            failures += 1

            print(
                "FAILED",
                symbol,
                str(exc)[:200],
            )

    results.sort(
        key=lambda row: (
            row["diagnosis"],
            row["symbol"],
        )
    )

    print()
    print("=" * 155)
    print(
        "V7.10 EXTERNAL STRUCTURE "
        "TARGET-LADDER DIAGNOSTIC"
    )
    print("=" * 155)

    print(
        f"{'SYMBOL':<14}"
        f"{'DIR':<7}"
        f"{'STOP%':>8}"
        f"{'LOCAL%':>9}"
        f"{'LOCALRR':>9}"
        f"{'1H12':>8}"
        f"{'1H24':>8}"
        f"{'1H48':>8}"
        f"{'5%RR':>8}"
        f"{'10%RR':>8}  "
        f"DIAGNOSIS"
    )

    print("-" * 155)

    for row in results:
        print(
            f"{row['symbol']:<14}"
            f"{row['direction']:<7}"
            f"{number(row['stop']):>8}"
            f"{number(row['local_reward']):>9}"
            f"{number(row['local_rr']):>9}"
            f"{number(row['rr12']):>8}"
            f"{number(row['rr24']):>8}"
            f"{number(row['rr48']):>8}"
            f"{number(row['rr5']):>8}"
            f"{number(row['rr10']):>8}  "
            f"{row['diagnosis']}"
        )

    counts = {}

    for row in results:
        name = row[
            "diagnosis"
        ]

        counts[name] = (
            counts.get(
                name,
                0,
            )
            + 1
        )

    print()
    print("DIAGNOSIS COUNTS")

    for name in sorted(counts):
        print(
            f"{name:<38}"
            f"{counts[name]}"
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
        "5%RR / 10%RR ARE GEOMETRY "
        "SCENARIOS ONLY — NOT PRICE TARGETS."
    )

    print(
        "1H12 / 1H24 / 1H48 USE ONLY "
        "STRUCTURE THAT EXISTED BEFORE EMERGING."
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
