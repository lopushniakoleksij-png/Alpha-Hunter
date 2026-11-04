"""Offline, read-only UTC cadence check for the Alpha Hunter big-mover freshness gate.

The model may be retrained every six hours, but an hourly downstream stage
requires evidence no older than 90 minutes. This utility demonstrates whether
the configured schedules can ever satisfy that contract, without connecting to
a database, reading secrets, changing cron jobs, or granting trade permission.

Only minute/hour daily UTC cron expressions are supported. All calendar fields
must be '*'; unsupported schedules fail rather than being silently misread.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timedelta, timezone


def _expand_utc_field(expression: str, *, maximum: int) -> tuple[int, ...]:
    values: set[int] = set()
    for item in expression.split(","):
        item = item.strip()
        if not item:
            raise ValueError("empty cron field item")
        if "/" in item:
            base, step_text = item.split("/", 1)
            if not step_text.isdecimal() or int(step_text) < 1:
                raise ValueError("invalid cron step")
            step = int(step_text)
        else:
            base, step = item, 1

        if base == "*":
            start, stop = 0, maximum
        elif "-" in base:
            lower, upper = base.split("-", 1)
            if not lower.isdecimal() or not upper.isdecimal():
                raise ValueError("invalid cron range")
            start, stop = int(lower), int(upper)
        elif base.isdecimal():
            start = int(base)
            stop = maximum if "/" in item else start
        else:
            raise ValueError(f"unsupported cron field item: {item!r}")

        if start < 0 or stop > maximum or start > stop:
            raise ValueError("cron field out of range")
        values.update(range(start, stop + 1, step))
    if not values:
        raise ValueError("cron field selects no times")
    return tuple(sorted(values))


def daily_utc_schedule(expression: str) -> tuple[tuple[int, int], ...]:
    """Return (hour, minute) UTC schedule, rejecting non-daily calendars."""
    fields = expression.strip().split()
    if len(fields) != 5 or fields[2:] != ["*", "*", "*"]:
        raise ValueError("only daily UTC 5-field cron expressions are supported")
    minutes = _expand_utc_field(fields[0], maximum=59)
    hours = _expand_utc_field(fields[1], maximum=23)
    return tuple((hour, minute) for hour in hours for minute in minutes)


def audit_cadence(
    *,
    producer_cron: str,
    consumer_cron: str,
    max_age_minutes: float,
    day_utc: date,
    producer_runtime_minutes: float = 0.0,
    source_timestamp_lag_minutes: float = 0.0,
) -> dict:
    """Model whether every downstream stage can consume eligible fresh evidence.

    Source timestamp lag is the observed age of the source data when its model
    job starts. The model is not considered available until its runtime elapses.
    No estimates are represented as observed uptime or scientific validation.
    """
    if not (0 < max_age_minutes <= 1440):
        raise ValueError("maximum evidence age must be within (0, 1440]")
    if not (0 <= producer_runtime_minutes < 1440):
        raise ValueError("producer runtime must be within [0, 1440)")
    if not (0 <= source_timestamp_lag_minutes < 1440):
        raise ValueError("source timestamp lag must be within [0, 1440)")

    source_times = daily_utc_schedule(producer_cron)
    consumer_times = daily_utc_schedule(consumer_cron)
    midnight = datetime.combine(day_utc, time(), tzinfo=timezone.utc)
    producer_events = []
    for day_offset in (-2, -1, 0):
        for hour, minute in source_times:
            started = midnight + timedelta(days=day_offset, hours=hour, minutes=minute)
            producer_events.append((
                started + timedelta(minutes=producer_runtime_minutes),
                started - timedelta(minutes=source_timestamp_lag_minutes),
            ))
    producer_events.sort()
    rows = []
    for hour, minute in consumer_times:
        checked_at = midnight + timedelta(hours=hour, minutes=minute)
        eligible = [event for event in producer_events if event[0] <= checked_at]
        if not eligible:
            status = "UNAVAILABLE"
            age_minutes = None
        else:
            completed_at, source_at = eligible[-1]
            age_minutes = round((checked_at - source_at).total_seconds() / 60, 3)
            status = "FRESH" if 0 <= age_minutes <= max_age_minutes else "STALE"
        rows.append({
            "consumer_hour_utc": hour,
            "consumer_time_utc": checked_at.isoformat(),
            "status": status,
            "source_age_minutes": age_minutes,
        })

    fresh = sum(row["status"] == "FRESH" for row in rows)
    return {
        "kind": "SCHEDULE_ONLY_SIMULATION_NOT_LIVE_DATA",
        "date_utc": day_utc.isoformat(),
        "producer_cron": producer_cron,
        "consumer_cron": consumer_cron,
        "max_age_minutes": max_age_minutes,
        "producer_runtime_minutes_assumed": producer_runtime_minutes,
        "source_timestamp_lag_minutes_assumed": source_timestamp_lag_minutes,
        "stage_runs": len(rows),
        "fresh_stage_runs": fresh,
        "blocked_stage_runs": len(rows) - fresh,
        "schedule_contract_pass": fresh == len(rows),
        "blocked_stage_hours_utc": [row["consumer_hour_utc"] for row in rows if row["status"] != "FRESH"],
        "trade_permission": False,
        "production_change_permitted": False,
        "hours": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer-cron", required=True)
    parser.add_argument("--consumer-cron", required=True)
    parser.add_argument("--max-age-minutes", type=float, required=True)
    parser.add_argument("--day-utc", required=True, help="YYYY-MM-DD")
    parser.add_argument("--producer-runtime-minutes", type=float, default=0.0)
    parser.add_argument("--source-timestamp-lag-minutes", type=float, default=0.0)
    parser.add_argument(
        "--require-complete-freshness",
        action="store_true",
        help="Exit non-zero if even one modeled stage would consume stale evidence.",
    )
    args = parser.parse_args()
    result = audit_cadence(
        producer_cron=args.producer_cron,
        consumer_cron=args.consumer_cron,
        max_age_minutes=args.max_age_minutes,
        day_utc=date.fromisoformat(args.day_utc),
        producer_runtime_minutes=args.producer_runtime_minutes,
        source_timestamp_lag_minutes=args.source_timestamp_lag_minutes,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 2 if args.require_complete_freshness and not result["schedule_contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
