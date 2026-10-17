"""Research-only capacity scenarios for unchanged 40-set P2 geometry evaluator.

The script never updates cron, replays, reads sealed outcomes, requests a venue,
or asserts scientific or DBA approval. Numbers are *planning scenarios* only:
HTTP durability, throughput yield and archival access require independent tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from typing import Any, Mapping

SPEC = "AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01"
END_UTC = "2026-11-19T00:29:06.132018Z"
PER_RUN_FROZEN = 40
HORIZONS = 2
DAYS_PER_WEEK = Decimal(7)
SECONDS_PER_DAY = Decimal(86400)


def _utc(iso: str) -> datetime:
    if not isinstance(iso, str):
        raise ValueError("AWARE_UTC_TIMESTAMP_REQUIRED")
    try:
        x = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("AWARE_UTC_TIMESTAMP_REQUIRED") from None
    if x.tzinfo is None or x.utcoffset() is None:
        raise ValueError("AWARE_UTC_TIMESTAMP_REQUIRED")
    return x.astimezone(timezone.utc)


def _natural(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("NONNEGATIVE_INTEGER_REQUIRED_" + field)
    return value


def scenario(*, verified_at_utc: str, end_utc: str, spec_id: str,
             due_sets: int, complete_sets: int, eligible_added_last_7d: int,
             hours_between_runs: int, success_fraction: str,
             max_sets_per_run: int = PER_RUN_FROZEN) -> dict:
    out = dict(
        status="METADATA_NOT_VALIDATED",
        advisory_only=True,
        no_production_change=True,
        scientific_approval=False, dba_approval=False,
        no_primary_outcomes_read=True,
        preserve_existing_frozen_spec=True,
        preserves_r9=True, no_trade_authority=True,
        actual_executable_venue_fills_proven=False,
        capacity_change_authorized=False,
        conclusion="NO_GO_UNTIL_INDEPENDENT_SIGNOFF",
    )
    try:
        if spec_id != SPEC or end_utc != END_UTC:
            raise ValueError("SCIENTIFIC_ID_OR_END_DATE_DRIFT")
        start = _utc(verified_at_utc)
        end = _utc(end_utc)
        remaining = (end - start).total_seconds()
        if remaining <= 0:
            raise ValueError("ENDPOINT_ALREADY_REACHED")
        due = _natural(due_sets, "due")
        complete = _natural(complete_sets, "complete")
        recent = _natural(eligible_added_last_7d, "recent_intake")
        h = _natural(hours_between_runs, "hours")
        m = _natural(max_sets_per_run, "batch")
        if h not in (1, 2, 3, 4, 6, 8, 12, 24) or m != PER_RUN_FROZEN:
            raise ValueError("UNREVIEWED_SCHEDULE_OR_FROZEN_BATCH_CHANGE")
        if complete > due:
            raise ValueError("COMPLETED_GREATER_THAN_DUE")
        yield_fraction = Decimal(success_fraction)
        if not yield_fraction.is_finite() or not 0 < yield_fraction <= 1:
            raise ValueError("INVALID_EVALUATION_SUCCESS_FRACTION")
        days = Decimal(str(remaining)) / SECONDS_PER_DAY
        backlog = due - complete
        intake = Decimal(recent * HORIZONS) / DAYS_PER_WEEK
        max_daily = Decimal(24 // h) * Decimal(PER_RUN_FROZEN)
        effective_daily = max_daily * yield_fraction
        net_daily = effective_daily - intake
        catchup = Decimal(backlog) / net_daily if net_daily > 0 else None
        feasible_if_assumptions_hold = (
            catchup is not None and catchup <= days
        )
        min_success_fraction = (
            (intake + Decimal(backlog) / days) / max_daily
        )
        out.update(
            status="SCENARIO_ONLY_NOT_AN_APPROVAL",
            original_frozen_per_call_limit=PER_RUN_FROZEN,
            hypothetical_hours_between_runs=h,
            hypothetical_cron_expression="38 " + (
                "* * * *" if h == 1 else "*/" + str(h) + " * * *"
            ),
            assumed_completion_fraction=str(yield_fraction),
            due_sets=due, complete_sets=complete, backlog=backlog,
            verified_at_utc=start.isoformat(),
            frozen_end_utc=end.isoformat(),
            days_remaining=str(days),
            trailing_7d_intake_sets_per_day=str(intake),
            maximum_scheduled_sets_per_day=str(max_daily),
            assumed_completed_sets_per_day=str(effective_daily),
            assumed_net_backlog_clearance_sets_per_day=str(net_daily),
            minimum_sustained_success_fraction_to_clear_by_end=str(
                min_success_fraction
            ),
            projected_clearance_days=(
                str(catchup) if catchup is not None else None
            ),
            mathematically_catches_up_before_end_if_assumptions_hold=(
                feasible_if_assumptions_hold
            ),
            assumptions_not_verified=[
                "INTAKE_FUTURE_EQUALS_TRAILING_SEVEN_DAY_AVERAGE",
                "EVALUATOR_MAX_40_SETS_PER_CALL_AND_SCHEDULE_STAYS_AVAILABLE",
                "SUSTAINED_SUCCESS_FRACTION_IS_HYPOTHETICAL",
                "BITGET_HISTORY_RETAINED_FOR_DELAYED_WINDOWS",
                "HTTP_TIMEOUT_CONCURRENCY_LOCKING_AND_LIMITS_NOT_BENCHMARKED",
                "ORIGINAL_MISSINGNESS_CENSORING_AND_PREREGISTRATION_PRESERVED",
            ],
        )
    except (TypeError, ValueError, ArithmeticError) as exc:
        out["reason"] = str(exc)
    return out
