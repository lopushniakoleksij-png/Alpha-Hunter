from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.bitget import BitgetClient
from alpha_hunter.collector import (
    load_config,
    load_previous_snapshot,
)
from alpha_hunter.env import load_env_file
from alpha_hunter.feature_capture import FeatureStorage
from alpha_hunter.outcome_evaluator import OutcomeEvaluator
from alpha_hunter.performance import PerformanceStorage
from alpha_hunter.storage import SupabaseConfig


HORIZONS = (1, 4, 12, 24)


def headers(
    key: str,
) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def get_rows(
    url: str,
    key: str,
    table: str,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    response = requests.get(
        f"{url}/rest/v1/{table}",
        params=params,
        headers=headers(key),
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, list):
        return []

    return payload


def f(
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


def save_latest_signal_cohort(
    snapshot: dict[str, Any],
    settings: SupabaseConfig,
) -> int:
    return PerformanceStorage(
        settings.url,
        settings.key,
    ).save_signals(
        snapshot
    )


def save_latest_features(
    snapshot: dict[str, Any],
    settings: SupabaseConfig,
) -> int:
    return FeatureStorage(
        settings.url,
        settings.key,
    ).save(
        snapshot
    )


def pending_v74_signals(
    url: str,
    key: str,
    horizon_hours: int,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    cutoff = datetime.fromtimestamp(
        datetime.now(
            timezone.utc
        ).timestamp()
        - horizon_hours
        * 3600,
        tz=timezone.utc,
    ).isoformat()

    signals = get_rows(
        url,
        key,
        "alpha_hunter_signals",
        {
            "select":
                (
                    "signal_id,symbol,"
                    "detected_at_utc,state,"
                    "direction,reference_price,"
                    "entry_price,stop_loss,"
                    "take_profit,payload"
                ),

            # Newest matured signals first.
            # This prevents historical backlog
            # from starving current V7.4 cohorts.
            "detected_at_utc":
                f"lte.{cutoff}",

            "order":
                "detected_at_utc.desc",

            "limit":
                str(limit),
        },
    )

    v74_signals = []

    for signal in signals:
        payload = (
            signal.get("payload")
            or {}
        )

        if not isinstance(
            payload,
            dict,
        ):
            continue

        tier = payload.get(
            "pre_move_tier"
        )

        path_name = payload.get(
            "pre_move_path"
        )

        if tier not in {
            "PRIMARY",
            "RESERVE",
        }:
            continue

        if path_name not in {
            "CONTINUATION",
            "REVERSAL",
        }:
            continue

        v74_signals.append(
            signal
        )

    if not v74_signals:
        return []

    ids = [
        str(
            row["signal_id"]
        )
        for row in v74_signals
        if row.get(
            "signal_id"
        )
    ]

    completed: set[str] = set()

    # Keep PostgREST URLs small.
    batch_size = 100

    for index in range(
        0,
        len(ids),
        batch_size,
    ):
        batch = ids[
            index:
            index + batch_size
        ]

        existing = get_rows(
            url,
            key,
            "alpha_hunter_signal_outcomes",
            {
                "select":
                    "signal_id",

                "horizon_hours":
                    f"eq.{horizon_hours}",

                "signal_id":
                    (
                        "in.("
                        + ",".join(batch)
                        + ")"
                    ),

                "limit":
                    str(
                        len(batch)
                    ),
            },
        )

        completed.update(
            str(
                row.get(
                    "signal_id"
                )
            )
            for row in existing
            if row.get(
                "signal_id"
            )
        )

    return [
        row
        for row in v74_signals
        if str(
            row.get(
                "signal_id"
            )
        )
        not in completed
    ]


def evaluate_v74_horizon(
    evaluator: OutcomeEvaluator,
    url: str,
    key: str,
    horizon_hours: int,
) -> tuple[int, int]:
    pending = pending_v74_signals(
        url,
        key,
        horizon_hours,
    )

    if not pending:
        return 0, 0

    rows = []
    failures = 0

    evaluated_at = datetime.now(
        timezone.utc
    ).isoformat()

    price_cache: dict[
        str,
        float,
    ] = {}

    for signal in pending:
        symbol = str(
            signal.get(
                "symbol"
            )
            or ""
        )

        try:
            if symbol not in price_cache:
                ticker = evaluator.bitget.ticker(
                    symbol,
                    evaluator.product_type,
                )

                price = f(
                    ticker.get(
                        "lastPr"
                    )
                    or ticker.get(
                        "last"
                    )
                )

                if (
                    price is None
                    or price <= 0
                ):
                    raise ValueError(
                        "Invalid current price"
                    )

                price_cache[
                    symbol
                ] = price

            current_price = (
                price_cache[
                    symbol
                ]
            )

            result = (
                evaluator.classify(
                    signal,
                    current_price,
                )
            )

            payload = (
                signal.get(
                    "payload"
                )
                or {}
            )

            if not isinstance(
                payload,
                dict,
            ):
                payload = {}

            rows.append({
                "signal_id":
                    signal[
                        "signal_id"
                    ],

                "horizon_hours":
                    horizon_hours,

                "evaluated_at_utc":
                    evaluated_at,

                "evaluation_price":
                    current_price,

                "return_pct":
                    result[
                        "return_pct"
                    ],

                "direction_adjusted_return_pct":
                    result[
                        "direction_adjusted_return_pct"
                    ],

                "target_hit":
                    result[
                        "target_hit"
                    ],

                "stop_hit":
                    result[
                        "stop_hit"
                    ],

                "outcome_class":
                    result[
                        "outcome_class"
                    ],

                "payload": {
                    "measurement_scope":
                        "V7.4_PRE_MOVE",

                    "direction_used":
                        result[
                            "direction_used"
                        ],

                    "reference_price":
                        signal.get(
                            "reference_price"
                        ),

                    "state":
                        signal.get(
                            "state"
                        ),

                    "pre_move_tier":
                        payload.get(
                            "pre_move_tier"
                        ),

                    "pre_move_path":
                        payload.get(
                            "pre_move_path"
                        ),

                    "pre_move_rank":
                        payload.get(
                            "pre_move_rank"
                        ),

                    "pre_move_score":
                        payload.get(
                            "pre_move_score"
                        ),
                },
            })

        except Exception as exc:
            failures += 1

            print(
                "V7.4 outcome evaluation "
                f"failed for {symbol} "
                f"at {horizon_hours}H: "
                f"{exc}"
            )

    evaluator._upsert(
        "alpha_hunter_signal_outcomes",
        rows,
        "signal_id,horizon_hours",
    )

    return (
        len(rows),
        failures,
    )


def evaluate_outcomes(
    config: dict[str, Any],
    settings: SupabaseConfig,
) -> tuple[int, int]:
    evaluator = OutcomeEvaluator(
        settings.url,
        settings.key,
        BitgetClient.from_environment(
            timeout=config.get(
                "request_timeout_seconds",
                12,
            ),
            max_retries=config.get(
                "max_retries",
                3,
            ),
        ),
        config["product_type"],
    )

    total_saved = 0
    total_failed = 0

    for horizon in HORIZONS:
        saved, failed = (
            evaluate_v74_horizon(
                evaluator,
                settings.url,
                settings.key,
                horizon,
            )
        )

        total_saved += saved
        total_failed += failed

        print(
            f"V7.4 OUTCOMES {horizon}H: "
            f"saved={saved} "
            f"failed={failed}"
        )

    return (
        total_saved,
        total_failed,
    )


def current_v74_candidates(
    url: str,
    key: str,
    run_id: str,
) -> list[dict[str, Any]]:
    rows = get_rows(
        url,
        key,
        "alpha_hunter_signals",
        {
            "select":
                (
                    "signal_id,run_id,symbol,"
                    "detected_at_utc,state,"
                    "direction,payload"
                ),
            "run_id":
                f"eq.{run_id}",
            "limit":
                "1000",
        },
    )

    output = []

    for row in rows:
        payload = (
            row.get("payload")
            or {}
        )

        if not isinstance(
            payload,
            dict,
        ):
            continue

        tier = payload.get(
            "pre_move_tier"
        )

        if tier not in {
            "PRIMARY",
            "RESERVE",
        }:
            continue

        output.append({
            "signal_id":
                row.get(
                    "signal_id"
                ),

            "symbol":
                row.get(
                    "symbol"
                ),

            "state":
                row.get(
                    "state"
                ),

            "tier":
                tier,

            "rank":
                payload.get(
                    "pre_move_rank"
                ),

            "path":
                payload.get(
                    "pre_move_path"
                ),

            "score":
                f(
                    payload.get(
                        "pre_move_score"
                    )
                ),
        })

    output.sort(
        key=lambda item:
            item.get(
                "rank"
            )
            or 999
    )

    return output


def load_v74_history(
    url: str,
    key: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    signals = get_rows(
        url,
        key,
        "alpha_hunter_signals",
        {
            "select":
                (
                    "signal_id,symbol,"
                    "detected_at_utc,payload"
                ),
            "order":
                "detected_at_utc.desc",
            "limit":
                "5000",
        },
    )

    outcomes = get_rows(
        url,
        key,
        "alpha_hunter_signal_outcomes",
        {
            "select":
                (
                    "signal_id,horizon_hours,"
                    "return_pct,"
                    "direction_adjusted_return_pct,"
                    "evaluated_at_utc"
                ),
            "order":
                "evaluated_at_utc.desc",
            "limit":
                "20000",
        },
    )

    return (
        signals,
        outcomes,
    )


def _rank_bucket(
    rank: Any,
) -> str:
    try:
        rank_int = int(rank)
    except (TypeError, ValueError):
        return "UNRANKED"

    if rank_int <= 3:
        return "TOP_1_3"

    if rank_int <= 5:
        return "TOP_4_5"

    return "RESERVE_6_10"


def _movement_metrics(
    values: list[float],
) -> dict[str, Any]:
    n = len(values)

    if not n:
        return {
            "n": 0,
            "avg_raw_return": 0.0,
            "avg_abs_move": 0.0,
            "positive_rate": 0.0,
            "up_3_rate": 0.0,
            "up_5_rate": 0.0,
            "up_10_rate": 0.0,
            "down_3_rate": 0.0,
            "down_5_rate": 0.0,
            "down_10_rate": 0.0,
            "expansion_3_rate": 0.0,
            "expansion_5_rate": 0.0,
            "expansion_10_rate": 0.0,
        }

    def rate(
        predicate,
    ) -> float:
        return (
            sum(
                1
                for value in values
                if predicate(value)
            )
            / n
            * 100
        )

    return {
        "n":
            n,

        "avg_raw_return":
            sum(values)
            / n,

        "avg_abs_move":
            sum(
                abs(value)
                for value in values
            )
            / n,

        "positive_rate":
            rate(
                lambda value:
                    value > 0
            ),

        "up_3_rate":
            rate(
                lambda value:
                    value >= 3
            ),

        "up_5_rate":
            rate(
                lambda value:
                    value >= 5
            ),

        "up_10_rate":
            rate(
                lambda value:
                    value >= 10
            ),

        "down_3_rate":
            rate(
                lambda value:
                    value <= -3
            ),

        "down_5_rate":
            rate(
                lambda value:
                    value <= -5
            ),

        "down_10_rate":
            rate(
                lambda value:
                    value <= -10
            ),

        # Expansion is direction-neutral.
        # This is the correct core metric for
        # PRE-MOVE surveillance.
        "expansion_3_rate":
            rate(
                lambda value:
                    abs(value) >= 3
            ),

        "expansion_5_rate":
            rate(
                lambda value:
                    abs(value) >= 5
            ),

        "expansion_10_rate":
            rate(
                lambda value:
                    abs(value) >= 10
            ),
    }


def build_performance_report(
    signals: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    signal_map: dict[
        str,
        dict[str, Any],
    ] = {}

    for signal in signals:
        payload = (
            signal.get("payload")
            or {}
        )

        if not isinstance(
            payload,
            dict,
        ):
            continue

        tier = payload.get(
            "pre_move_tier"
        )

        path_name = payload.get(
            "pre_move_path"
        )

        if tier not in {
            "PRIMARY",
            "RESERVE",
        }:
            continue

        if path_name not in {
            "CONTINUATION",
            "REVERSAL",
        }:
            continue

        signal_id = str(
            signal.get(
                "signal_id"
            )
            or ""
        )

        if not signal_id:
            continue

        rank = payload.get(
            "pre_move_rank"
        )

        signal_map[
            signal_id
        ] = {
            "tier":
                tier,

            "path":
                path_name,

            "rank":
                rank,

            "rank_bucket":
                _rank_bucket(
                    rank
                ),

            "score":
                f(
                    payload.get(
                        "pre_move_score"
                    )
                ),
        }

    tier_path_groups: dict[
        tuple[str, str, int],
        list[float],
    ] = defaultdict(list)

    rank_groups: dict[
        tuple[str, int],
        list[float],
    ] = defaultdict(list)

    for outcome in outcomes:
        signal_id = str(
            outcome.get(
                "signal_id"
            )
            or ""
        )

        signal = signal_map.get(
            signal_id
        )

        if not signal:
            continue

        try:
            horizon = int(
                outcome.get(
                    "horizon_hours"
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        # IMPORTANT:
        # V7.4 surveillance is evaluated
        # from RAW market return.
        #
        # We deliberately DO NOT use
        # direction_adjusted_return_pct here.
        raw_return = f(
            outcome.get(
                "return_pct"
            )
        )

        if raw_return is None:
            continue

        tier_path_key = (
            str(
                signal["tier"]
            ),
            str(
                signal["path"]
            ),
            horizon,
        )

        tier_path_groups[
            tier_path_key
        ].append(
            raw_return
        )

        rank_key = (
            str(
                signal[
                    "rank_bucket"
                ]
            ),
            horizon,
        )

        rank_groups[
            rank_key
        ].append(
            raw_return
        )

    tier_path_report = []

    for (
        tier,
        path_name,
        horizon,
    ), values in tier_path_groups.items():

        tier_path_report.append({
            "tier":
                tier,

            "path":
                path_name,

            "horizon":
                horizon,

            **_movement_metrics(
                values
            ),
        })

    tier_path_report.sort(
        key=lambda row: (
            row["horizon"],
            0
            if row["tier"]
            == "PRIMARY"
            else 1,
            row["path"],
        )
    )

    rank_report = []

    bucket_order = {
        "TOP_1_3": 0,
        "TOP_4_5": 1,
        "RESERVE_6_10": 2,
        "UNRANKED": 3,
    }

    for (
        bucket,
        horizon,
    ), values in rank_groups.items():

        rank_report.append({
            "bucket":
                bucket,

            "horizon":
                horizon,

            **_movement_metrics(
                values
            ),
        })

    rank_report.sort(
        key=lambda row: (
            row["horizon"],
            bucket_order.get(
                row["bucket"],
                99,
            ),
        )
    )

    return {
        "tier_path":
            tier_path_report,

        "rank":
            rank_report,
    }


def print_current_candidates(
    candidates: list[dict[str, Any]],
) -> None:
    print()
    print(
        "=" * 90
    )

    print(
        "V7.4 CURRENT SURVEILLANCE COHORT"
    )

    print(
        "=" * 90
    )

    if not candidates:
        print(
            "No PRIMARY or RESERVE candidates."
        )

        return

    print(
        f"{'RANK':>4} "
        f"{'SYMBOL':<14} "
        f"{'TIER':<9} "
        f"{'PATH':<13} "
        f"{'SCORE':>7} "
        f"{'STATE'}"
    )

    print(
        "-" * 90
    )

    for row in candidates:
        print(
            f"{str(row.get('rank') or '—'):>4} "
            f"{str(row.get('symbol') or '—'):<14} "
            f"{str(row.get('tier') or '—'):<9} "
            f"{str(row.get('path') or '—'):<13} "
            f"{float(row.get('score') or 0):>7.2f} "
            f"{row.get('state') or '—'}"
        )


def print_performance(
    report: dict[
        str,
        list[dict[str, Any]],
    ],
) -> None:
    tier_path = report.get(
        "tier_path",
        [],
    )

    rank_report = report.get(
        "rank",
        [],
    )

    print()
    print(
        "=" * 128
    )

    print(
        "V7.4 FORWARD PERFORMANCE — RAW PRICE EXPANSION"
    )

    print(
        "=" * 128
    )

    if not tier_path:
        print(
            "No matured V7.4 outcomes yet."
        )

        return

    print()
    print(
        "PRIMARY / RESERVE + PATH"
    )

    print(
        f"{'H':>3} "
        f"{'TIER':<9} "
        f"{'PATH':<13} "
        f"{'N':>5} "
        f"{'POS%':>7} "
        f"{'AVG RAW':>9} "
        f"{'AVG ABS':>9} "
        f"{'EXP3%':>8} "
        f"{'EXP5%':>8} "
        f"{'EXP10%':>8} "
        f"{'UP5%':>7} "
        f"{'DN5%':>7}"
    )

    print(
        "-" * 128
    )

    for row in tier_path:
        print(
            f"{row['horizon']:>3} "
            f"{row['tier']:<9} "
            f"{row['path']:<13} "
            f"{row['n']:>5} "
            f"{row['positive_rate']:>6.1f}% "
            f"{row['avg_raw_return']:>8.3f}% "
            f"{row['avg_abs_move']:>8.3f}% "
            f"{row['expansion_3_rate']:>7.1f}% "
            f"{row['expansion_5_rate']:>7.1f}% "
            f"{row['expansion_10_rate']:>7.1f}% "
            f"{row['up_5_rate']:>6.1f}% "
            f"{row['down_5_rate']:>6.1f}%"
        )

    print()
    print(
        "RANK QUALITY"
    )

    print(
        f"{'H':>3} "
        f"{'RANK BUCKET':<15} "
        f"{'N':>5} "
        f"{'POS%':>7} "
        f"{'AVG RAW':>9} "
        f"{'AVG ABS':>9} "
        f"{'EXP3%':>8} "
        f"{'EXP5%':>8} "
        f"{'EXP10%':>8} "
        f"{'UP5%':>7} "
        f"{'DN5%':>7}"
    )

    print(
        "-" * 112
    )

    for row in rank_report:
        print(
            f"{row['horizon']:>3} "
            f"{row['bucket']:<15} "
            f"{row['n']:>5} "
            f"{row['positive_rate']:>6.1f}% "
            f"{row['avg_raw_return']:>8.3f}% "
            f"{row['avg_abs_move']:>8.3f}% "
            f"{row['expansion_3_rate']:>7.1f}% "
            f"{row['expansion_5_rate']:>7.1f}% "
            f"{row['expansion_10_rate']:>7.1f}% "
            f"{row['up_5_rate']:>6.1f}% "
            f"{row['down_5_rate']:>6.1f}%"
        )

    print()
    print(
        "Metric definitions:"
    )

    print(
        "AVG RAW = average raw market return from detection price."
    )

    print(
        "AVG ABS = average absolute price movement regardless of direction."
    )

    print(
        "EXP3/5/10 = percentage of candidates moving at least "
        "3% / 5% / 10% in either direction."
    )

    print(
        "UP5 = raw upside move >= +5%; "
        "DN5 = raw downside move <= -5%."
    )

    print(
        "No V7.4 trade-direction assumption is used in these metrics."
    )


def main() -> int:
    root = (
        Path(__file__)
        .resolve()
        .parent
    )

    load_env_file(
        root / ".env"
    )

    config = load_config(
        root
        / "config.json"
    )

    snapshot = load_previous_snapshot(
        root
        / "config.json",
        config,
    )

    if not snapshot:
        raise SystemExit(
            "No latest Alpha Hunter snapshot found"
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

    run_id = str(
        snapshot.get(
            "run_id"
        )
        or ""
    )

    if not run_id:
        raise SystemExit(
            "Latest snapshot has no run_id"
        )

    print(
        "V7.4 HOURLY PERFORMANCE TRACKER"
    )

    print(
        "Run ID:",
        run_id,
    )

    signal_count = (
        save_latest_signal_cohort(
            snapshot,
            settings,
        )
    )

    print(
        "PERFORMANCE SIGNALS SAVED:",
        signal_count,
    )

    feature_count = (
        save_latest_features(
            snapshot,
            settings,
        )
    )

    print(
        "FEATURE ROWS SAVED:",
        feature_count,
    )

    (
        outcomes_saved,
        outcomes_failed,
    ) = evaluate_outcomes(
        config,
        settings,
    )

    print(
        "OUTCOME EVALUATION COMPLETE: "
        f"saved={outcomes_saved} "
        f"failed={outcomes_failed}"
    )

    current = (
        current_v74_candidates(
            settings.url,
            settings.key,
            run_id,
        )
    )

    print_current_candidates(
        current
    )

    (
        historical_signals,
        historical_outcomes,
    ) = load_v74_history(
        settings.url,
        settings.key,
    )

    report = (
        build_performance_report(
            historical_signals,
            historical_outcomes,
        )
    )

    print_performance(
        report
    )

    print()
    print(
        "V7.4 TRACKING JOB: PASS"
    )

    return (
        0
        if outcomes_failed == 0
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
