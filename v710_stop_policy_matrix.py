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
    atr,
    f,
    stop_distance_pct,
)

from v710_early_execution_rr_shadow import (
    group_v78_rows,
    load_v78_rows,
    phase_evidence_from_v78_row,
)

from v710_execution_replay_diagnostic import (
    STOP_WINDOWS,
    candidate_stop,
    future_path,
    historical_range,
    parse_dt,
    replay,
    target_for_5r,
    target_levels,
)


ROOT = Path(__file__).resolve().parent

POLICIES = (
    "CURRENT_V78",
    "TIGHTEST_5R",
    "WIDEST_5R",
    "15M_4",
    "15M_6",
    "15M_8",
    "15M_12",
)


def build_all_candidates(
    direction: str,
    entry: float,
    current_stop: float | None,
    pre15: list[dict[str, float | int]],
    pre1h: list[dict[str, float | int]],
) -> list[dict[str, Any]]:
    atr15 = atr(pre15)

    stops: list[
        tuple[str, float]
    ] = []

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

    for source, stop in stops:
        risk = stop_distance_pct(
            entry,
            stop,
        )

        if risk in (
            None,
            0,
        ):
            continue

        (
            target_source,
            target,
            setup_rr,
        ) = target_for_5r(
            direction,
            entry,
            risk,
            levels,
        )

        if (
            target is None
            or setup_rr is None
        ):
            continue

        candidates.append(
            {
                "stop_source":
                    source,

                "stop":
                    stop,

                "stop_pct":
                    risk,

                "target_source":
                    target_source,

                "target":
                    target,

                "rr":
                    setup_rr,
            }
        )

    return candidates


def choose_policy(
    policy: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidates:
        return None

    if policy == "TIGHTEST_5R":
        return min(
            candidates,
            key=lambda row: (
                float(
                    row["stop_pct"]
                ),
                str(
                    row["stop_source"]
                ),
            ),
        )

    if policy == "WIDEST_5R":
        return max(
            candidates,
            key=lambda row: (
                float(
                    row["stop_pct"]
                ),
                str(
                    row["stop_source"]
                ),
            ),
        )

    matches = [
        row
        for row in candidates
        if row[
            "stop_source"
        ] == policy
    ]

    if not matches:
        return None

    return matches[0]


def outcome_for_policy(
    policy: str,
    candidates: list[dict[str, Any]],
    direction: str,
    future: list[dict[str, float | int]],
) -> dict[str, Any]:
    setup = choose_policy(
        policy,
        candidates,
    )

    if setup is None:
        return {
            "policy":
                policy,

            "outcome":
                "NO_SETUP",

            "rr":
                None,

            "stop_pct":
                None,

            "stop_source":
                None,

            "target_source":
                None,
        }

    outcome, _ = replay(
        direction,
        float(
            setup["stop"]
        ),
        float(
            setup["target"]
        ),
        future,
    )

    return {
        "policy":
            policy,

        "outcome":
            outcome,

        "rr":
            setup["rr"],

        "stop_pct":
            setup[
                "stop_pct"
            ],

        "stop_source":
            setup[
                "stop_source"
            ],

        "target_source":
            setup[
                "target_source"
            ],
    }


def n(
    value: Any,
) -> str:
    value = f(value)

    if value is None:
        return "—"

    return f"{value:.2f}"


def short_outcome(
    value: str,
) -> str:
    mapping = {
        "TARGET_FIRST":
            "TARGET",

        "STOP_FIRST":
            "STOP",

        "UNRESOLVED":
            "OPEN",

        "AMBIGUOUS_SAME_BAR":
            "AMBIG",

        "NO_SETUP":
            "NONE",
    }

    return mapping.get(
        value,
        value,
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

    episode_results = []

    failures = 0

    for episode_id, phase_rows in grouped.items():
        by_phase = {
            str(
                row.get("phase")
                or ""
            ).upper():
                row
            for row in phase_rows
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
            not emerging.direction_available
            or not emerging.measurement_complete
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

        entry = emerging.phase_price

        current_stop = f(
            row.get(
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
                build_all_candidates(
                    direction,
                    entry,
                    current_stop,
                    pre15,
                    pre1h,
                )
            )

            future = []

            complete = False

            if candidates:
                (
                    future,
                    complete,
                ) = future_path(
                    client,
                    symbol,
                    product_type,
                    phase_at,
                )

            policies = {}

            for policy in POLICIES:
                policies[
                    policy
                ] = outcome_for_policy(
                    policy,
                    candidates,
                    direction,
                    future,
                )

            episode_results.append(
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
    print("=" * 150)
    print(
        "ALPHA HUNTER V7.10 "
        "STOP-POLICY MATRIX — SHADOW"
    )
    print("=" * 150)

    print(
        f"{'SYMBOL':<14}"
        f"{'DIR':<7}"
        f"{'OK?':<6}"
        f"{'CURRENT':<12}"
        f"{'TIGHT':<12}"
        f"{'WIDE':<12}"
        f"{'15M4':<12}"
        f"{'15M6':<12}"
        f"{'15M8':<12}"
        f"{'15M12':<12}"
    )

    print("-" * 150)

    for episode in episode_results:
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

        for policy in POLICIES:
            result = (
                episode[
                    "policies"
                ][policy]
            )

            cell = (
                short_outcome(
                    result[
                        "outcome"
                    ]
                )
            )

            if result[
                "rr"
            ] is not None:
                cell += (
                    f"/{n(result['rr'])}"
                )

            cells.append(
                cell
            )

        print(
            f"{episode['symbol']:<14}"
            f"{episode['direction']:<7}"
            f"{ok:<6}"
            f"{cells[0]:<12}"
            f"{cells[1]:<12}"
            f"{cells[2]:<12}"
            f"{cells[3]:<12}"
            f"{cells[4]:<12}"
            f"{cells[5]:<12}"
            f"{cells[6]:<12}"
        )

    print()
    print("=" * 150)
    print(
        "CORRECT EARLY DIRECTION — "
        "POLICY SUMMARY"
    )
    print("=" * 150)

    for policy in POLICIES:
        counts = defaultdict(
            int
        )

        resolved_r = 0.0

        resolved = 0

        for episode in episode_results:
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

        print(
            "  TARGET_FIRST:",
            counts[
                "TARGET_FIRST"
            ],
        )

        print(
            "  STOP_FIRST:",
            counts[
                "STOP_FIRST"
            ],
        )

        print(
            "  UNRESOLVED:",
            counts[
                "UNRESOLVED"
            ],
        )

        print(
            "  AMBIGUOUS:",
            counts[
                "AMBIGUOUS_SAME_BAR"
            ],
        )

        print(
            "  NO_SETUP:",
            counts[
                "NO_SETUP"
            ],
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
        "No policy is selected as the winner."
    )

    print(
        "This compares pre-declared "
        "structural stop policies only."
    )

    print(
        "Incomplete 24H episodes remain "
        "UNRESOLVED."
    )

    print(
        "Provisional R excludes fees, "
        "slippage and unresolved episodes."
    )

    print(
        "READ ONLY — NO SUPABASE WRITES "
        "— NO TRADE PERMISSION."
    )

    print()
    print(
        "Evaluated:",
        len(
            episode_results
        ),
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
