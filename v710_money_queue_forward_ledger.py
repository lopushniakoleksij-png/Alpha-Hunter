from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from v710_money_queue_shadow import (
    generate_money_queue,
)


ROOT = Path(__file__).resolve().parent

LEDGER_PATH = (
    ROOT
    / "data"
    / "money-queue"
    / "forward-ledger.jsonl"
)

MODEL_VERSION = (
    "7.10-money-queue-forward-v1"
)


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def load_json(
    path: Path,
) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            f"{path} must contain an object"
        )

    return payload


def production_run_id_from_env(
) -> str | None:
    value = str(
        os.environ.get(
            "ALPHA_HUNTER_PRODUCTION_RUN_ID",
            ""
        )
        or ""
    ).strip()

    return value or None


def snapshot_run_id(
    snapshot: dict[str, Any],
) -> str | None:
    value = str(
        snapshot.get(
            "production_run_id"
        )
        or ""
    ).strip()

    return value or None


def observation_id(
    production_run_id: str,
    candidate: dict[str, Any],
) -> str:
    raw = "|".join([
        production_run_id,
        str(
            candidate.get(
                "symbol"
            )
            or ""
        ),
        str(
            candidate.get(
                "direction"
            )
            or ""
        ),
        str(
            candidate.get(
                "required_entry"
            )
        ),
        str(
            candidate.get(
                "stop"
            )
        ),
        str(
            candidate.get(
                "stop_timeframe"
            )
        ),
        str(
            candidate.get(
                "target"
            )
        ),
        str(
            candidate.get(
                "target_timeframe"
            )
        ),
        MODEL_VERSION,
    ]).encode(
        "utf-8"
    )

    return hashlib.sha256(
        raw
    ).hexdigest()[:32]


def build_ledger_row(
    candidate: dict[str, Any],
    production_run_id: str,
    snapshot_at_utc: str,
    *,
    captured_at_utc: str | None = None,
) -> dict[str, Any]:
    captured_at_utc = (
        captured_at_utc
        or utc_now().isoformat()
    )

    return {
        "observation_id":
            observation_id(
                production_run_id,
                candidate,
            ),

        "model_version":
            MODEL_VERSION,

        "production_run_id":
            production_run_id,

        "snapshot_at_utc":
            snapshot_at_utc,

        "captured_at_utc":
            captured_at_utc,

        "symbol":
            candidate.get(
                "symbol"
            ),

        "direction":
            candidate.get(
                "direction"
            ),

        "current_price":
            candidate.get(
                "current_price"
            ),

        "current_rr":
            candidate.get(
                "current_rr"
            ),

        "required_entry":
            candidate.get(
                "required_entry"
            ),

        "distance_from_current_pct":
            candidate.get(
                "distance_from_current_pct"
            ),

        "price_ready":
            bool(
                candidate.get(
                    "price_ready"
                )
            ),

        "stop":
            candidate.get(
                "stop"
            ),

        "stop_timeframe":
            candidate.get(
                "stop_timeframe"
            ),

        "target":
            candidate.get(
                "target"
            ),

        "target_timeframe":
            candidate.get(
                "target_timeframe"
            ),

        "planned_rr":
            candidate.get(
                "planned_rr"
            ),

        "planned_risk_pct":
            candidate.get(
                "planned_risk_pct"
            ),

        "planned_atr_x":
            candidate.get(
                "planned_atr_x"
            ),

        "market_phase":
            candidate.get(
                "market_phase"
            ),

        "opportunity_timing":
            candidate.get(
                "opportunity_timing"
            ),

        "behaviour_score":
            candidate.get(
                "behaviour_score"
            ),

        "missing_non_rr_checks":
            list(
                candidate.get(
                    "missing_non_rr_checks",
                    [],
                )
                or []
            ),

        "production_blockers":
            list(
                candidate.get(
                    "production_blockers",
                    [],
                )
                or []
            ),

        "production_trade_permission":
            bool(
                candidate.get(
                    "production_trade_permission"
                )
            ),

        "production_v7_trade_ready":
            bool(
                candidate.get(
                    "production_v7_trade_ready"
                )
            ),

        # Permanent research quarantine.
        "shadow_trade_permission":
            False,

        "shadow_only":
            True,

        # Outcome fields remain unknown
        # at capture time.
        "entry_touched_later":
            None,

        "entry_touch_at_utc":
            None,

        "confirmation_after_touch":
            None,

        "stop_hit_after_touch":
            None,

        "target_hit_after_touch":
            None,

        "mfe_r":
            None,

        "mae_r":
            None,

        "outcome":
            "PENDING",
    }


