"""Isolated, deterministic cadence-contract tests. No database or market calls."""
from datetime import date

import pytest

from ops.reviews.p0_big_mover_freshness_cadence_audit_v01 import (
    _expand_utc_field,
    audit_cadence,
    daily_utc_schedule,
)


DAY = date(2026, 11, 4)
SIX_HOURLY = "11 2,8,14,20 * * *"
HOURLY_STAGE = "16 * * * *"


def test_actual_producer_cadence_cannot_meet_90_minute_hourly_guard():
    result = audit_cadence(
        producer_cron=SIX_HOURLY,
        consumer_cron=HOURLY_STAGE,
        max_age_minutes=90,
        day_utc=DAY,
        producer_runtime_minutes=3,
        source_timestamp_lag_minutes=7,
    )
    assert result["stage_runs"] == 24
    assert result["fresh_stage_runs"] == 8
    assert result["blocked_stage_runs"] == 16
    assert result["schedule_contract_pass"] is False
    assert [16, 17, 18, 19] == [
        hour for hour in result["blocked_stage_hours_utc"] if 16 <= hour <= 19
    ]
    assert result["trade_permission"] is False
    assert result["production_change_permitted"] is False


def test_hourly_lightweight_candidate_can_satisfy_cadence_only():
    result = audit_cadence(
        producer_cron="11 * * * *",
        consumer_cron=HOURLY_STAGE,
        max_age_minutes=90,
        day_utc=DAY,
        producer_runtime_minutes=3,
        source_timestamp_lag_minutes=7,
    )
    assert result["fresh_stage_runs"] == 24
    assert result["blocked_stage_runs"] == 0
    assert result["schedule_contract_pass"] is True
    assert result["kind"] == "SCHEDULE_ONLY_SIMULATION_NOT_LIVE_DATA"
    assert not result["trade_permission"]
    assert not result["production_change_permitted"]


def test_hourly_job_finishing_after_consumer_does_not_claim_current_source():
    result = audit_cadence(
        producer_cron="11 * * * *",
        consumer_cron=HOURLY_STAGE,
        max_age_minutes=30,
        day_utc=DAY,
        producer_runtime_minutes=6,
        source_timestamp_lag_minutes=7,
    )
    assert result["blocked_stage_runs"] == 24
    assert result["hours"][14]["source_age_minutes"] == 72.0


def test_freshness_exactly_at_boundary_is_valid():
    result = audit_cadence(
        producer_cron="0 * * * *",
        consumer_cron="30 * * * *",
        max_age_minutes=30,
        day_utc=DAY,
    )
    assert result["schedule_contract_pass"] is True
    assert result["hours"][0]["source_age_minutes"] == 30.0


def test_one_minute_beyond_boundary_fails_closed():
    result = audit_cadence(
        producer_cron="0 * * * *",
        consumer_cron="31 * * * *",
        max_age_minutes=30,
        day_utc=DAY,
    )
    assert result["blocked_stage_runs"] == 24
    assert result["hours"][0]["status"] == "STALE"


def test_cross_midnight_producer_source_is_found_but_stale():
    result = audit_cadence(
        producer_cron="23 23 * * *",
        consumer_cron="16 0 * * *",
        max_age_minutes=15,
        day_utc=DAY,
    )
    assert result["stage_runs"] == 1
    assert result["hours"][0]["source_age_minutes"] == 53
    assert result["hours"][0]["status"] == "STALE"


def test_cron_hour_list_and_step_range_parse_deterministically():
    assert daily_utc_schedule(SIX_HOURLY) == (
        (2, 11), (8, 11), (14, 11), (20, 11),
    )
    assert _expand_utc_field("2-8/3", maximum=23) == (2, 5, 8)


@pytest.mark.parametrize("schedule", [
    "11 2,8,14,20 * * 1",
    "11 2,8,14,20 1 * *",
    "61 * * * *",
    "11 24 * * *",
    "11 */0 * * *",
    "11 2-1 * * *",
    "11 * * *",
    "bad cron",
])
def test_unsupported_or_invalid_schedules_are_rejected(schedule):
    with pytest.raises(ValueError):
        daily_utc_schedule(schedule)


@pytest.mark.parametrize("parameter", [
    {"max_age_minutes": 0},
    {"max_age_minutes": -1},
    {"producer_runtime_minutes": -1},
    {"source_timestamp_lag_minutes": -1},
    {"producer_runtime_minutes": 1440},
])
def test_invalid_assumptions_fail_before_simulation(parameter):
    kwargs = dict(
        producer_cron=SIX_HOURLY,
        consumer_cron=HOURLY_STAGE,
        max_age_minutes=90,
        day_utc=DAY,
    )
    kwargs.update(parameter)
    with pytest.raises(ValueError):
        audit_cadence(**kwargs)
