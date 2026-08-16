from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file


ROOT = Path(__file__).resolve().parent

STATE_PATH = (
    ROOT
    / "data"
    / "v75-lifecycle-episodes.json"
)

REPORT_PATH = (
    ROOT
    / "data"
    / "v75-lifecycle-performance.json"
)


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_episodes() -> list[dict[str, Any]]:
    if not STATE_PATH.exists():
        raise SystemExit(
            "V7.5 lifecycle state file not found"
        )

    raw = json.loads(
        STATE_PATH.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(raw, list):
        raise RuntimeError(
            "Lifecycle state must be a JSON list"
        )

    return [
        row
        for row in raw
        if isinstance(row, dict)
    ]


def age_hours(
    episode: dict[str, Any],
) -> float | None:

    first = parse_time(
        episode.get(
            "first_detected_at_utc"
        )
    )

    last = parse_time(
        episode.get(
            "last_detected_at_utc"
        )
    )

    if first is None or last is None:
        return None

    return (
        last - first
    ).total_seconds() / 3600.0


def classify(
    episode: dict[str, Any],
) -> str:

    exp3 = bool(
        episode.get(
            "expansion_3_hit"
        )
    )

    exp5 = bool(
        episode.get(
            "expansion_5_hit"
        )
    )

    exp10 = bool(
        episode.get(
            "expansion_10_hit"
        )
    )

    trade_ready = bool(
        episode.get(
            "v7_trade_ready"
        )
    )

    permission = bool(
        episode.get(
            "trade_permission"
        )
    )

    state = str(
        episode.get(
            "lifecycle_state"
        )
        or ""
    )

    if exp10:
        if trade_ready or permission:
            return "SUCCESSFUL_MAJOR_EXPANSION"

        return "MISSED_MAJOR_EXPANSION"

    if exp5:
        if trade_ready or permission:
            return "SUCCESSFUL_EXPANSION"

        return "EARLY_DETECTION_NO_EXECUTION"

    if exp3:
        return "EARLY_EXPANSION"

    if state == "FAILED":
        return "FALSE_POSITIVE"

    if state == "EXTENDED":
        return "LATE_DETECTION"

    return "ACTIVE"


def time_to_hit(
    episode: dict[str, Any],
    field: str,
) -> float | None:

    first = parse_time(
        episode.get(
            "first_detected_at_utc"
        )
    )

    hit = parse_time(
        episode.get(field)
    )

    if first is None or hit is None:
        return None

    return (
        hit - first
    ).total_seconds() / 3600.0


def pct(
    count: int,
    total: int,
) -> float:

    if total <= 0:
        return 0.0

    return count / total * 100.0


def main() -> int:

    load_env_file(
        ROOT / ".env"
    )

    # Validate production config is readable.
    load_config(
        ROOT / "config.json"
    )

    episodes = load_episodes()

    evaluated = []

    for episode in episodes:

        first_price = number(
            episode.get(
                "first_detection_price"
            )
        )

        latest_price = number(
            episode.get(
                "latest_price"
            )
        )

        raw_return = None

        if (
            first_price is not None
            and latest_price is not None
            and first_price != 0
        ):
            raw_return = (
                latest_price
                / first_price
                - 1.0
            ) * 100.0

        row = dict(episode)

        row[
            "episode_age_hours"
        ] = age_hours(
            episode
        )

        row[
            "raw_return_pct"
        ] = raw_return

        row[
            "time_to_3pct_hours"
        ] = time_to_hit(
            episode,
            "first_3pct_at_utc",
        )

        row[
            "time_to_5pct_hours"
        ] = time_to_hit(
            episode,
            "first_5pct_at_utc",
        )

        row[
            "time_to_10pct_hours"
        ] = time_to_hit(
            episode,
            "first_10pct_at_utc",
        )

        row[
            "performance_class"
        ] = classify(
            episode
        )

        evaluated.append(
            row
        )

    total = len(evaluated)

    hit3 = sum(
        bool(
            row.get(
                "expansion_3_hit"
            )
        )
        for row in evaluated
    )

    hit5 = sum(
        bool(
            row.get(
                "expansion_5_hit"
            )
        )
        for row in evaluated
    )

    hit10 = sum(
        bool(
            row.get(
                "expansion_10_hit"
            )
        )
        for row in evaluated
    )

    trade_ready = sum(
        bool(
            row.get(
                "v7_trade_ready"
            )
        )
        for row in evaluated
    )

    permissions = sum(
        bool(
            row.get(
                "trade_permission"
            )
        )
        for row in evaluated
    )

    classes: dict[str, int] = {}

    for row in evaluated:
        name = str(
            row[
                "performance_class"
            ]
        )

        classes[name] = (
            classes.get(
                name,
                0,
            )
            + 1
        )

    report = {
        "generated_at_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "episodes":
            evaluated,

        "summary": {
            "episodes":
                total,

            "expansion_3":
                hit3,

            "expansion_5":
                hit5,

            "expansion_10":
                hit10,

            "expansion_3_pct":
                pct(
                    hit3,
                    total,
                ),

            "expansion_5_pct":
                pct(
                    hit5,
                    total,
                ),

            "expansion_10_pct":
                pct(
                    hit10,
                    total,
                ),

            "trade_ready":
                trade_ready,

            "trade_permission":
                permissions,

            "classes":
                classes,
        },
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print(
        "=" * 110
    )

    print(
        "ALPHA HUNTER V7.5 "
        "LIFECYCLE PERFORMANCE"
    )

    print(
        "=" * 110
    )

    print(
        "Episodes:",
        total,
    )

    print()

    print(
        "EXPANSION RESULTS"
    )

    print(
        f"3%  {hit3:>4}/{total:<4} "
        f"{pct(hit3, total):>6.1f}%"
    )

    print(
        f"5%  {hit5:>4}/{total:<4} "
        f"{pct(hit5, total):>6.1f}%"
    )

    print(
        f"10% {hit10:>4}/{total:<4} "
        f"{pct(hit10, total):>6.1f}%"
    )

    print()

    print(
        "EXECUTION RESULTS"
    )

    print(
        "Trade ready:",
        trade_ready,
    )

    print(
        "Trade permission:",
        permissions,
    )

    print()

    print(
        "CLASSIFICATIONS"
    )

    for name in sorted(classes):
        print(
            f"{name:<32}"
            f"{classes[name]:>5}"
        )

    print()

    print(
        "=" * 110
    )

    print(
        "EPISODE DETAIL"
    )

    print(
        "=" * 110
    )

    print(
        f"{'SYMBOL':<14}"
        f"{'PATH':<14}"
        f"{'DET':>5}"
        f"{'MFE':>9}"
        f"{'MAE':>9}"
        f"{'3%':>6}"
        f"{'5%':>6}"
        f"{'10%':>6} "
        f"{'CLASS'}"
    )

    print(
        "-" * 110
    )

    evaluated.sort(
        key=lambda row:
            abs(
                number(
                    row.get(
                        "max_favorable_excursion_pct"
                    )
                )
                or 0.0
            ),
        reverse=True,
    )

    for row in evaluated:

        mfe = (
            number(
                row.get(
                    "max_favorable_excursion_pct"
                )
            )
            or 0.0
        )

        mae = (
            number(
                row.get(
                    "max_adverse_excursion_pct"
                )
            )
            or 0.0
        )

        print(
            f"{str(row.get('symbol') or ''):<14}"
            f"{str(row.get('path') or ''):<14}"
            f"{int(row.get('detections') or 0):>5}"
            f"{mfe:>8.2f}%"
            f"{mae:>8.2f}%"
            f"{('Y' if row.get('expansion_3_hit') else '-'):>6}"
            f"{('Y' if row.get('expansion_5_hit') else '-'):>6}"
            f"{('Y' if row.get('expansion_10_hit') else '-'):>6} "
            f"{row['performance_class']}"
        )

    print()

    print(
        "Report:",
        REPORT_PATH,
    )

    print()

    print(
        "V7.5 LIFECYCLE PERFORMANCE: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
