from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig
from alpha_hunter.collector import load_config


HORIZONS = (4, 12)


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

    if not isinstance(
        payload,
        list,
    ):
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

        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def classify_move(
    value: float,
) -> str:
    if value >= 10:
        return "EXP10_UP"

    if value >= 5:
        return "EXP5_UP"

    if value >= 3:
        return "EXP3_UP"

    if value <= -10:
        return "EXP10_DOWN"

    if value <= -5:
        return "EXP5_DOWN"

    if value <= -3:
        return "EXP3_DOWN"

    return "FLAT"


def load_signals(
    url: str,
    key: str,
) -> list[dict[str, Any]]:
    return get_rows(
        url,
        key,
        "alpha_hunter_signals",
        {
            "select":
                (
                    "signal_id,symbol,"
                    "detected_at_utc,state,"
                    "payload"
                ),

            "order":
                "detected_at_utc.desc",

            "limit":
                "5000",
        },
    )


def load_outcomes(
    url: str,
    key: str,
) -> list[dict[str, Any]]:
    return get_rows(
        url,
        key,
        "alpha_hunter_signal_outcomes",
        {
            "select":
                (
                    "signal_id,horizon_hours,"
                    "return_pct,"
                    "evaluated_at_utc"
                ),

            "order":
                "evaluated_at_utc.desc",

            "limit":
                "20000",
        },
    )


def load_features(
    url: str,
    key: str,
) -> list[dict[str, Any]]:
    return get_rows(
        url,
        key,
        "alpha_hunter_signal_features",
        {
            "select":
                "*",

            "limit":
                "5000",
        },
    )


def extract_behaviour_score(
    payload: dict[str, Any],
) -> float | None:
    behaviour = payload.get(
        "behaviour",
        {},
    )

    if not isinstance(
        behaviour,
        dict,
    ):
        return None

    return f(
        behaviour.get(
            "score"
        )
    )


def build_signal_map(
    signals: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    dict[str, Any],
]:
    output = {}

    for row in signals:
        payload = (
            row.get(
                "payload"
            )
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
            "REVERSAL",
            "CONTINUATION",
        }:
            continue

        signal_id = str(
            row.get(
                "signal_id"
            )
            or ""
        )

        if not signal_id:
            continue

        output[
            signal_id
        ] = {
            "signal_id":
                signal_id,

            "symbol":
                row.get(
                    "symbol"
                ),

            "detected_at":
                row.get(
                    "detected_at_utc"
                ),

            "state":
                row.get(
                    "state"
                ),

            "tier":
                tier,

            "path":
                path_name,

            "rank":
                payload.get(
                    "pre_move_rank"
                ),

            "score":
                f(
                    payload.get(
                        "pre_move_score"
                    )
                ),

            "behaviour_score":
                extract_behaviour_score(
                    payload
                ),
        }

    return output


def build_feature_map(
    features: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    dict[str, Any],
]:
    output = {}

    for row in features:
        signal_id = str(
            row.get(
                "signal_id"
            )
            or ""
        )

        if signal_id:
            output[
                signal_id
            ] = row

    return output


