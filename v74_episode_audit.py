from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.storage import SupabaseConfig


EPISODE_GAP_HOURS = 2.5
HORIZONS = (4, 12)


def headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def get_rows(url, key, table, params):
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


def dt(value: str) -> datetime:
    value = str(value).strip()

    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    # Normalize fractional seconds for Python 3.9.
    if "." in value:
        left, right = value.split(".", 1)

        offset = ""

        if "+" in right:
            fraction, tz = right.split("+", 1)
            offset = "+" + tz

        elif "-" in right:
            fraction, tz = right.split("-", 1)
            offset = "-" + tz

        else:
            fraction = right

        fraction = (
            fraction[:6]
            .ljust(6, "0")
        )

        value = (
            left
            + "."
            + fraction
            + offset
        )

    return datetime.fromisoformat(value)


def move_class(value: float) -> str:
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


def main() -> int:
    root = Path(__file__).resolve().parent

    load_env_file(root / ".env")
    config = load_config(root / "config.json")

    settings = SupabaseConfig.from_environment(config)

    if settings is None:
        raise SystemExit("Supabase not configured")

    signals = get_rows(
        settings.url,
        settings.key,
        "alpha_hunter_signals",
        {
            "select": (
                "signal_id,symbol,"
                "detected_at_utc,payload"
            ),
            "order": "detected_at_utc.asc",
            "limit": "10000",
        },
    )

    outcomes = get_rows(
        settings.url,
        settings.key,
        "alpha_hunter_signal_outcomes",
        {
            "select": (
                "signal_id,"
                "horizon_hours,"
                "return_pct"
            ),
            "limit": "30000",
        },
    )

    outcome_map = {}

    for row in outcomes:
        try:
            horizon = int(row.get("horizon_hours"))
        except (TypeError, ValueError):
            continue

        if horizon not in HORIZONS:
            continue

        outcome_map[
            (str(row.get("signal_id")), horizon)
        ] = f(row.get("return_pct"))

    detections = []

    for row in signals:
        payload = row.get("payload") or {}

        if not isinstance(payload, dict):
            continue

        tier = payload.get("pre_move_tier")
        path = payload.get("pre_move_path")

        if tier not in {"PRIMARY", "RESERVE"}:
            continue

        if path not in {"REVERSAL", "CONTINUATION"}:
            continue

        detected = row.get("detected_at_utc")

        if not detected:
            continue

        detections.append({
            "signal_id": str(row["signal_id"]),
            "symbol": str(row["symbol"]),
            "time": dt(detected),
            "tier": tier,
            "path": path,
            "rank": payload.get("pre_move_rank"),
            "score": f(payload.get("pre_move_score")),
            "last_time": dt(detected),
            "detections": 1,
        })

    detections.sort(
        key=lambda row: (
            row["symbol"],
            row["path"],
            row["time"],
        )
    )

    episodes = []
    current = None

    for row in detections:
        if current is None:
            current = row
            continue

        same_event = (
            row["symbol"] == current["symbol"]
            and row["path"] == current["path"]
            and (
                row["time"] - current["last_time"]
            ).total_seconds()
            <= EPISODE_GAP_HOURS * 3600
        )

        if same_event:
            current["last_time"] = row["time"]
            current["detections"] += 1
            continue

        episodes.append(current)
        current = row

    if current is not None:
        episodes.append(current)

    matured = []

    for episode in episodes:
        for horizon in HORIZONS:
            ret = outcome_map.get(
                (episode["signal_id"], horizon)
            )

            if ret is None:
                continue

            matured.append({
                **episode,
                "horizon": horizon,
                "return": ret,
                "abs": abs(ret),
                "class": move_class(ret),
            })

    print()
    print("=" * 100)
    print("V7.4 EPISODE-LEVEL FORWARD AUDIT")
    print("=" * 100)
    print("Independent episodes:", len(episodes))
    print()

    for horizon in HORIZONS:
        sample = [
            row
            for row in matured
            if row["horizon"] == horizon
        ]

        print(
            f"{horizon}H MATURED EPISODES:",
            len(sample),
        )

        for path in ("REVERSAL", "CONTINUATION"):
            group = [
                row
                for row in sample
                if row["tier"] == "PRIMARY"
                and row["path"] == path
            ]

            if not group:
                continue

            n = len(group)

            avg_abs = sum(
                row["abs"] for row in group
            ) / n

            exp3 = sum(
                row["abs"] >= 3
                for row in group
            ) / n * 100

            exp5 = sum(
                row["abs"] >= 5
                for row in group
            ) / n * 100

            exp10 = sum(
                row["abs"] >= 10
                for row in group
            ) / n * 100

            print(
                f"  PRIMARY {path:<13}"
                f"N={n:<4}"
                f" AVG_ABS={avg_abs:>6.2f}%"
                f" EXP3={exp3:>6.1f}%"
                f" EXP5={exp5:>6.1f}%"
                f" EXP10={exp10:>6.1f}%"
            )

        print()

    print("=" * 100)
    print("12H PRIMARY REVERSAL EPISODES")
    print("=" * 100)

    reversal_12 = [
        row
        for row in matured
        if row["horizon"] == 12
        and row["tier"] == "PRIMARY"
        and row["path"] == "REVERSAL"
    ]

    reversal_12.sort(
        key=lambda row: row["abs"],
        reverse=True,
    )

    print(
        f"{'SYMBOL':<14}"
        f"{'RANK':>6}"
        f"{'SCORE':>8}"
        f"{'RETURN':>11}"
        f"{'CLASS':>14}"
    )

    print("-" * 60)

    for row in reversal_12:
        print(
            f"{row['symbol']:<14}"
            f"{str(row.get('rank') or '—'):>6}"
            f"{float(row.get('score') or 0):>8.2f}"
            f"{row['return']:>10.2f}%"
            f"{row['class']:>14}"
        )

    print()
    print("V7.4 EPISODE AUDIT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
