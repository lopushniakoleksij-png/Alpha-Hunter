from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig


HORIZONS = (4, 12)


def headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def get_rows(
    url: str,
    key: str,
    table: str,
    params: dict[str, str],
) -> list[dict[str, Any]]:
    r = requests.get(
        f"{url}/rest/v1/{table}",
        params=params,
        headers=headers(key),
        timeout=30,
    )
    r.raise_for_status()

    data = r.json()
    return data if isinstance(data, list) else []


def f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_signals(url: str, key: str) -> list[dict[str, Any]]:
    return get_rows(
        url,
        key,
        "alpha_hunter_signals",
        {
            "select":
                "signal_id,symbol,detected_at_utc,payload",
            "order":
                "detected_at_utc.asc",
            "limit":
                "10000",
        },
    )


def load_outcomes(url: str, key: str) -> list[dict[str, Any]]:
    return get_rows(
        url,
        key,
        "alpha_hunter_signal_outcomes",
        {
            "select":
                "signal_id,horizon_hours,return_pct",
            "limit":
                "30000",
        },
    )


def metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {
            "n": 0,
            "avg_abs": 0.0,
            "exp3": 0.0,
            "exp5": 0.0,
            "exp10": 0.0,
        }

    values = [
        abs(float(row["return_pct"]))
        for row in rows
    ]

    n = len(values)

    return {
        "n": n,
        "avg_abs":
            sum(values) / n,
        "exp3":
            sum(v >= 3 for v in values) / n * 100,
        "exp5":
            sum(v >= 5 for v in values) / n * 100,
        "exp10":
            sum(v >= 10 for v in values) / n * 100,
    }


def print_metric(
    label: str,
    result: dict[str, float],
) -> None:
    print(
        f"{label:<18}"
        f"N={int(result['n']):<4}"
        f" AVG_ABS={result['avg_abs']:>6.2f}%"
        f" EXP3={result['exp3']:>6.1f}%"
        f" EXP5={result['exp5']:>6.1f}%"
        f" EXP10={result['exp10']:>6.1f}%"
    )


def main() -> int:
    root = Path(__file__).resolve().parent

    load_env_file(root / ".env")

    config = load_config(
        root / "config.json"
    )

    settings = SupabaseConfig.from_environment(
        config
    )

    if settings is None:
        raise SystemExit(
            "Supabase not configured"
        )

    signals = load_signals(
        settings.url,
        settings.key,
    )

    outcomes = load_outcomes(
        settings.url,
        settings.key,
    )

    outcome_map = {}

    for row in outcomes:
        try:
            horizon = int(
                row.get("horizon_hours")
            )
        except (TypeError, ValueError):
            continue

        if horizon not in HORIZONS:
            continue

        ret = f(
            row.get("return_pct")
        )

        if ret is None:
            continue

        outcome_map[
            (
                str(row.get("signal_id")),
                horizon,
            )
        ] = ret

    candidates = []

    for row in signals:
        payload = row.get("payload") or {}

        if not isinstance(
            payload,
            dict,
        ):
            continue

        if (
            payload.get("pre_move_path")
            != "REVERSAL"
        ):
            continue

        old_rank = payload.get(
            "pre_move_rank"
        )

        shadow_rank = payload.get(
            "v741_shadow_rank"
        )

        shadow_score = f(
            payload.get(
                "v741_shadow_score"
            )
        )

        # Historical rows before shadow deployment
        # are deliberately excluded.
        if shadow_rank is None:
            continue

        try:
            old_rank = int(old_rank)
        except (TypeError, ValueError):
            old_rank = None

        try:
            shadow_rank = int(shadow_rank)
        except (TypeError, ValueError):
            continue

        signal_id = str(
            row.get("signal_id")
            or ""
        )

        if not signal_id:
            continue

        for horizon in HORIZONS:
            ret = outcome_map.get(
                (
                    signal_id,
                    horizon,
                )
            )

            if ret is None:
                continue

            candidates.append({
                "signal_id":
                    signal_id,
                "symbol":
                    row.get("symbol"),
                "horizon":
                    horizon,
                "old_rank":
                    old_rank,
                "shadow_rank":
                    shadow_rank,
                "shadow_score":
                    shadow_score,
                "return_pct":
                    ret,
            })

    print()
    print("=" * 100)
    print("V7.4 vs V7.4.1 SHADOW — FORWARD COMPARISON")
    print("=" * 100)

    print(
        "Matched post-shadow outcomes:",
        len(candidates),
    )

    print()

    for horizon in HORIZONS:
        sample = [
            row
            for row in candidates
            if row["horizon"] == horizon
        ]

        print(
            f"{horizon}H"
        )
        print("-" * 100)

        old_top3 = [
            row
            for row in sample
            if (
                row["old_rank"] is not None
                and row["old_rank"] <= 3
            )
        ]

        shadow_top3 = [
            row
            for row in sample
            if row["shadow_rank"] <= 3
        ]

        old_top1 = [
            row
            for row in sample
            if row["old_rank"] == 1
        ]

        shadow_top1 = [
            row
            for row in sample
            if row["shadow_rank"] == 1
        ]

        print_metric(
            "V7.4 TOP3",
            metrics(old_top3),
        )

        print_metric(
            "SHADOW TOP3",
            metrics(shadow_top3),
        )

        print_metric(
            "V7.4 TOP1",
            metrics(old_top1),
        )

        print_metric(
            "SHADOW TOP1",
            metrics(shadow_top1),
        )

        print()

    print("=" * 100)
    print("SHADOW TOP3 INDIVIDUAL OUTCOMES")
    print("=" * 100)

    top = [
        row
        for row in candidates
        if row["shadow_rank"] <= 3
    ]

    top.sort(
        key=lambda row: (
            row["horizon"],
            -abs(row["return_pct"]),
        )
    )

    print(
        f"{'H':>3} "
        f"{'SYMBOL':<14} "
        f"{'OLD':>5} "
        f"{'SH':>4} "
        f"{'SH_SCORE':>9} "
        f"{'RETURN':>10}"
    )

    print("-" * 65)

    for row in top:
        print(
            f"{row['horizon']:>3} "
            f"{str(row['symbol']):<14} "
            f"{str(row['old_rank'] or '—'):>5} "
            f"{row['shadow_rank']:>4} "
            f"{float(row['shadow_score'] or 0):>9.2f} "
            f"{row['return_pct']:>9.2f}%"
        )

    print()
    print("V7.4.1 COMPARISON: PASS")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
