from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alpha_hunter.collector import (
    load_config,
    load_previous_snapshot,
)
from alpha_hunter.lifecycle import (
    LifecycleEpisode,
    classify_episode,
    create_episode,
    same_episode,
    update_episode,
)
from alpha_hunter.env import load_env_file
from v741_shadow import apply_shadow_scores


ROOT = Path(__file__).resolve().parent

STATE_PATH = (
    ROOT
    / "data"
    / "v75-lifecycle-episodes.json"
)

HISTORY_PATH = (
    ROOT
    / "data"
    / "v75-lifecycle-history.jsonl"
)


def now_utc() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def snapshot_time(
    snapshot: dict[str, Any],
) -> str:
    for key in (
        "collected_at_utc",
        "generated_at_utc",
        "detected_at_utc",
        "timestamp_utc",
        "created_at_utc",
    ):
        value = snapshot.get(
            key
        )

        if value:
            return str(
                value
            )

    return now_utc()


def load_state() -> list[LifecycleEpisode]:
    if not STATE_PATH.exists():
        return []

    raw = json.loads(
        STATE_PATH.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        raw,
        list,
    ):
        raise RuntimeError(
            "V7.5 lifecycle state "
            "must be a JSON list"
        )

    episodes = []

    for item in raw:
        if not isinstance(
            item,
            dict,
        ):
            continue

        episodes.append(
            LifecycleEpisode(
                **item
            )
        )

    return episodes


def save_state(
    episodes: list[
        LifecycleEpisode
    ],
) -> None:
    STATE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path = (
        STATE_PATH
        .with_suffix(
            ".json.tmp"
        )
    )

    payload = [
        episode.to_dict()
        for episode in episodes
    ]

    temp_path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temp_path.replace(
        STATE_PATH
    )


def append_history(
    event: dict[str, Any],
) -> None:
    HISTORY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with HISTORY_PATH.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(
            json.dumps(
                event,
                separators=(
                    ",",
                    ":",
                ),
            )
            + "\n"
        )


def prepare_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    row = dict(
        record
    )

    # Normalize nested pre_move payload
    # into top-level lifecycle fields.
    pre_move = (
        row.get(
            "pre_move"
        )
        or {}
    )

    if isinstance(
        pre_move,
        dict,
    ):
        row.setdefault(
            "pre_move_path",
            pre_move.get(
                "path"
            ),
        )

        row.setdefault(
            "pre_move_state",
            pre_move.get(
                "state"
            ),
        )

        row.setdefault(
            "pre_move_score",
            pre_move.get(
                "score"
            ),
        )

        row.setdefault(
            "pre_move_rank",
            pre_move.get(
                "rank"
            ),
        )

        row.setdefault(
            "pre_move_tier",
            pre_move.get(
                "tier"
            ),
        )

    return row


def active_episode_for(
    episodes: list[
        LifecycleEpisode
    ],
    record: dict[str, Any],
    detected_at_utc: str,
) -> LifecycleEpisode | None:
    symbol = str(
        record.get(
            "symbol"
        )
        or ""
    )

    path = str(
        record.get(
            "pre_move_path"
        )
        or ""
    )

    matches = [
        episode
        for episode in episodes
        if same_episode(
            episode,
            symbol,
            path,
            detected_at_utc,
        )
    ]

    if not matches:
        return None

    matches.sort(
        key=lambda episode:
            episode.last_detected_at_utc,
        reverse=True,
    )

    return matches[0]


