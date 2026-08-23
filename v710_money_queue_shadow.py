from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent

TIMEFRAMES = (
    "15m",
    "1H",
    "4H",
)

TF_RANK = {
    timeframe: index
    for index, timeframe
    in enumerate(TIMEFRAMES)
}

NON_RR_CHECKS = (
    "direction_aligned",
    "structure_valid",
    "momentum_confirmed",
    "participation_confirmed",
    "funding_not_extreme",
    "data_integrity_min_88",
)

EXECUTION_PHASES = {
    "RECOVERY",
    "IGNITION",
}

TERMINAL_PHASES = {
    "FOMO",
    "EXTENDED",
    "EXPANSION_MANAGEMENT",
    "RECOVERY_MANAGEMENT",
}


DIRECTIONALLY_INVALID_PHASES = {
    "LONG": {
        "DISTRIBUTION_RISK",
        "BREAKDOWN",
    },
    "SHORT": set(),
}


def number(
    value: Any,
) -> float | None:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def required_entry_for_constraints(
    direction: str,
    stop: float,
    target: float,
    atr: float,
    minimum_rr: float = 5.0,
    maximum_risk_pct: float = 2.0,
    maximum_atr_x: float = 3.0,
) -> dict[str, float] | None:
    direction = direction.upper()

    if direction not in {
        "LONG",
        "SHORT",
    }:
        return None

    if (
        stop <= 0
        or target <= 0
        or atr <= 0
        or minimum_rr <= 0
        or maximum_risk_pct <= 0
        or maximum_atr_x <= 0
    ):
        return None

    risk_fraction = (
        maximum_risk_pct
        / 100.0
    )

    if direction == "LONG":
        if stop >= target:
            return None

        rr_entry = (
            target
            + minimum_rr * stop
        ) / (
            minimum_rr + 1.0
        )

        risk_entry = (
            stop
            / (
                1.0
                - risk_fraction
            )
        )

        atr_entry = (
            stop
            + maximum_atr_x * atr
        )

        required_entry = min(
            rr_entry,
            risk_entry,
            atr_entry,
        )

        if not (
            stop
            < required_entry
            < target
        ):
            return None

    else:
        if target >= stop:
            return None

        rr_entry = (
            minimum_rr * stop
            + target
        ) / (
            minimum_rr + 1.0
        )

        risk_entry = (
            stop
            / (
                1.0
                + risk_fraction
            )
        )

        atr_entry = (
            stop
            - maximum_atr_x * atr
        )

        required_entry = max(
            rr_entry,
            risk_entry,
            atr_entry,
        )

        if not (
            target
            < required_entry
            < stop
        ):
            return None

    risk = abs(
        required_entry
        - stop
    )

    reward = abs(
        target
        - required_entry
    )

    if risk <= 0:
        return None

    planned_rr = (
        reward
        / risk
    )

    planned_risk_pct = (
        risk
        / required_entry
        * 100.0
    )

    planned_atr_x = (
        risk
        / atr
    )

    return {
        "required_entry":
            required_entry,

        "rr_entry":
            rr_entry,

        "risk_entry":
            risk_entry,

        "atr_entry":
            atr_entry,

        "planned_rr":
            planned_rr,

        "planned_risk_pct":
            planned_risk_pct,

        "planned_atr_x":
            planned_atr_x,
    }


