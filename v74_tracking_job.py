from __future__ import annotations

import os
from collections import defaultdict
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
            evaluator.evaluate_horizon(
                horizon
            )
        )

        total_saved += saved
        total_failed += failed

        print(
            f"OUTCOMES {horizon}H: "
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
                    "direction_adjusted_return_pct"
                ),
            "limit":
                "20000",
        },
    )

    return (
        signals,
        outcomes,
    )


def build_performance_report(
    signals: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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

        path = payload.get(
            "pre_move_path"
        )

        if tier not in {
            "PRIMARY",
            "RESERVE",
        }:
            continue

        if path not in {
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

        signal_map[
            signal_id
        ] = {
            "tier":
                tier,

            "path":
                path,

            "score":
                f(
                    payload.get(
                        "pre_move_score"
                    )
                ),
        }

    groups: dict[
        tuple[str, str, int],
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

        horizon = outcome.get(
            "horizon_hours"
        )

        try:
            horizon = int(
                horizon
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        raw_return = f(
            outcome.get(
                "return_pct"
            )
        )

        if raw_return is None:
            continue

        key = (
            str(
                signal["tier"]
            ),
            str(
                signal["path"]
            ),
            horizon,
        )

        groups[
            key
        ].append(
            raw_return
        )

    report = []

    for (
        tier,
        path,
        horizon,
    ), values in groups.items():

        n = len(
            values
        )

        positive = sum(
            value > 0
            for value in values
        )

        big_move = sum(
            value >= 5
            for value in values
        )

        avg_return = (
            sum(values)
            / n
            if n
            else 0.0
        )

        report.append({
            "tier":
                tier,

            "path":
                path,

            "horizon":
                horizon,

            "n":
                n,

            "positive":
                positive,

            "win_rate":
                (
                    positive
                    / n
                    * 100
                    if n
                    else 0.0
                ),

            "big_moves":
                big_move,

            "big_move_rate":
                (
                    big_move
                    / n
                    * 100
                    if n
                    else 0.0
                ),

            "avg_return":
                avg_return,
        })

    report.sort(
        key=lambda row: (
            row["horizon"],
            0
            if row["tier"]
            == "PRIMARY"
            else 1,
            row["path"],
        )
    )

    return report


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
    report: list[dict[str, Any]],
) -> None:
    print()
    print(
        "=" * 100
    )

    print(
        "V7.4 PERFORMANCE — PRIMARY vs RESERVE / CONTINUATION vs REVERSAL"
    )

    print(
        "=" * 100
    )

    if not report:
        print(
            "No matured V7.4 outcomes yet."
        )

        return

    print(
        f"{'H':>3} "
        f"{'TIER':<9} "
        f"{'PATH':<13} "
        f"{'N':>5} "
        f"{'WIN%':>8} "
        f"{'+5%':>6} "
        f"{'+5% RATE':>10} "
        f"{'AVG RET':>10}"
    )

    print(
        "-" * 100
    )

    for row in report:
        print(
            f"{row['horizon']:>3} "
            f"{row['tier']:<9} "
            f"{row['path']:<13} "
            f"{row['n']:>5} "
            f"{row['win_rate']:>7.1f}% "
            f"{row['big_moves']:>6} "
            f"{row['big_move_rate']:>9.1f}% "
            f"{row['avg_return']:>9.3f}%"
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
