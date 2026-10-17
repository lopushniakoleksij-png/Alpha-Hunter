"""Isolated synthetic tests; do NOT unseal geometry outcome tables."""
from copy import deepcopy
from pathlib import Path

import pytest
from pglast import parse_sql

from alpha_hunter.geometry_preunseal_operational_gate_v01 import (
    SPEC, review_capture_metadata,
)


def fixture():
    return dict(
        spec_id=SPEC,
        captured=30697,
        eligible=3915,
        excluded=26782,
        group_quality_mismatch=0,
        authority_violation=0,
        source_after_decision=0,
        source_hash_metadata_missing=0,
        eligible_nonascii_symbols=47,
        nonascii_with_logged_failure=26,
        nonascii_without_logged_failure=21,
        distinct_failed_bindings=27,
        failed_attempt_events=218,
        same_source_opposing_direction_pairs=4225,
        unexpected_source_reuse=0,
        primary_results_exposed=False,
        scientific_conclusion="NONE",
        trade_permission=False,
        production_promotion_permitted=False,
    )


def assert_denied(r):
    assert r["primary_outcome_access_permitted"] is False
    assert r["promotion_permitted"] is False
    assert r["trading_permission"] is False
    assert r["independent_review_approved"] is False
    assert r["cohort_spec_change_permitted"] is False
    assert r["missing_outcomes_imputed"] == 0
    assert r["historical_trade_reclassified"] == 0
    assert r["overwrite_existing_outcomes_permitted"] is False


def test_observed_metadata_flags_input_censoring_without_guessing_absent_outcomes():
    r=review_capture_metadata(fixture())
    assert r["status"]=="BLOCKED_FOR_INDEPENDENT_PREUNSEAL_REVIEW"
    assert r["observed_eligible_count"]==3915
    assert r["eligible_nonascii_symbols"]==47
    assert r["nonascii_with_logged_failure"]==26
    assert r["nonascii_without_logged_failure"]==21
    assert r["distinct_failed_bindings"]==27
    assert r["failed_attempt_events"]==218
    assert r["same_source_opposing_direction_pairs"]==4225
    assert r["missing_outcome_count"]=="UNKNOWN_NOT_RETRIEVED"
    assert "SYSTEMATIC_SYMBOL_REJECTION_RISK" in r["reasons"]
    assert "PAIRED_DIRECTION_SOURCE_DEPENDENCE" in r["reasons"]
    assert_denied(r)


def test_failed_attempt_events_are_not_added_as_extra_candidates():
    f=fixture()
    f["failed_attempt_events"]=2180
    r=review_capture_metadata(f)
    assert r["observed_eligible_count"]==3915
    assert r["missing_outcome_count"]=="UNKNOWN_NOT_RETRIEVED"
    assert_denied(r)


def test_clean_data_does_not_self_approve_or_unseal_primary_hypothesis():
    f=fixture()
    f.update(eligible_nonascii_symbols=0,nonascii_with_logged_failure=0,
             nonascii_without_logged_failure=0,distinct_failed_bindings=0,
             failed_attempt_events=0,same_source_opposing_direction_pairs=0)
    r=review_capture_metadata(f)
    assert r["status"]=="COLLECTING_SEALED_NO_SCIENTIFIC_PROMOTION"
    assert_denied(r)


@pytest.mark.parametrize("field,value",[
    ("spec_id","WRONG_SPEC"),
    ("primary_results_exposed",True),
    ("primary_results_exposed",None),
    ("trade_permission",True),
    ("production_promotion_permitted",True),
    ("scientific_conclusion","POSITIVE"),
    ("captured",30696),
    ("nonascii_without_logged_failure",20),
    ("eligible",-1),
    ("eligible",True),
    ("distinct_failed_bindings",5000),
    ("nonascii_with_logged_failure",28),
    ("failed_attempt_events",1),
    ("source_after_decision",1),
    ("source_hash_metadata_missing",1),
    ("authority_violation",1),
    ("group_quality_mismatch",1),
    ("unexpected_source_reuse",1),
])
def test_inconsistent_or_unauthorized_metadata_fails_closed(field,value):
    f=fixture()
    f[field]=value
    r=review_capture_metadata(f)
    assert r["status"]=="BLOCKED_MISSING_OR_INVALID_METADATA"
    assert r["reasons"]
    assert_denied(r)


def test_missing_counter_fails_closed():
    f=fixture()
    del f["excluded"]
    r=review_capture_metadata(f)
    assert r["status"]=="BLOCKED_MISSING_OR_INVALID_METADATA"
    assert_denied(r)


def test_sql_is_exactly_six_select_statements_no_mutations():
    sql=Path("ops/research/p2_geometry_preunseal_censoring_audit_v01.sql").read_text()
    parsed=parse_sql(sql)
    assert len(parsed)==6
    assert all(type(x.stmt).__name__=="SelectStmt" for x in parsed)


def test_sql_never_queries_sealed_primary_outcomes_and_keeps_unit_of_count():
    sql=Path("ops/research/p2_geometry_preunseal_censoring_audit_v01.sql").read_text()
    raw="\n".join(x.lower() for x in sql.splitlines()
                  if not x.lstrip().startswith("--"))
    assert "alpha_hunter_geometry_holdout_outcomes_sealed" not in raw
    assert "alpha_hunter_scientific_holdout_outcomes_sealed" not in raw
    assert "count(distinct f.binding_id)" in raw
    assert "count(distinct direction)" in raw
    assert "group_name='eligible'" in raw
    assert "symbol !~ '^[a-z0-9]+usdt$'" in raw
    for bad in (" insert "," update "," delete "," alter "," drop ",
                " create "," call "," http_get","select * from public.alpha_hunter_geometry_holdout_outcomes"):
        assert bad not in raw


def test_runtime_is_pure_no_private_credential_and_no_promotion_path():
    src=Path("alpha_hunter/geometry_preunseal_operational_gate_v01.py").read_text()
    for forbidden in ("import requests","urllib","psycopg","supabase",
                      "apply_migration", "place_order(", "execute_sql",
                      "cancel_order(", "read_outcome("):
        assert forbidden not in src
    assert "UNKNOWN_NOT_RETRIEVED" in src
    assert "independent_review_approved=False" in src
