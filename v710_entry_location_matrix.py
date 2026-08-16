from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from alpha_hunter.bitget import BitgetClient
from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig

from v77_execution_feasibility_shadow import (
    f,
    stop_distance_pct,
)

from v710_early_execution_rr_shadow import (
    group_v78_rows,
    load_v78_rows,
    phase_evidence_from_v78_row,
)

from v710_execution_replay_diagnostic import (
    future_path,
    historical_range,
    parse_dt,
    replay,
    target_for_5r,
    target_levels,
)


ROOT = Path(__file__).resolve().parent

ENTRY_POLICIES = {
    "MARKET": 0.00,
    "PB25": 0.25,
    "PB50": 0.50,
    "PB75": 0.75,
}


def limit_entry(
    direction: str,
    market_entry: float,
    stop: float,
    fraction: float,
) -> float:
    distance = abs(
        market_entry - stop
    )

    if direction == "LONG":
        return (
            market_entry
            - distance * fraction
        )

    if direction == "SHORT":
        return (
            market_entry
            + distance * fraction
        )

    raise ValueError(
        f"Invalid direction: {direction}"
    )


def build_policy_setup(
    direction: str,
    market_entry: float,
    stop: float,
    fraction: float,
    levels: list[
        tuple[str, float]
    ],
) -> dict[str, Any] | None:
    entry = limit_entry(
        direction,
        market_entry,
        stop,
        fraction,
    )

    risk_pct = stop_distance_pct(
        entry,
        stop,
    )

    if risk_pct in (
        None,
        0,
    ):
        return None

    (
        target_source,
        target,
        setup_rr,
    ) = target_for_5r(
        direction,
        entry,
        risk_pct,
        levels,
    )

    if (
        target is None
        or setup_rr is None
    ):
        return None

    return {
        "entry":
            entry,

        "stop":
            stop,

        "risk_pct":
            risk_pct,

        "target":
            target,

        "target_source":
            target_source,

        "rr":
            setup_rr,

        "fraction":
            fraction,
    }


def replay_limit_entry(
    direction: str,
    setup: dict[str, Any],
    future: list[
        dict[str, float | int]
    ],
) -> str:
    entry = float(
        setup["entry"]
    )

    stop = float(
        setup["stop"]
    )

    target = float(
        setup["target"]
    )

    if setup[
        "fraction"
    ] == 0.0:
        outcome, _ = replay(
            direction,
            stop,
            target,
            future,
        )

        return outcome

    for index, candle in enumerate(
        future
    ):
        high = float(
            candle["high"]
        )

        low = float(
            candle["low"]
        )

        if direction == "LONG":
            target_hit = (
                high >= target
            )

            entry_hit = (
                low <= entry
            )

            stop_hit = (
                low <= stop
            )

        else:
            target_hit = (
                low <= target
            )

            entry_hit = (
                high >= entry
            )

            stop_hit = (
                high >= stop
            )

        if (
            target_hit
            and entry_hit
        ):
            return (
                "AMBIGUOUS_TARGET_AND_FILL"
            )

        if target_hit:
            return (
                "TARGET_BEFORE_FILL"
            )

        if entry_hit:
            if stop_hit:
                return (
                    "FILL_AND_STOP_SAME_BAR"
                )

            remaining = future[
                index + 1:
            ]

            outcome, _ = replay(
                direction,
                stop,
                target,
                remaining,
            )

            if outcome == "UNRESOLVED":
                return (
                    "FILLED_UNRESOLVED"
                )

            return outcome

    return "NOT_FILLED"


def n(
    value: Any,
) -> str:
    value = f(value)

    if value is None:
        return "—"

    return f"{value:.2f}"


