from __future__ import annotations

import hashlib
from typing import Any


PERSISTENCE_VERSION = "0.1"
ACTIVE_STATUSES = {"SHADOW_CANDIDATE", "WATCH"}


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _strategy_map(record: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(record, dict):
        return {}
    engine = record.get("multi_strategy_engine")
    if not isinstance(engine, dict):
        return {}
    rows = engine.get("strategies")
    if not isinstance(rows, list):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        strategy_id = str(row.get("strategy_id") or "")
        if strategy_id:
            output[strategy_id] = row
    return output


def make_strategy_instance_id(
    symbol: str,
    strategy_id: str,
    direction: str | None,
    first_seen_at_utc: str,
) -> str:
    raw = (
        f"{symbol.upper()}|{strategy_id.upper()}|"
        f"{str(direction or 'NONE').upper()}|{first_seen_at_utc}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def annotate_strategy_persistence(
    record: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    engine = record.get("multi_strategy_engine")
    if not isinstance(engine, dict):
        return {
            "version": PERSISTENCE_VERSION,
            "strategy_count": 0,
            "active_count": 0,
            "continuing_count": 0,
        }

    rows = engine.get("strategies")
    if not isinstance(rows, list):
        rows = []
    previous_by_id = _strategy_map(previous)
    observed_at = str(record.get("collected_at_utc") or "")
    symbol = str(record.get("symbol") or "")
    active_count = 0
    continuing_count = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        strategy_id = str(row.get("strategy_id") or "")
        current_status = str(row.get("status") or "")
        current_action = str(row.get("action") or "")
        current_direction = str(row.get("direction") or "").upper() or None
        current_active = current_status in ACTIVE_STATUSES

        prior = previous_by_id.get(strategy_id, {})
        previous_status = str(prior.get("status") or "") or None
        previous_action = str(prior.get("action") or "") or None
        previous_direction = str(prior.get("direction") or "").upper() or None
        previous_active = previous_status in ACTIVE_STATUSES
        previous_persistence = (
            prior.get("persistence")
            if isinstance(prior.get("persistence"), dict)
            else {}
        )

        same_direction = (
            current_direction is not None
            and current_direction == previous_direction
        )
        continuing = bool(
            current_active
            and previous_active
            and same_direction
        )

        if continuing:
            state = "CONTINUING"
            consecutive = int(previous_persistence.get("consecutive_scans") or 1) + 1
            first_seen = str(
                previous_persistence.get("first_seen_at_utc")
                or observed_at
            )
            continuing_count += 1
        elif current_active:
            state = "NEW" if not previous_active else "CHANGED"
            consecutive = 1
            first_seen = observed_at
        else:
            state = "INACTIVE"
            consecutive = 0
            first_seen = None

        if current_active:
            active_count += 1

        row["persistence"] = {
            "version": PERSISTENCE_VERSION,
            "state": state,
            "first_seen_at_utc": first_seen,
            "last_seen_at_utc": observed_at if current_active else None,
            "consecutive_scans": consecutive,
            "previous_status": previous_status,
            "previous_action": previous_action,
            "previous_direction": previous_direction,
            "status_changed": previous_status is not None and previous_status != current_status,
            "action_changed": previous_action is not None and previous_action != current_action,
            "direction_changed": previous_direction is not None and previous_direction != current_direction,
            "previous_signal_score": _float(prior.get("signal_score")),
            "previous_rr": _float(prior.get("rr")),
            "strategy_instance_id": (
                make_strategy_instance_id(
                    symbol,
                    strategy_id,
                    current_direction,
                    first_seen or observed_at,
                )
                if current_active
                else None
            ),
        }

    summary = {
        "version": PERSISTENCE_VERSION,
        "strategy_count": len([row for row in rows if isinstance(row, dict)]),
        "active_count": active_count,
        "continuing_count": continuing_count,
    }
    engine["persistence_summary"] = summary
    return summary
