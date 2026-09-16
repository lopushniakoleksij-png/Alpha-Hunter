import re
from pathlib import Path


SQL = Path("scientific_forward_holdout_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_registration_is_server_timed_immutable_and_conflict_detecting():
    assert "registered_at_utc timestamptz not null default clock_timestamp()" in SQL
    assert "scientific holdout specification conflict" in SQL
    assert "spec_hash" in SQL
    assert "extensions.digest" in SQL
    assert "sha256" in SQL
    assert "trg_ah_scientific_holdout_specs_append_only" in SQL
    assert "before update or delete" in LOWER
    trigger_position = LOWER.index("create trigger trg_ah_capture_scientific_holdout_v01")
    registration_position = LOWER.index(
        "select private.alpha_hunter_register_scientific_holdout_v01()"
    )
    assert trigger_position < registration_position
    assert "drop function private.alpha_hunter_register_scientific_holdout_v01()" in LOWER


def test_capture_is_prospective_only_and_has_no_backfill():
    assert "new.created_at <= v_spec.registered_at_utc" in SQL
    assert "new.candidate_at_utc <= v_spec.registered_at_utc" in SQL
    assert "NOT_STRICTLY_POST_REGISTRATION" in SQL
    assert "collection_ends_at_utc = registered_at_utc + interval '60 days'" in SQL
    assert "v_decision_available_at > v_spec.collection_ends_at_utc" in SQL
    assert "new.created_at > v_spec.collection_ends_at_utc" in SQL
    assert "new.candidate_at_utc > v_spec.collection_ends_at_utc" in SQL
    assert "AFTER_COLLECTION_WINDOW" in SQL
    assert "after insert on public.alpha_hunter_big_mover_money_scorecard_candidates" in LOWER
    assert not re.search(
        r"insert\s+into\s+public\.alpha_hunter_scientific_holdout_bindings\s+select",
        LOWER,
    )


def test_assignment_uses_candidate_time_evidence_and_not_outcomes():
    function_body = LOWER.split(
        "create or replace function private.alpha_hunter_capture_scientific_holdout_v01()",
        1,
    )[1].split("$$;", 1)[0]
    assert "alpha_hunter_big_mover_money_scorecard_outcomes" not in function_body
    assert "evaluation_status" not in function_body
    assert "new.scanner_direction" in function_body
    assert "new.geometry_valid" in function_body
    assert "new.frozen_evidence" in function_body
    assert "DIRECTION_AND_GEOMETRY_BOUND" in SQL
    assert "CONTROL_DIRECTION_AND_GEOMETRY_GAP" in SQL
    assert "CONTROL_DIRECTION_GAP" in SQL
    assert "CONTROL_GEOMETRY_GAP" in SQL


def test_source_contract_drift_and_explicit_json_booleans_fail_closed():
    assert "SOURCE_SCHEMA_DRIFT" in SQL
    assert "SOURCE_VERSION_DRIFT" in SQL
    assert "source_schema_fingerprint" in SQL
    assert "source_query_fingerprint" in SQL
    assert "pg_catalog.pg_get_functiondef" in SQL
    assert "ASSIGNMENT_FUNCTION_DRIFT" in SQL
    assert "big-mover-money-scorecard-v0.2-stage-linked" in SQL
    assert "big-mover-money-entry-bridge-v0.1" in SQL
    assert "@> '{\"geometry_direction_bound\":true}'::jsonb" in SQL
    assert "@> '{\"research_geometry_promoted\":false}'::jsonb" in SQL
    assert "PROMOTION_STATE_NOT_EXPLICITLY_FALSE" in SQL


def test_overlap_is_prevented_before_matching():
    assert "SYMBOL_DIRECTION_24H_COOLDOWN" in SQL
    assert "interval '24 hours'" in SQL
    assert "pg_catalog.pg_advisory_xact_lock" in SQL
    assert "pg_catalog.hashtextextended" in SQL
    assert "unique (spec_id, scorecard_id)" in SQL
    assert "unique (spec_id, source_bridge_id)" in SQL
    assert "group_name in ('TEST','CONTROL_POOL','EXCLUDED')" in SQL
    assert "MATCH_STRATUM_MISSING" in SQL
    assert "MATCH_COVARIATE_MISSING" in SQL
    assert "new.similarity_score not between 0.0 and 100.0" in SQL
    assert "new.feature_coverage not between 0.0 and 1.0" in SQL
    assert "abs(similarity_test-similarity_control)/100" in SQL


def test_metric_and_analysis_contract_do_not_claim_execution_returns():
    assert "decision_anchor_direction_adjusted_close_return_pct" in SQL
    assert "primary_horizon_hours = 12" in SQL
    assert "secondary_horizon_hours = 24" in SQL
    assert "'prohibited_metrics'" in SQL
    assert "'path_r_pre_cost'" in SQL
    assert "'candidate_path_outcome'" in SQL
    assert "'realistic_net_r'" in SQL
    assert "no unpaired evaluator; no peeking" in SQL
    assert "'primary_statistic'" in SQL
    assert "'minimum_effect_percentage_points',0.50" in SQL
    assert "'missing_data_rule'" in SQL
    assert "'multiplicity_rule'" in SQL
    assert "'day_60_rule'" in SQL
    assert "not independent replication" in SQL
    assert "'randomization_test'" in SQL
    assert "100000 Monte Carlo draws" in SQL
    assert "PRNG seed 2026091602" in SQL
    assert "100000 draws" in SQL
    assert "PRNG seed 2026091601" in SQL
    assert "p=(1+count(permuted_stat>=observed_stat))/(100000+1)" in SQL
    assert "LONG return_pct=100*(endpoint_close/reference_open-1)" in SQL
    assert "SHORT return_pct=100*(1-endpoint_close/reference_open)" in SQL
    assert "COLLECTING - NOT YET EVALUABLE" in SQL
    assert "'NONE'::text as scientific_conclusion" in SQL


def test_persistent_objects_are_service_role_read_only():
    for table in (
        "alpha_hunter_scientific_holdout_specs",
        "alpha_hunter_scientific_holdout_bindings",
        "alpha_hunter_scientific_holdout_capture_failures",
    ):
        assert f"alter table public.{table} enable row level security" in LOWER
        assert f"revoke all on table public.{table}" in LOWER
        assert f"grant select on table public.{table} to service_role" in LOWER
    assert "from public, anon, authenticated, service_role" in LOWER
    assert "grant insert on table public.alpha_hunter_scientific" not in LOWER
    assert "grant update on table public.alpha_hunter_scientific" not in LOWER
    assert "grant delete on table public.alpha_hunter_scientific" not in LOWER


def test_status_view_is_invoker_barrier_and_phone_safe():
    assert "with (security_invoker = true, security_barrier = true)" in SQL
    assert "CAPTURE_PROSPECTIVE_TEST_AND_CONTROL_POOL" in SQL
    assert "test_bound" in SQL
    assert "control_pool_bound" in SQL
    assert "capture_failures" in SQL
    assert "grant select on public.alpha_hunter_scientific_holdout_status_v01 to service_role" in LOWER


def test_safety_boundary_is_hard_constrained_and_has_no_order_path():
    assert SQL.count("check (shadow_only = true)") >= 3
    assert SQL.count("check (trade_permission = false)") >= 3
    assert SQL.count("check (production_promotion_permitted = false)") >= 3
    assert SQL.count("check (order_path = 'NONE')") >= 3
    forbidden = (
        "trade_permission=true",
        "trade_permission = true",
        "shadow_only=false",
        "shadow_only = false",
        "production_promotion_permitted=true",
        "place_order",
        "create_order",
        "submit_order",
        "/api/v2/mix/order/",
        "/api/v3/trade/",
        "private_account",
    )
    for token in forbidden:
        assert token not in LOWER


def test_auxiliary_capture_failure_cannot_block_canonical_candidate_insert():
    assert "exception when others then" in LOWER
    assert "scientific holdout capture failed for scorecard" in LOWER
    assert "return new;" in LOWER