def lifecycle_candidates(
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    symbols = (
        snapshot.get(
            "symbols"
        )
        or []
    )

    if not isinstance(
        symbols,
        list,
    ):
        return []

    # Recalculate shadow metadata locally.
    # This is deterministic and still SHADOW ONLY.
    apply_shadow_scores(
        symbols
    )

    candidates = []

    for raw in symbols:
        if not isinstance(
            raw,
            dict,
        ):
            continue

        row = prepare_record(
            raw
        )

        path = row.get(
            "pre_move_path"
        )

        tier = row.get(
            "pre_move_tier"
        )

        if path not in {
            "REVERSAL",
            "CONTINUATION",
        }:
            continue

        if tier not in {
            "PRIMARY",
            "RESERVE",
        }:
            continue

        candidates.append(
            row
        )

    return candidates


def main() -> int:
    load_env_file(
        ROOT
        / ".env"
    )

    config = load_config(
        ROOT
        / "config.json"
    )

    snapshot = (
        load_previous_snapshot(
            ROOT
            / "config.json",
            config,
        )
    )

    if not snapshot:
        raise SystemExit(
            "No latest Alpha Hunter "
            "snapshot found"
        )

    detected_at = (
        snapshot_time(
            snapshot
        )
    )

    run_id = str(
        snapshot.get(
            "run_id"
        )
        or ""
    )

    episodes = load_state()

    candidates = (
        lifecycle_candidates(
            snapshot
        )
    )

    created = 0
    updated = 0

    print()
    print(
        "ALPHA HUNTER V7.5 "
        "OPPORTUNITY LIFECYCLE"
    )

    print(
        "Run ID:",
        run_id or "N/A",
    )

    print(
        "Timestamp:",
        detected_at,
    )

    print(
        "Lifecycle candidates:",
        len(
            candidates
        ),
    )

    print()

    for record in candidates:
        existing = (
            active_episode_for(
                episodes,
                record,
                detected_at,
            )
        )

        if existing is None:
            episode = (
                create_episode(
                    record,
                    detected_at,
                )
            )

            episodes.append(
                episode
            )

            created += 1

            append_history({
                "event":
                    "EPISODE_CREATED",

                "run_id":
                    run_id,

                "event_at_utc":
                    detected_at,

                "episode":
                    episode.to_dict(),
            })

            action = "NEW"

        else:
            before_state = (
                existing.lifecycle_state
            )

            before_detections = (
                existing.detections
            )

            update_episode(
                existing,
                record,
                detected_at,
            )

            updated += 1

            append_history({
                "event":
                    "EPISODE_UPDATED",

                "run_id":
                    run_id,

                "event_at_utc":
                    detected_at,

                "episode_id":
                    existing.episode_id,

                "symbol":
                    existing.symbol,

                "path":
                    existing.path,

                "state_before":
                    before_state,

                "state_after":
                    existing.lifecycle_state,

                "detections_before":
                    before_detections,

                "detections_after":
                    existing.detections,

                "episode":
                    existing.to_dict(),
            })

            episode = existing
            action = "UPDATE"

        episode.final_classification = (
            classify_episode(
                episode
            )
        )

        print(
            f"{action:<6} "
            f"{episode.symbol:<14} "
            f"{episode.path:<13} "
            f"state="
            f"{episode.lifecycle_state:<20} "
            f"det={episode.detections:<3} "
            f"v74="
            f"{episode.v74_score or 0:>5.2f} "
            f"rank="
            f"{episode.v74_rank or '—'} "
            f"shadow="
            f"{episode.v741_shadow_score or 0:>5.2f} "
            f"class="
            f"{episode.final_classification}"
        )

    save_state(
        episodes
    )

    print()
    print(
        "=" * 100
    )

    print(
        "V7.5 LIFECYCLE SUMMARY"
    )

    print(
        "=" * 100
    )

    print(
        "Episodes stored:",
        len(
            episodes
        ),
    )

    print(
        "Created this run:",
        created,
    )

    print(
        "Updated this run:",
        updated,
    )

    active = [
        episode
        for episode in episodes
        if episode.lifecycle_state
        not in {
            "FAILED",
            "EXTENDED",
        }
    ]

    print(
        "Active episodes:",
        len(
            active
        ),
    )

    by_state: dict[
        str,
        int,
    ] = {}

    for episode in episodes:
        state = (
            episode.lifecycle_state
        )

        by_state[
            state
        ] = (
            by_state.get(
                state,
                0,
            )
            + 1
        )

    print()

    print(
        "STATE COUNTS"
    )

    for state in sorted(
        by_state
    ):
        print(
            f"{state:<24}",
            by_state[
                state
            ],
        )

    print()

    print(
        "State file:",
        STATE_PATH,
    )

    print(
        "History file:",
        HISTORY_PATH,
    )

    print()

    print(
        "V7.5 LIFECYCLE JOB: PASS"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
