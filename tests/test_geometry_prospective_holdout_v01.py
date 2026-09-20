import re
from pathlib import Path


SQL = Path("geometry_prospective_holdout_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_geometry_holdout_is_strictly_prospective_and_has_no_backfill():
    assert "new.created_at<=v_spec.registered_at_utc" in SQL
    assert "new.captured_at_utc<=v_spec.registered_at_utc" in SQL
    assert "NOT_STRICTLY_POST_REGISTRATION" in SQL
    assert "collection_ends_at_utc=registered_at_utc + interval '60 days'" in SQL
    assert "AFTER_COLLECTION_WINDOW" in SQL

    assert not re.search(
        r"insert\s+into\s+public\.alpha_hunter_geometry_holdout_bindings\s+select",
        LOWER,
    )

    trigger_pos = LOWER.index("create trigger trg_ah_capture_geometry_holdout_v01")
    registration_pos = LOWER.index(
        "select private.alpha_hunter_register_geometry_holdout_v01()"
    )
    assert trigger_pos < registration_pos


def test_geometry_holdout_freezes_retrospectively_selected_primary_hypothesis():
    required = [
        "H_15M_STOP_4H_TARGET_Q5_PATH_VS_1H_BASELINE_24H_V1",
        "15M_STOP_4H_TARGET",
        "1H_STOP_1H_TARGET",
        "Q5_TARGET_FIRST_24H",
        "'primary_horizon_hours',24",
        "'secondary_horizon_hours',12",
        "selected as the single primary alternative after the explicitly retrospective v0.3 exploratory screen",
        "all pre-registration observations are prohibited from confirmatory use",
    ]
    for marker in required:
        assert marker in SQL


def test_primary_endpoint_combines_rr_and_first_touch_without_fill_claim():
    required = [
        "reference RR >= 5.0 AND target is touched before stop within 24H",
        "first post-decision fully complete public Bitget 3m candle open",
        "open_time >= ceil_3m(decision_available_at_utc)",
        "BOTH_TOUCHED_IN_SAME_3M_CANDLE",
        "do not infer intrabar order",
        "never use a pre-decision candle or source entry as a fill claim",
    ]
    for marker in required:
        assert marker in SQL


def test_capture_reads_candidate_time_evidence_only_and_no_outcomes():
    function_body = LOWER.split(
        "create or replace function private.alpha_hunter_capture_geometry_holdout_v01()",
        1,
    )[1].split("$$;", 1)[0]

    assert "alpha_hunter_big_mover_money_scorecard_outcomes" not in function_body
    assert "evaluation_status" not in function_body
    assert "mfe_pct" not in function_body
    assert "mae_pct" not in function_body

    assert "alpha_hunter_signal_features" in function_body
    assert "source_payload" in function_body
    assert "variant_bundle" in function_body


def test_source_model_and_fingerprints_fail_closed():
    required = [
        "geometry-diagnostics-v0.2.2-money-entry-scope-aligned",
        "SOURCE_SCHEMA_DRIFT",
        "SOURCE_QUERY_DRIFT",
        "SOURCE_VERSION_DRIFT",
        "alpha_hunter_geometry_holdout_source_schema_fingerprint_v01",
        "alpha_hunter_geometry_holdout_query_fingerprint_v01",
        "pg_get_viewdef",
        "pg_get_functiondef",
        "spec_hash",
        "geometry holdout specification conflict",
    ]
    for marker in required:
        assert marker in SQL


def test_all_four_variants_are_frozen_on_same_candidate():
    required = [
        "1H_STOP_1H_TARGET",
        "15M_STOP_1H_TARGET",
        "15M_STOP_4H_TARGET",
        "1H_STOP_4H_TARGET",
        "COMMON_VARIANT_GEOMETRY_COMPLETE",
        "COMMON_VARIANT_GEOMETRY_INCOMPLETE",
        "variant_geometry",
        "support_15m",
        "resistance_15m",
        "support_1h",
        "resistance_1h",
        "support_4h",
        "resistance_4h",
    ]
    for marker in required:
        assert marker in SQL


def test_overlap_guard_and_candidate_pairing_are_frozen():
    assert "SYMBOL_DIRECTION_24H_COOLDOWN" in SQL
    assert "interval '24 hours'" in SQL
    assert "pg_catalog.pg_advisory_xact_lock" in SQL
    assert "pg_catalog.hashtextextended" in SQL
    assert "within-candidate pairing is intrinsic" in SQL
    assert "no post-hoc matching or replacement" in SQL


def test_sample_and_inference_contract_are_frozen():
    required = [
        "minimum_paired_candidates=100",
        "minimum_symbols=30",
        "minimum_utc_days=20",
        "minimum_candidates_per_direction=25",
        "maximum_collection_days=60",
        "one-sided exact McNemar test",
        "alpha 0.025",
        "at least +5 percentage points",
        "100000 draws",
        "PRNG seed 2026092001",
        "incomplete primary pairs exceed 10%",
        "INCONCLUSIVE",
        "do not extend or relax",
    ]
    for marker in required:
        assert marker in SQL


def test_persistent_holdout_objects_are_append_only_and_service_role_read_only():
    tables = [
        "alpha_hunter_geometry_holdout_specs",
        "alpha_hunter_geometry_holdout_bindings",
        "alpha_hunter_geometry_holdout_capture_failures",
    ]
    for table in tables:
        assert f"alter table public.{table} enable row level security" in LOWER
        assert f"revoke all on table public.{table}" in LOWER
        assert f"grant select on table public.{table} to service_role" in LOWER

    assert "before update or delete on public.alpha_hunter_geometry_holdout_specs" in LOWER
    assert "before update or delete on public.alpha_hunter_geometry_holdout_bindings" in LOWER
    assert "before update or delete on public.alpha_hunter_geometry_holdout_capture_failures" in LOWER

    assert "grant insert on table public.alpha_hunter_geometry_holdout" not in LOWER
    assert "grant update on table public.alpha_hunter_geometry_holdout" not in LOWER
    assert "grant delete on table public.alpha_hunter_geometry_holdout" not in LOWER


def test_safety_boundary_has_no_execution_or_threshold_authority():
    assert SQL.count("check (shadow_only=true)") >= 3
    assert SQL.count("check (trade_permission=false)") >= 3
    assert SQL.count("check (production_promotion_permitted=false)") >= 3
    assert SQL.count("check (order_path='NONE')") >= 3

    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "shadow_only=false",
        "shadow_only = false",
        "production_execution_enabled=true",
        "place_order",
        "create_order",
        "submit_order",
        "/api/v2/mix/order/",
        "/api/v3/trade/",
        "money_entry_threshold_sets",
        "status='ACTIVE'",
        "cron.",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_capture_failure_is_auxiliary_and_cannot_block_canonical_geometry_insert():
    assert "exception when others then" in LOWER
    assert "geometry holdout capture failed for diagnostic" in SQL
    assert "return new;" in LOWER


def test_status_view_is_phone_safe_and_never_claims_support_during_capture():
    required = [
        "alpha_hunter_geometry_holdout_status_v01",
        "with (security_invoker=true,security_barrier=true)",
        "COLLECTING - CAPTURE ONLY - NOT YET EVALUABLE",
        "capture_sample_gate_met",
        "IMPLEMENT_FROZEN_PUBLIC_3M_FIRST_TOUCH_EVALUATOR",
        "'NONE'::text as scientific_conclusion",
        "grant select on public.alpha_hunter_geometry_holdout_status_v01 to service_role",
    ]
    for marker in required:
        assert marker in SQL