def read_existing_ids(
    path: Path,
) -> set[str]:
    if not path.exists():
        return set()

    ids: set[str] = set()

    for line in path.read_text(
        encoding="utf-8"
    ).splitlines():

        if not line.strip():
            continue

        try:
            row = json.loads(
                line
            )
        except json.JSONDecodeError:
            continue

        if not isinstance(
            row,
            dict,
        ):
            continue

        value = str(
            row.get(
                "observation_id"
            )
            or ""
        ).strip()

        if value:
            ids.add(value)

    return ids


def append_rows(
    path: Path,
    rows: list[dict[str, Any]],
) -> int:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing = read_existing_ids(
        path
    )

    new_rows = [
        row
        for row in rows
        if row[
            "observation_id"
        ] not in existing
    ]

    if not new_rows:
        return 0

    with path.open(
        "a",
        encoding="utf-8",
    ) as handle:

        for row in new_rows:
            handle.write(
                json.dumps(
                    row,
                    sort_keys=True,
                    separators=(
                        ",",
                        ":",
                    ),
                )
            )

            handle.write(
                "\n"
            )

    return len(
        new_rows
    )


def capture(
    snapshot: dict[str, Any],
    config: dict[str, Any],
    production_run_id: str,
) -> list[dict[str, Any]]:
    actual_run_id = (
        snapshot_run_id(
            snapshot
        )
    )

    if actual_run_id != production_run_id:
        raise ValueError(
            "snapshot production_run_id "
            "does not match requested run: "
            f"snapshot={actual_run_id!r} "
            f"requested={production_run_id!r}"
        )

    snapshot_at = str(
        snapshot.get(
            "collected_at_utc"
        )
        or ""
    ).strip()

    if not snapshot_at:
        raise ValueError(
            "snapshot collected_at_utc "
            "is required"
        )

    queue = generate_money_queue(
        snapshot,
        config,
    )

    return [
        build_ledger_row(
            candidate,
            production_run_id,
            snapshot_at,
        )
        for candidate
        in queue
    ]


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

    requested_run_id = (
        production_run_id_from_env()
    )

    actual_run_id = (
        snapshot_run_id(
            snapshot
        )
    )

    # Manual research runs are allowed,
    # but still bind explicitly to the
    # snapshot's own production ID.
    production_run_id = (
        requested_run_id
        or actual_run_id
    )

    if not production_run_id:
        raise SystemExit(
            "No production_run_id "
            "available in environment "
            "or snapshot"
        )

    rows = capture(
        snapshot,
        config,
        production_run_id,
    )

    added = append_rows(
        LEDGER_PATH,
        rows,
    )

    print(
        "MONEY QUEUE FORWARD LEDGER V1"
    )

    print(
        "Production run:",
        production_run_id,
    )

    print(
        "Snapshot:",
        snapshot.get(
            "collected_at_utc"
        ),
    )

    print(
        "Queue observations:",
        len(rows),
    )

    print(
        "New rows appended:",
        added,
    )

    print(
        "Ledger:",
        LEDGER_PATH,
    )

    print(
        "Shadow trade permission: FALSE"
    )

    print(
        "Production changed: NO"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