def build_candidate(
    row: dict[str, Any],
    stop_tf: str,
    target_tf: str,
    minimum_rr: float = 5.0,
    maximum_risk_pct: float = 2.0,
    maximum_atr_x: float = 3.0,
    minimum_execution_score: float = 7.5,
) -> dict[str, Any] | None:
    if (
        stop_tf not in TF_RANK
        or target_tf not in TF_RANK
    ):
        return None

    # Execution invalidation should normally
    # come from the same or lower timeframe
    # than the reward horizon.
    if (
        TF_RANK[target_tf]
        < TF_RANK[stop_tf]
    ):
        return None

    setup = (
        row.get(
            "execution_setup",
            {},
        )
        or {}
    )

    direction = str(
        setup.get(
            "direction"
        )
        or ""
    ).upper()

    current = number(
        row.get(
            "last_price"
        )
    )

    if (
        direction not in {
            "LONG",
            "SHORT",
        }
        or current in (
            None,
            0,
        )
    ):
        return None

    phase = (
        row.get(
            "market_phase"
        )
    )

    timing = (
        row.get(
            "opportunity_timing"
        )
    )

    # Do not queue clearly stale/late structures.
    if (
        phase in TERMINAL_PHASES
        or timing == "LATE"
    ):
        return None

    if (
        phase
        in DIRECTIONALLY_INVALID_PHASES.get(
            direction,
            set(),
        )
    ):
        return None

    timeframes = (
        row.get(
            "timeframes",
            {},
        )
        or {}
    )

    stop_obj = (
        timeframes.get(
            stop_tf,
            {},
        )
        or {}
    )

    target_obj = (
        timeframes.get(
            target_tf,
            {},
        )
        or {}
    )

    atr = number(
        (
            stop_obj
            .get(
                "indicators",
                {},
            )
            .get(
                "atr_14"
            )
        )
    )

    if direction == "LONG":
        stop = number(
            stop_obj.get(
                "support"
            )
        )

        target = number(
            target_obj.get(
                "resistance"
            )
        )

        if (
            stop is None
            or target is None
            or atr is None
            or not (
                stop
                < current
                < target
            )
        ):
            return None

    else:
        stop = number(
            stop_obj.get(
                "resistance"
            )
        )

        target = number(
            target_obj.get(
                "support"
            )
        )

        if (
            stop is None
            or target is None
            or atr is None
            or not (
                target
                < current
                < stop
            )
        ):
            return None

    geometry = (
        required_entry_for_constraints(
            direction,
            stop,
            target,
            atr,
            minimum_rr,
            maximum_risk_pct,
            maximum_atr_x,
        )
    )

    if geometry is None:
        return None

    required_entry = (
        geometry[
            "required_entry"
        ]
    )

    current_risk = abs(
        current
        - stop
    )

    current_reward = abs(
        target
        - current
    )

    current_rr = (
        current_reward
        / current_risk
        if current_risk > 0
        else None
    )

    if direction == "LONG":
        price_ready = (
            current
            <= required_entry
        )
    else:
        price_ready = (
            current
            >= required_entry
        )

    distance_pct = (
        (
            required_entry
            - current
        )
        / current
        * 100.0
    )

    checks = (
        setup.get(
            "checks",
            {},
        )
        or {}
    )

    missing_checks = [
        name
        for name
        in NON_RR_CHECKS
        if checks.get(name)
        is not True
    ]

    behaviour_score = number(
        row.get(
            "behaviour_score"
        )
    )

    production_blockers = []

    if (
        row.get(
            "trade_permission"
        )
        is not True
    ):
        production_blockers.append(
            "CURRENT_TRADE_PERMISSION_FALSE"
        )

    if (
        behaviour_score is None
        or behaviour_score
        < minimum_execution_score
    ):
        production_blockers.append(
            "EXECUTION_SCORE_BELOW_MINIMUM"
        )

    if phase not in EXECUTION_PHASES:
        production_blockers.append(
            (
                "PHASE_"
                + str(phase)
                + "_NOT_PRODUCTION_EXECUTION_PHASE"
            )
        )

    if timing != "EARLY":
        production_blockers.append(
            (
                "TIMING_"
                + str(timing)
                + "_NOT_EARLY"
            )
        )

    if (
        row.get(
            "v7_trade_ready"
        )
        is not True
    ):
        production_blockers.append(
            "CURRENT_V7_TRADE_READY_FALSE"
        )

    return {
        "symbol":
            row.get(
                "symbol"
            ),

        "direction":
            direction,

        "current_price":
            current,

        "current_rr":
            current_rr,

        "required_entry":
            required_entry,

        "distance_from_current_pct":
            distance_pct,

        "price_ready":
            price_ready,

        "stop":
            stop,

        "stop_timeframe":
            stop_tf,

        "target":
            target,

        "target_timeframe":
            target_tf,

        "planned_rr":
            geometry[
                "planned_rr"
            ],

        "planned_risk_pct":
            geometry[
                "planned_risk_pct"
            ],

        "planned_atr_x":
            geometry[
                "planned_atr_x"
            ],

        "rr_entry_boundary":
            geometry[
                "rr_entry"
            ],

        "risk_entry_boundary":
            geometry[
                "risk_entry"
            ],

        "atr_entry_boundary":
            geometry[
                "atr_entry"
            ],

        "market_phase":
            phase,

        "opportunity_timing":
            timing,

        "behaviour_score":
            behaviour_score,

        "missing_non_rr_checks":
            missing_checks,

        "production_blockers":
            production_blockers,

        "production_trade_permission":
            bool(
                row.get(
                    "trade_permission"
                )
            ),

        "production_v7_trade_ready":
            bool(
                row.get(
                    "v7_trade_ready"
                )
            ),

        # Critical safety rule:
        # this module can never grant permission.
        "shadow_trade_permission":
            False,

        "shadow_only":
            True,
    }


def candidate_rank(
    row: dict[str, Any],
) -> tuple[Any, ...]:
    return (
        0
        if row.get(
            "price_ready"
        )
        else 1,

        len(
            row.get(
                "missing_non_rr_checks",
                [],
            )
        ),

        abs(
            float(
                row.get(
                    "distance_from_current_pct"
                )
                or 0.0
            )
        ),

        -float(
            row.get(
                "planned_rr"
            )
            or 0.0
        ),
    )