def short(
    outcome: str,
) -> str:
    mapping = {
        "TARGET_FIRST":
            "TARGET",

        "STOP_FIRST":
            "STOP",

        "FILLED_UNRESOLVED":
            "OPEN",

        "UNRESOLVED":
            "OPEN",

        "NOT_FILLED":
            "NOFILL",

        "TARGET_BEFORE_FILL":
            "MISSED",

        "FILL_AND_STOP_SAME_BAR":
            "FILLSTOP",

        "AMBIGUOUS_TARGET_AND_FILL":
            "AMBIG",
    }

    return mapping.get(
        outcome,
        outcome,
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

    episodes = []

    failures = 0

    for (
        episode_id,
        phase_rows,
    ) in grouped.items():
        by_phase = {
            str(
                row.get("phase")
                or ""
            ).upper():
                row
            for row
            in phase_rows
        }

        row = by_phase.get(
            "EMERGING"
        )

        if row is None:
            continue

        emerging = (
            phase_evidence_from_v78_row(
                row,
                "EMERGING",
            )
        )

        if (
            not emerging
            .direction_available
            or not emerging
            .measurement_complete
            or emerging.phase_price
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
            emerging.observed_direction
            or ""
        ).upper()

        phase_at = parse_dt(
            row.get(
                "phase_at_utc"
            )
        )

        market_entry = (
            emerging.phase_price
        )

        stop = f(
            row.get(
                "stop_price"
            )
        )

        if (
            not symbol
            or phase_at is None
            or stop is None
            or direction
            not in {
                "LONG",
                "SHORT",
            }
        ):
            continue

        try:
            pre1h = (
                historical_range(
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
            )

            levels = target_levels(
                direction,
                market_entry,
                pre1h,
            )

            future, complete = (
                future_path(
                    client,
                    symbol,
                    product_type,
                    phase_at,
                )
            )

            policies = {}

            for (
                name,
                fraction,
            ) in ENTRY_POLICIES.items():
                setup = (
                    build_policy_setup(
                        direction,
                        market_entry,
                        stop,
                        fraction,
                        levels,
                    )
                )

                if setup is None:
                    policies[name] = {
                        "outcome":
                            "NO_SETUP",

                        "rr":
                            None,

                        "entry":
                            None,

                        "risk_pct":
                            None,
                    }

                    continue

                outcome = (
                    replay_limit_entry(
                        direction,
                        setup,
                        future,
                    )
                )

                policies[name] = {
                    "outcome":
                        outcome,

                    "rr":
                        setup[
                            "rr"
                        ],

                    "entry":
                        setup[
                            "entry"
                        ],

                    "risk_pct":
                        setup[
                            "risk_pct"
                        ],
                }

            episodes.append(
                {
                    "episode_id":
                        episode_id,

                    "symbol":
                        symbol,

                    "direction":
                        direction,

                    "direction_ok":
                        (
                            emerging
                            .direction_consistent_with_confirmed
                        ),

                    "complete":
                        complete,

                    "policies":
                        policies,
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
    print("=" * 125)
    print(
        "ALPHA HUNTER V7.10 "
        "ENTRY-LOCATION MATRIX — SHADOW"
    )
    print("=" * 125)

    print(
        f"{'SYMBOL':<14}"
        f"{'DIR':<7}"
        f"{'OK?':<6}"
        f"{'MARKET':<18}"
        f"{'PB25':<18}"
        f"{'PB50':<18}"
        f"{'PB75':<18}"
    )

    print("-" * 125)

    for episode in episodes:
        ok = (
            "Y"
            if episode[
                "direction_ok"
            ] is True
            else (
                "N"
                if episode[
                    "direction_ok"
                ] is False
                else "—"
            )
        )

        cells = []

        for name in (
            "MARKET",
            "PB25",
            "PB50",
            "PB75",
        ):
            result = (
                episode[
                    "policies"
                ][name]
            )

            cell = short(
                result[
                    "outcome"
                ]
            )

            if result[
                "rr"
            ] is not None:
                cell += (
                    "/"
                    + n(
                        result[
                            "rr"
                        ]
                    )
                )

            cells.append(
                cell
            )

        print(
            f"{episode['symbol']:<14}"
            f"{episode['direction']:<7}"
            f"{ok:<6}"
            f"{cells[0]:<18}"
            f"{cells[1]:<18}"
            f"{cells[2]:<18}"
            f"{cells[3]:<18}"
        )

    print()
    print("=" * 125)
    print(
        "CORRECT EARLY DIRECTION — "
        "ENTRY POLICY SUMMARY"
    )
    print("=" * 125)

    for policy in (
        "MARKET",
        "PB25",
        "PB50",
        "PB75",
    ):
        counts = defaultdict(
            int
        )

        resolved_r = 0.0
        resolved = 0

        for episode in episodes:
            if episode[
                "direction_ok"
            ] is not True:
                continue

            result = (
                episode[
                    "policies"
                ][policy]
            )

            outcome = result[
                "outcome"
            ]

            counts[
                outcome
            ] += 1

            if outcome == "STOP_FIRST":
                resolved += 1
                resolved_r -= 1.0

            elif outcome == "TARGET_FIRST":
                resolved += 1
                resolved_r += float(
                    result["rr"]
                )

        print()
        print(policy)

        for outcome in (
            "TARGET_FIRST",
            "STOP_FIRST",
            "FILLED_UNRESOLVED",
            "NOT_FILLED",
            "TARGET_BEFORE_FILL",
            "FILL_AND_STOP_SAME_BAR",
            "AMBIGUOUS_TARGET_AND_FILL",
            "NO_SETUP",
        ):
            print(
                f"  {outcome}:",
                counts[outcome],
            )

        print(
            "  RESOLVED:",
            resolved,
        )

        print(
            "  PROVISIONAL_RESOLVED_R:",
            f"{resolved_r:+.2f}",
        )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "Pullback orders are defined "
        "at EMERGING, before future data."
    )

    print(
        "Stop remains the frozen V7.8 "
        "structural invalidation."
    )

    print(
        "Targets must already exist "
        "before EMERGING."
    )

    print(
        "TARGET_BEFORE_FILL means the "
        "move escaped without entry."
    )

    print(
        "No entry policy is selected "
        "as a winner from this cohort."
    )

    print(
        "READ ONLY — NO SUPABASE WRITES "
        "— NO TRADE PERMISSION."
    )

    print()
    print(
        "Evaluated:",
        len(episodes),
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
