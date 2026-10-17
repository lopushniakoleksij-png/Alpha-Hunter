"""Synthetic metadata contracts, NOT sealed outcomes or a production repair."""
from pathlib import Path

import pytest
from pglast import parse_sql
from alpha_hunter.geometry_preunseal_capacity_gate_v01 import (
    audit_capacity, SPEC, FROZEN_END
)


def fixture():
    return dict(
        spec_id=SPEC,
        collection_ends_at_utc=FROZEN_END,
        primary_results_exposed=False,
        trade_permission=False,
        production_promotion_permitted=False,
        scientific_conclusion="NONE",
        cron_active=True,
        cron_schedule="38 */6 * * *",
        max_40_in_sql=True,
        max_batch_per_run=40,
        horizons_hours=[12,24],
        eligible=3915,
        due_12h=3866,
        due_24h=3759,
        complete_horizon_sets=3954,
        sealed_rows=15816,
        eligible_added_last_7d=1330,
        evaluator_failure_events=218,
    )


def no_authority(verdict):
    assert verdict["original_cohort_immutable"] is True
    assert verdict["private_outcomes_queried"] is False
    assert verdict["primary_results_exposed"] is False
    assert verdict["independent_scientific_approval"] is False
    assert verdict["independent_risk_approval"] is False
    assert verdict["allowed_to_change_cron"] is False
    assert verdict["allowed_to_run_evaluator"] is False
    assert verdict["allowed_to_unseal"] is False
    assert verdict["scientific_promotion_permitted"] is False
    assert verdict["trade_permission"] is False
    assert verdict["production_promotion_permitted"] is False


def test_real_snapshot_values_are_a_consistent_aggregate_backlog():
    r=audit_capacity(fixture())
    assert r["status"]=="BLOCKED_PREUNSEAL_CAPACITY_RISK"
    assert r["due_binding_horizon_sets"]==7625
    assert r["complete_binding_horizon_sets"]==3954
    assert r["apparent_overdue_set_deficit"]==3671
    assert r["theoretical_scheduled_daily_capacity"]==160
    assert r["recent_7d_average_new_sets_per_day"]=="380"
    assert r["intake_minus_scheduled_capacity_per_day"]=="220"
    assert r["minimum_days_to_clear_existing_deficit_if_zero_new_arrivals"]==23
    assert "RECENT_INTAKE_ABOVE_SCHEDULED_CAPACITY" in r["reasons"]
    no_authority(r)


def test_backlog_is_not_a_claim_of_missing_specific_outcomes():
    r=audit_capacity(fixture())
    assert r["lower_bound_note"]=="AGGREGATE_ONLY_NOT_BINDING_LEVEL_OUTCOME_CHECK"
    assert r["original_cohort_immutable"] is True
    no_authority(r)


def test_zero_backlog_still_cannot_authorize_unsealing():
    f=fixture()
    f.update(due_12h=1977,due_24h=1977,
             eligible_added_last_7d=100,evaluator_failure_events=0)
    r=audit_capacity(f)
    assert r["status"]=="OBSERVATION_COUNTS_ONLY_NO_AUTHORITY_TO_UNSEAL"
    assert r["apparent_overdue_set_deficit"]==0
    no_authority(r)


def test_slower_intake_does_not_hide_existing_backlog():
    f=fixture()
    f["eligible_added_last_7d"]=1
    r=audit_capacity(f)
    assert r["status"]=="BLOCKED_PREUNSEAL_CAPACITY_RISK"
    assert r["apparent_overdue_set_deficit"]==3671
    assert "DUE_SETS_EXCEED_AGGREGATE_COMPLETIONS" in r["reasons"]
    no_authority(r)


@pytest.mark.parametrize("k,v",[
    ("spec_id","SOME-OTHER-SPEC"),
    ("collection_ends_at_utc","2026-11-18T00:29:06.132018Z"),
    ("primary_results_exposed",None),
    ("primary_results_exposed",True),
    ("trade_permission",True),
    ("production_promotion_permitted",True),
    ("scientific_conclusion","POSITIVE"),
    ("cron_active",False),
    ("cron_schedule","38 * * * *"),
    ("cron_schedule","38 */3 * * *"),
    ("max_40_in_sql",False),
    ("max_batch_per_run",80),
    ("horizons_hours",[24]),
    ("eligible",-1),
    ("eligible",True),
    ("due_12h",4000),
    ("complete_horizon_sets",8000),
    ("sealed_rows",15815),
    ("eligible_added_last_7d",4000),
])
def test_unverified_inputs_and_changed_scientific_clock_fail_closed(k,v):
    f=fixture()
    f[k]=v
    r=audit_capacity(f)
    assert r["status"]=="METADATA_INSUFFICIENT", (k,r)
    assert r["reasons"]
    no_authority(r)


def test_missing_metadata_is_fail_closed():
    f=fixture()
    del f["eligible_added_last_7d"]
    r=audit_capacity(f)
    assert r["status"]=="METADATA_INSUFFICIENT"
    no_authority(r)


def test_sql_five_select_statements_never_read_sealed_primary_outcomes():
    sql=Path("ops/research/p2_geometry_due_capacity_readonly_v01.sql").read_text()
    statements=parse_sql(sql)
    assert len(statements)==5
    assert all(type(node.stmt).__name__=="SelectStmt" for node in statements)
    raw="\n".join(line.lower() for line in sql.splitlines()
                  if not line.lstrip().startswith("--"))
    assert "alpha_hunter_geometry_holdout_outcomes_sealed" not in raw
    assert "alpha_hunter_scientific_holdout_outcomes_sealed" not in raw
    assert "cron.job_run_details" in raw
    assert "cron.job" in raw
    assert "pg_get_functiondef" in raw
    assert "interval '5 minutes'" in raw
    assert "make_interval(hours=>h.horizon_hours)" in raw
    for mutation in (" insert ", " update ", " delete ", " alter ",
                     " drop ", " create ", " select private.alpha_hunter_run_geometry"):
        assert mutation not in raw


def test_runtime_is_pure_and_never_accesses_database():
    src=Path("alpha_hunter/geometry_preunseal_capacity_gate_v01.py").read_text()
    for forbidden in ("import requests", "import httpx", "psycopg", "supabase",
                      "sqlalchemy","execute_sql","run_geometry_holdout_sealed",
                      "cancel_order","place_order","alter_job","unseal_result"):
        assert forbidden not in src
    no_authority(audit_capacity(fixture()))