def generate_money_queue(
    snapshot: dict[str, Any],
    config: dict[str, Any],
    maximum_risk_pct: float = 2.0,
    maximum_atr_x: float = 3.0,
) -> list[dict[str, Any]]:
    quality = (
        config.get(
            "candidate_quality",
            {},
        )
        or {}
    )

    minimum_rr = float(
        quality.get(
            "minimum_execution_reward_risk",
            config.get(
                "minimum_reward_risk",
                5.0,
            ),
        )
    )

    minimum_execution_score = float(
        quality.get(
            "minimum_execution_score",
            7.5,
        )
    )

    candidates = []

    for row in snapshot.get(
        "symbols",
        [],
    ):
        if (
            not isinstance(
                row,
                dict,
            )
            or "error" in row
        ):
            continue

        for stop_tf in TIMEFRAMES:
            for target_tf in TIMEFRAMES:
                candidate = (
                    build_candidate(
                        row,
                        stop_tf,
                        target_tf,
                        minimum_rr,
                        maximum_risk_pct,
                        maximum_atr_x,
                        minimum_execution_score,
                    )
                )

                if candidate is not None:
                    candidates.append(
                        candidate
                    )

    # Keep only the best current structural
    # route per symbol.
    best_by_symbol = {}

    for candidate in candidates:
        symbol = str(
            candidate.get(
                "symbol"
            )
            or ""
        )

        if not symbol:
            continue

        existing = (
            best_by_symbol.get(
                symbol
            )
        )

        if (
            existing is None
            or candidate_rank(
                candidate
            )
            < candidate_rank(
                existing
            )
        ):
            best_by_symbol[
                symbol
            ] = candidate

    queue = list(
        best_by_symbol.values()
    )

    queue.sort(
        key=candidate_rank
    )

    return queue


def load_json(
    path: Path,
) -> dict[str, Any]:
    return json.loads(
        path.read_text()
    )


def main() -> int:
    config = load_json(
        ROOT / "config.json"
    )

    snapshot_dir = (
        ROOT
        / config.get(
            "snapshot_directory",
            "data/snapshots",
        )
    )

    snapshot = load_json(
        snapshot_dir
        / "latest.json"
    )

    queue = generate_money_queue(
        snapshot,
        config,
    )

    print(
        "MONEY QUEUE SHADOW V1"
    )
    print(
        "Snapshot:",
        snapshot.get(
            "collected_at_utc"
        ),
    )
    print(
        "Shadow trade permission: FALSE"
    )
    print()

    if not queue:
        print(
            "NO MONEY QUEUE CANDIDATES"
        )
        return 0

    for index, row in enumerate(
        queue[:15],
        1,
    ):
        direction = row[
            "direction"
        ]

        operator = (
            "<="
            if direction == "LONG"
            else ">="
        )

        print(
            f"{index:>2}. "
            f"{row['symbol']} "
            f"{direction}"
        )

        print(
            "    current=",
            row[
                "current_price"
            ],
            "currentRR=",
            (
                f"{row['current_rr']:.2f}"
                if row[
                    "current_rr"
                ]
                is not None
                else "N/A"
            ),
        )

        print(
            "    wait:",
            f"entry {operator} "
            f"{row['required_entry']}",
            f"distance="
            f"{row['distance_from_current_pct']:+.2f}%",
        )

        print(
            "    stop=",
            row["stop"],
            f"({row['stop_timeframe']})",
            "target=",
            row["target"],
            f"({row['target_timeframe']})",
        )

        print(
            "    planned:",
            f"RR={row['planned_rr']:.2f}",
            f"risk={row['planned_risk_pct']:.2f}%",
            f"ATR={row['planned_atr_x']:.2f}x",
        )

        print(
            "    phase=",
            row["market_phase"],
            "timing=",
            row[
                "opportunity_timing"
            ],
            "score=",
            row[
                "behaviour_score"
            ],
        )

        missing = (
            row[
                "missing_non_rr_checks"
            ]
        )

        print(
            "    missing=",
            (
                ", ".join(
                    missing
                )
                if missing
                else "NONE"
            ),
        )

        blockers = (
            row[
                "production_blockers"
            ]
        )

        print(
            "    production blockers=",
            (
                ", ".join(
                    blockers
                )
                if blockers
                else "NONE"
            ),
        )

        print(
            "    status=",
            (
                "PRICE READY / "
                "PRODUCTION STILL REQUIRED"
                if row[
                    "price_ready"
                ]
                else "WAIT FOR PRICE"
            ),
        )

        print()

    print(
        "PRODUCTION CHANGED: NO"
    )
    print(
        "SHADOW TRADE PERMISSION: FALSE"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