def build_rows(
    signal_map: dict[
        str,
        dict[str, Any],
    ],
    feature_map: dict[
        str,
        dict[str, Any],
    ],
    outcomes: list[
        dict[str, Any]
    ],
) -> list[
    dict[str, Any]
]:
    rows = []

    for outcome in outcomes:
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

        if horizon not in HORIZONS:
            continue

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

        raw_return = f(
            outcome.get(
                "return_pct"
            )
        )

        if raw_return is None:
            continue

        feature = (
            feature_map.get(
                signal_id
            )
            or {}
        )

        row = dict(
            signal
        )

        row.update({
            "horizon":
                horizon,

            "return_pct":
                raw_return,

            "abs_move":
                abs(
                    raw_return
                ),

            "class":
                classify_move(
                    raw_return
                ),

            "compression":
                f(
                    feature.get(
                        "compression_score"
                    )
                ),

            "relative_strength":
                f(
                    feature.get(
                        "relative_strength_vs_btc"
                    )
                ),

            "volatility":
                f(
                    feature.get(
                        "volatility_pct"
                    )
                ),

            "volume_ratio":
                f(
                    feature.get(
                        "volume_ratio"
                    )
                ),

            "oi_change":
                f(
                    feature.get(
                        "oi_change_pct"
                    )
                ),

            "rsi_15m":
                f(
                    feature.get(
                        "rsi_15m"
                    )
                ),

            "rsi_1h":
                f(
                    feature.get(
                        "rsi_1h"
                    )
                ),

            "rsi_4h":
                f(
                    feature.get(
                        "rsi_4h"
                    )
                ),

            "trend_15m":
                feature.get(
                    "trend_15m"
                ),

            "trend_1h":
                feature.get(
                    "trend_1h"
                ),

            "trend_4h":
                feature.get(
                    "trend_4h"
                ),

            "ema_15m":
                feature.get(
                    "ema_alignment_15m"
                ),

            "ema_1h":
                feature.get(
                    "ema_alignment_1h"
                ),

            "ema_4h":
                feature.get(
                    "ema_alignment_4h"
                ),

            "liquidity":
                feature.get(
                    "liquidity_state"
                ),

            "resistance_distance":
                f(
                    feature.get(
                        "resistance_distance_pct"
                    )
                ),
        })

        rows.append(
            row
        )

    return rows


def print_candidates(
    rows: list[
        dict[str, Any]
    ],
    horizon: int,
) -> None:
    selected = [
        row
        for row in rows
        if (
            row[
                "horizon"
            ]
            == horizon
            and row[
                "path"
            ]
            == "REVERSAL"
        )
    ]

    selected.sort(
        key=lambda row:
            abs(
                row[
                    "return_pct"
                ]
            ),
        reverse=True,
    )

    print()
    print(
        "=" * 112
    )

    print(
        f"V7.4 REVERSAL FORENSICS — {horizon}H"
    )

    print(
        "=" * 112
    )

    print(
        f"{'SYMBOL':<14} "
        f"{'TIER':<9} "
        f"{'RANK':>4} "
        f"{'SCORE':>7} "
        f"{'RETURN':>9} "
        f"{'ABS':>8} "
        f"{'CLASS':<12} "
        f"{'BEHAV':>7}"
    )

    print(
        "-" * 112
    )

    for row in selected:
        print(
            f"{str(row.get('symbol') or '—'):<14} "
            f"{str(row.get('tier') or '—'):<9} "
            f"{str(row.get('rank') or '—'):>4} "
            f"{float(row.get('score') or 0):>7.2f} "
            f"{row['return_pct']:>8.3f}% "
            f"{row['abs_move']:>7.3f}% "
            f"{row['class']:<12} "
            f"{float(row.get('behaviour_score') or 0):>7.2f}"
        )


def numeric_summary(
    rows: list[
        dict[str, Any]
    ],
    field: str,
) -> tuple[
    int,
    float | None,
]:
    values = [
        f(
            row.get(
                field
            )
        )
        for row in rows
    ]

    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return (
            0,
            None,
        )

    return (
        len(values),
        sum(
            values
        )
        / len(
            values
        ),
    )


