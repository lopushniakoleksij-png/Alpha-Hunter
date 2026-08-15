from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha_hunter.collector import load_config
from alpha_hunter.env import load_env_file
from alpha_hunter.lifecycle import LifecycleEpisode
from alpha_hunter.storage import SupabaseConfig
from v75_lifecycle_job import (
    load_state,
    load_supabase_state,
    save_state,
    upsert_supabase,
)

ROOT = Path(__file__).resolve().parent
FINALIZATION_HOURS = 24.0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip()

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            result = datetime.fromisoformat(text)
        except ValueError:
            return None

    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)

    return result.astimezone(timezone.utc)


def episode_age_hours(
    episode: LifecycleEpisode,
    current_time: datetime,
) -> float | None:
    first = dt(
        episode.first_detected_at_utc
    )

    if first is None:
        return None

    return (
        current_time - first
    ).total_seconds() / 3600.0


def dominant_direction(
    episode: LifecycleEpisode,
) -> str | None:
    up = max(
        0.0,
        float(
            episode.max_up_excursion_pct
            or 0.0
        ),
    )

    down = abs(
        min(
            0.0,
            float(
                episode.max_down_excursion_pct
                or 0.0
            ),
        )
    )

    if (
        up < 3.0
        and down < 3.0
    ):
        return None

    if up >= down:
        return "UP"

    return "DOWN"


def classify_ground_truth(
    episode: LifecycleEpisode,
) -> str:
    direction = dominant_direction(
        episode
    )

    up = max(
        0.0,
        float(
            episode.max_up_excursion_pct
            or 0.0
        ),
    )

    down = abs(
        min(
            0.0,
            float(
                episode.max_down_excursion_pct
                or 0.0
            ),
        )
    )

    magnitude = max(
        up,
        down,
    )

    if direction is None:
        return "NO_EXPANSION"

    if magnitude >= 10.0:
        return (
            f"HUGE_EXPANSION_{direction}"
        )

    if magnitude >= 5.0:
        return (
            f"MAJOR_EXPANSION_{direction}"
        )

    if magnitude >= 3.0:
        return (
            f"GOOD_DETECTION_{direction}"
        )

    return "NO_EXPANSION"


def finalization_ready(
    episode: LifecycleEpisode,
    current_time: datetime,
) -> bool:
    if episode.is_finalized:
        return False

    age = episode_age_hours(
        episode,
        current_time,
    )

    if age is None:
        return False

    if age < FINALIZATION_HOURS:
        return False

    if (
        episode.measurement_quality
        != "FORWARD_COMPLETE"
    ):
        return False

    return True


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

    episodes = load_state()

    if not episodes:
        episodes = load_supabase_state(
            settings
        )

    now = now_utc()

    finalized = 0
    waiting = 0
    legacy = 0
    already_finalized = 0

    print()
    print("=" * 110)
    print(
        "ALPHA HUNTER V7.5 "
        "24H EPISODE FINALIZER"
    )
    print("=" * 110)

    for episode in episodes:
        age = episode_age_hours(
            episode,
            now,
        )

        if episode.is_finalized:
            already_finalized += 1
            continue

        if (
            episode.measurement_quality
            != "FORWARD_COMPLETE"
        ):
            legacy += 1

            print(
                f"SKIP   "
                f"{episode.symbol:<15}"
                f"quality="
                f"{episode.measurement_quality or 'UNKNOWN':<18}"
                f"age="
                f"{age if age is not None else 0:>7.2f}H"
            )

            continue

        if not finalization_ready(
            episode,
            now,
        ):
            waiting += 1

            print(
                f"WAIT   "
                f"{episode.symbol:<15}"
                f"age="
                f"{age if age is not None else 0:>7.2f}H "
                f"UP="
                f"{episode.max_up_excursion_pct:>8.2f}% "
                f"DOWN="
                f"{episode.max_down_excursion_pct:>8.2f}%"
            )

            continue

        final_direction = (
            dominant_direction(
                episode
            )
        )

        classification = (
            classify_ground_truth(
                episode
            )
        )

        episode.expansion_direction = (
            final_direction
        )

        episode.final_classification = (
            classification
        )

        episode.finalized_at_utc = (
            now.isoformat()
        )

        episode.is_finalized = True

        episode.previous_state = (
            episode.lifecycle_state
        )

        episode.lifecycle_state = (
            "FINALIZED"
        )

        finalized += 1

        print(
            f"FINAL  "
            f"{episode.symbol:<15}"
            f"direction="
            f"{str(final_direction or 'NONE'):<5} "
            f"UP="
            f"{episode.max_up_excursion_pct:>8.2f}% "
            f"DOWN="
            f"{episode.max_down_excursion_pct:>8.2f}% "
            f"class="
            f"{classification}"
        )

    save_state(
        episodes
    )

    saved = upsert_supabase(
        episodes,
        settings,
    )

    print()
    print("=" * 110)
    print("FINALIZER SUMMARY")
    print("=" * 110)

    print(
        "Episodes:",
        len(episodes),
    )

    print(
        "Finalized this run:",
        finalized,
    )

    print(
        "Waiting for 24H:",
        waiting,
    )

    print(
        "Legacy partial skipped:",
        legacy,
    )

    print(
        "Already finalized:",
        already_finalized,
    )

    print(
        "Supabase rows upserted:",
        saved,
    )

    print()
    print(
        "V7.5 EPISODE FINALIZER: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
