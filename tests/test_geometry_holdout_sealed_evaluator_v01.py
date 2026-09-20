from pathlib import Path


SQL = Path("geometry_holdout_sealed_evaluator_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_sealed_outcomes_are_not_selectable_by_service_role():
    assert "revoke all on table public.alpha_hunter_geometry_holdout_outcomes_sealed" in LOWER
    assert "revoke all on table public.alpha_hunter_geometry_holdout_evaluator_failures" in LOWER

    assert "grant select on table public.alpha_hunter_geometry_holdout_outcomes_sealed" not in LOWER
    assert "grant select on table public.alpha_hunter_geometry_holdout_evaluator_failures" not in LOWER

    assert "intentionally no select grant to service_role" in LOWER


def test_outcomes_and_failures_are_append_only():
    required = [
        "before update or delete on public.alpha_hunter_geometry_holdout_outcomes_sealed",
        "before update or delete on public.alpha_hunter_geometry_holdout_evaluator_failures",
        "sealed geometry holdout outcomes are append-only",
    ]
    for marker in required:
        assert marker in LOWER


def test_evaluator_uses_only_public_bitget_3m_market_candles():
    assert "https://api.bitget.com/api/v3/market/candles" in SQL
    assert "category=USDT-FUTURES" in SQL
    assert "interval=3m" in SQL
    assert "limit=1000" in SQL
    assert "extensions.http_get" in SQL

    forbidden = [
        "/api/v2/mix/order/",
        "/api/v3/trade/",
        "/api/v3/account/",
        "private=true",
        "place-order",
        "place_order",
        "submit_order",
        "create_order",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_reference_anchor_is_post_decision_and_complete_candle_based():
    required = [
        "ceil(",
        "extract(epoch from r.decision_available_at_utc)/180.0",
        "v_reference_start",
        "v_last_expected_open",
        "interval '3 minutes'",
        "v_reference_open",
        "v_reference_open is null",
        "v_missing_count<>0",
        "v_observed_count<>v_expected_count",
        "INCOMPLETE_3M_COVERAGE",
    ]
    for marker in required:
        assert marker in SQL


def test_all_four_variants_are_evaluated_on_same_frozen_binding():
    required = [
        "1H_STOP_1H_TARGET",
        "15M_STOP_1H_TARGET",
        "15M_STOP_4H_TARGET",
        "1H_STOP_4H_TARGET",
        "jsonb_each(r.variant_geometry)",
        "frozen_stop",
        "frozen_target",
        "reference_rr",
        "unique(binding_id,research_variant,horizon_hours)",
    ]
    for marker in required:
        assert marker in SQL


def test_first_touch_path_does_not_guess_same_candle_order():
    required = [
        "TARGET_FIRST",
        "STOP_FIRST",
        "NEITHER",
        "BOTH_TOUCHED_IN_SAME_3M_CANDLE",
        "AMBIGUOUS_INTRABAR",
        "first_stop",
        "first_target",
        "t.first_stop=t.first_target",
    ]
    for marker in required:
        assert marker in SQL

    assert (
        "when x.path_class='BOTH_TOUCHED_IN_SAME_3M_CANDLE'\n"
        "              then null::boolean"
    ) in SQL


def test_q5_endpoint_matches_preregistered_definition():
    assert "x.reference_rr>=5.0" in SQL
    assert "x.path_class='TARGET_FIRST'" in SQL
    assert "q5_target_first" in SQL

    assert "reference_price_is_fill_claim boolean not null default false" in LOWER
    assert "check (reference_price_is_fill_claim=false)" in LOWER


def test_evaluator_is_sealed_collection_not_primary_analysis():
    required = [
        "'outcomes_exposed',false",
        "'primary_analysis_performed',false",
        "'primary_results_exposed boolean'",
        "'SEALED_OUTCOME_COLLECTION - NO PEEKING'",
        "'WAIT_FOR FROZEN COHORT GATE; DO NOT QUERY SEALED OUTCOMES'",
        "'NONE'::text as scientific_conclusion",
    ]

    # The return-table declaration is SQL syntax rather than a quoted string.
    assert "primary_results_exposed boolean" in SQL

    for marker in required:
        if marker == "'primary_results_exposed boolean'":
            continue
        assert marker in SQL


def test_safe_operational_status_exposes_counts_not_hypothesis_results():
    status_body = LOWER.split(
        "create or replace function private.alpha_hunter_geometry_holdout_sealed_operational_status_v01()",
        1,
    )[1].split("$$;", 1)[0]

    assert "count(*)" in status_body
    assert "max(evaluated_at_utc)" in status_body
    assert "primary_results_exposed" in status_body

    forbidden = [
        "q5_target_first",
        "reference_rr",
        "path_class",
        "research_variant",
        "target_first",
        "stop_first",
        "success_rate",
        "mcnemar",
    ]
    for marker in forbidden:
        assert marker not in status_body


def test_retry_path_fails_closed_to_data_insufficient_without_fake_result():
    required = [
        "v_prior_failures>=3",
        "interval '6 hours'",
        "alpha_hunter_insert_geometry_holdout_data_insufficient_v01",
        "'DATA_INSUFFICIENT',null,'DATA_INSUFFICIENT'",
        "retry_failures",
        "data_insufficient_sets",
    ]
    for marker in required:
        assert marker in SQL


def test_scheduler_is_isolated_and_does_not_modify_primary_hourly_core():
    assert "alpha-hunter-geometry-holdout-sealed-hourly" in SQL
    assert "'38 * * * *'" in SQL
    assert "select private.alpha_hunter_run_geometry_holdout_sealed_v01();" in SQL

    forbidden = [
        "unschedule",
        "alpha-hunter-primary",
        "p0 primary",
        "production_execution",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_persistent_safety_contract_is_hard_locked():
    assert SQL.count("check (shadow_only=true)") >= 2
    assert SQL.count("check (trade_permission=false)") >= 2
    assert SQL.count("check (production_promotion_permitted=false)") >= 2
    assert SQL.count("check (order_path='NONE')") >= 2

    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "shadow_only=false",
        "shadow_only = false",
        "production_promotion_permitted=true",
        "production_promotion_permitted = true",
        "money_entry_threshold_sets",
        "t0_authorized=true",
        "t1_authorized=true",
        "t2_authorized=true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_service_role_only_gets_safe_status_surface():
    assert (
        "grant execute on function private.alpha_hunter_geometry_holdout_sealed_operational_status_v01()\n"
        "  to service_role"
    ) in LOWER
    assert (
        "grant select on public.alpha_hunter_geometry_holdout_collection_status_v01\n"
        "  to service_role"
    ) in LOWER

    assert "grant execute on function private.alpha_hunter_run_geometry_holdout_sealed_v01()" not in LOWER