def compare_reversal_groups(
    rows: list[
        dict[str, Any]
    ],
    horizon: int,
) -> None:
    primary = [
        row
        for row in rows
        if (
            row[
                "horizon"
            ]
            == horizon
            and row[
                "tier"
            ]
            == "PRIMARY"
            and row[
                "path"
            ]
            == "REVERSAL"
        )
    ]

    winners = [
        row
        for row in primary
        if row[
            "return_pct"
        ]
        >= 5
    ]

    downside = [
        row
        for row in primary
        if row[
            "return_pct"
        ]
        <= -5
    ]

    flat = [
        row
        for row in primary
        if abs(
            row[
                "return_pct"
            ]
        )
        < 3
    ]

    print()
    print(
        "=" * 112
    )

    print(
        f"PRIMARY REVERSAL FEATURE COMPARISON — {horizon}H"
    )

    print(
        "=" * 112
    )

    print(
        "Groups:"
        f" EXP5_UP={len(winners)}"
        f" | EXP5_DOWN={len(downside)}"
        f" | FLAT={len(flat)}"
    )

    fields = (
        "score",
        "behaviour_score",
        "compression",
        "relative_strength",
        "volatility",
        "volume_ratio",
        "oi_change",
        "rsi_15m",
        "rsi_1h",
        "rsi_4h",
        "resistance_distance",
    )

    print()
    print(
        f"{'FEATURE':<24} "
        f"{'WIN N':>6} "
        f"{'WIN AVG':>10} "
        f"{'DOWN N':>7} "
        f"{'DOWN AVG':>10} "
        f"{'FLAT N':>7} "
        f"{'FLAT AVG':>10}"
    )

    print(
        "-" * 90
    )

    for field in fields:
        win_n, win_avg = (
            numeric_summary(
                winners,
                field,
            )
        )

        down_n, down_avg = (
            numeric_summary(
                downside,
                field,
            )
        )

        flat_n, flat_avg = (
            numeric_summary(
                flat,
                field,
            )
        )

        def display(
            value: float | None,
        ) -> str:
            if value is None:
                return "—"

            return (
                f"{value:.3f}"
            )

        print(
            f"{field:<24} "
            f"{win_n:>6} "
            f"{display(win_avg):>10} "
            f"{down_n:>7} "
            f"{display(down_avg):>10} "
            f"{flat_n:>7} "
            f"{display(flat_avg):>10}"
        )


def categorical_summary(
    rows: list[
        dict[str, Any]
    ],
    field: str,
) -> str:
    counts: dict[
        str,
        int,
    ] = defaultdict(int)

    for row in rows:
        value = row.get(
            field
        )

        if value in (
            None,
            "",
        ):
            continue

        counts[
            str(
                value
            )
        ] += 1

    if not counts:
        return "—"

    ranked = sorted(
        counts.items(),
        key=lambda item:
            item[1],
        reverse=True,
    )

    return ", ".join(
        f"{key}:{value}"
        for key, value in ranked[
            :3
        ]
    )


def compare_categorical(
    rows: list[
        dict[str, Any]
    ],
    horizon: int,
) -> None:
    primary = [
        row
        for row in rows
        if (
            row[
                "horizon"
            ]
            == horizon
            and row[
                "tier"
            ]
            == "PRIMARY"
            and row[
                "path"
            ]
            == "REVERSAL"
        )
    ]

    winners = [
        row
        for row in primary
        if row[
            "return_pct"
        ]
        >= 5
    ]

    flat = [
        row
        for row in primary
        if abs(
            row[
                "return_pct"
            ]
        )
        < 3
    ]

    print()
    print(
        "CATEGORICAL STRUCTURE"
    )

    fields = (
        "trend_15m",
        "trend_1h",
        "trend_4h",
        "ema_15m",
        "ema_1h",
        "ema_4h",
        "liquidity",
    )

    print(
        f"{'FEATURE':<20} "
        f"{'EXP5_UP':<42} "
        f"{'FLAT'}"
    )

    print(
        "-" * 110
    )

    for field in fields:
        print(
            f"{field:<20} "
            f"{categorical_summary(winners, field):<42} "
            f"{categorical_summary(flat, field)}"
        )


def main() -> int:
    root = (
        Path(__file__)
        .resolve()
        .parent
    )

    load_env_file(
        root
        / ".env"
    )

    config = load_config(
        root
        / "config.json"
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

    print(
        "V7.4 FORENSIC ANALYTICS"
    )

    signals = load_signals(
        settings.url,
        settings.key,
    )

    outcomes = load_outcomes(
        settings.url,
        settings.key,
    )

    features = load_features(
        settings.url,
        settings.key,
    )

    signal_map = (
        build_signal_map(
            signals
        )
    )

    feature_map = (
        build_feature_map(
            features
        )
    )

    rows = build_rows(
        signal_map,
        feature_map,
        outcomes,
    )

    print(
        "V7.4 signals:",
        len(
            signal_map
        ),
    )

    print(
        "Feature rows:",
        len(
            feature_map
        ),
    )

    print(
        "Matched forensic outcomes:",
        len(
            rows
        ),
    )

    for horizon in HORIZONS:
        print_candidates(
            rows,
            horizon,
        )

        compare_reversal_groups(
            rows,
            horizon,
        )

        compare_categorical(
            rows,
            horizon,
        )

    print()
    print(
        "V7.4 FORENSICS: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
