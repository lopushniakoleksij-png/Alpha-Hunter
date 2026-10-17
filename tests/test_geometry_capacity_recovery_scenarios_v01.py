"""Isolated hypothetical math only; cannot be mistaken for scientific approval."""
from decimal import Decimal
from pathlib import Path

import pytest
from alpha_hunter.geometry_capacity_recovery_scenarios_v01 import (
    scenario, SPEC, END_UTC
)

BASE = dict(
    verified_at_utc="2026-10-17T01:59:49Z",
    end_utc=END_UTC,
    spec_id=SPEC,
    due_sets=7625,
    complete_sets=3954,
    eligible_added_last_7d=1330,
    hours_between_runs=6,
    success_fraction="1",
)


def run(**kw):
    return scenario(**(BASE | kw))


def no_permissions(x):
    assert x["advisory_only"]
    assert x["no_production_change"]
    assert x["scientific_approval"] is False
    assert x["dba_approval"] is False
    assert x["no_primary_outcomes_read"]
    assert x["preserve_existing_frozen_spec"]
    assert x["preserves_r9"]
    assert x["no_trade_authority"]
    assert x["actual_executable_venue_fills_proven"] is False
    assert x["capacity_change_authorized"] is False
    assert x["conclusion"]=="NO_GO_UNTIL_INDEPENDENT_SIGNOFF"


def test_current_schedule_cannot_keep_up_even_at_perfect_capacity():
    x=run()
    assert x["status"]=="SCENARIO_ONLY_NOT_AN_APPROVAL"
    assert x["backlog"]==3671
    assert x["maximum_scheduled_sets_per_day"]=="160"
    assert x["trailing_7d_intake_sets_per_day"]=="380"
    assert x["assumed_net_backlog_clearance_sets_per_day"]=="-220"
    assert x["projected_clearance_days"] is None
    assert x["mathematically_catches_up_before_end_if_assumptions_hold"] is False
    no_permissions(x)


def test_two_hour_cadence_at_100_pct_is_still_insufficient_for_endpoint():
    x=run(hours_between_runs=2)
    assert x["maximum_scheduled_sets_per_day"]=="480"
    assert x["assumed_net_backlog_clearance_sets_per_day"]=="100"
    assert Decimal(x["projected_clearance_days"])==Decimal("36.71")
    assert x["mathematically_catches_up_before_end_if_assumptions_hold"] is False
    no_permissions(x)


def test_hourly_at_half_success_insufficient():
    x=run(hours_between_runs=1,success_fraction="0.50")
    assert x["hypothetical_cron_expression"]=="38 * * * *"
    assert x["maximum_scheduled_sets_per_day"]=="960"
    assert x["assumed_completed_sets_per_day"]=="480.00"
    assert x["mathematically_catches_up_before_end_if_assumptions_hold"] is False
    no_permissions(x)


def test_hourly_at_60_pct_arithmetically_possible_not_verified():
    x=run(hours_between_runs=1,success_fraction="0.60")
    assert x["assumed_completed_sets_per_day"]=="576.00"
    assert x["assumed_net_backlog_clearance_sets_per_day"]=="196.00"
    assert Decimal(x["projected_clearance_days"])>18
    assert Decimal(x["projected_clearance_days"])<19
    assert x["mathematically_catches_up_before_end_if_assumptions_hold"] is True
    assert len(x["assumptions_not_verified"])>=5
    no_permissions(x)


def test_hourly_at_80_pct_still_no_approval():
    x=run(hours_between_runs=1,success_fraction="0.80")
    assert Decimal(x["projected_clearance_days"])<10
    assert x["mathematically_catches_up_before_end_if_assumptions_hold"] is True
    no_permissions(x)


@pytest.mark.parametrize("override", [
    {"spec_id":"fake"},
    {"end_utc":"2026-11-20T00:29:06.132018Z"},
    {"verified_at_utc":"2026-11-20T00:00:00Z"},
    {"verified_at_utc":"2026-10-17T00:00:00"},
    {"hours_between_runs":0},
    {"hours_between_runs":5},
    {"hours_between_runs":2,"max_sets_per_run":80},
    {"eligible_added_last_7d":-1},
    {"due_sets":1,"complete_sets":200},
    {"success_fraction":"NaN"},
    {"success_fraction":"0"},
    {"success_fraction":"1.01"},
    {"success_fraction":"bogus"},
    {"success_fraction":"-1"},
    {"due_sets":True},
])
def test_fail_closed_on_bad_date_sample_or_unreviewed_parameter(override):
    x=run(**override)
    assert x["status"]=="METADATA_NOT_VALIDATED"
    assert x.get("reason")
    no_permissions(x)


def test_capacity_scenario_script_has_no_venue_or_database_access():
    src=Path("alpha_hunter/geometry_capacity_recovery_scenarios_v01.py").read_text()
    for word in ("supabase","psycopg","import requests","urllib","httpx",
                 "execute_sql","cron.alter_job","alter_job(",
                 "place_order(","cancel_order(","read_outcomes("):
        assert word not in src
    no_permissions(run(hours_between_runs=1,success_fraction="1"))


def test_retrospective_retry_timing_would_change_even_if_sql_is_unchanged():
    """Synthetic always-failing market symbol; no real study result is read."""
    from datetime import datetime, timedelta, timezone

    sql=Path("geometry_holdout_sealed_evaluator_v01.sql").read_text()
    assert "v_prior_failures>=3" in sql
    assert "interval '6 hours'" in sql
    assert "raise exception 'SYMBOL_NOT_URL_SAFE'" in sql
    assert "limit 40" in sql.lower()

    due=datetime(2026,10,1,0,0,tzinfo=timezone.utc)

    def hypothetical_terminal_after(hours_per_run):
        errors=0
        for hour in range(0,48,hours_per_run):
            tick=due+timedelta(hours=hour,minutes=38)
            if tick<=due+timedelta(minutes=5):
                continue
            errors+=1  # synthetic error on every attempt, never a true outcome
            if errors>=3 and tick>due+timedelta(hours=6):
                return tick
        raise AssertionError("Expected synthetic terminal threshold")

    legacy=hypothetical_terminal_after(6)
    proposed=hypothetical_terminal_after(1)
    assert legacy==due+timedelta(hours=12,minutes=38)
    assert proposed==due+timedelta(hours=6,minutes=38)
    assert proposed<legacy
    # Important: no test result authorizes any scientific protocol retiming.
    no_permissions(run(hours_between_runs=1,success_fraction="0.8"))
