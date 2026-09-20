from pathlib import Path

SQL = Path("geometry_multitimeframe_research_v03.sql").read_text()


def test_v03_is_read_only_and_shadow_only():
    lower = SQL.lower()

    for marker in [
        "insert into",
        "update public.",
        "delete from",
        "cron.",
        "http_get(",
        "http_post(",
        "/api/v3/trade/place-order",
        "/api/v2/mix/order/place-order",
    ]:
        assert marker not in lower

    required = [
        "with (security_invoker=true)",
        "true as shadow_only",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "false as threshold_derivation_permitted",
        "false as confirmatory_claim_permitted",
        "false as t0_authorized",
    ]
    for marker in required:
        assert marker in SQL


def test_v03_reuses_existing_scope_aligned_geometry_and_frozen_levels():
    required = [
        "geometry-diagnostics-v0.2.2-money-entry-scope-aligned",
        "alpha_hunter_geometry_diagnostics",
        "alpha_hunter_signal_features",
        "{timeframes,15m,support}",
        "{timeframes,15m,resistance}",
        "{timeframes,1H,support}",
        "{timeframes,1H,resistance}",
        "{timeframes,4H,support}",
        "{timeframes,4H,resistance}",
    ]
    for marker in required:
        assert marker in SQL


def test_v03_compares_four_observable_structural_variants():
    variants = [
        "1H_STOP_1H_TARGET",
        "15M_STOP_1H_TARGET",
        "15M_STOP_4H_TARGET",
        "1H_STOP_4H_TARGET",
    ]
    for variant in variants:
        assert variant in SQL

    assert "research_stop" in SQL
    assert "research_target" in SQL
    assert "research_rr" in SQL
    assert "geometry_valid" in SQL


def test_v03_keeps_current_5r_as_reference_not_new_threshold():
    assert "rr_ge_5_current_reference_only" in SQL
    assert "CURRENT_PRODUCTION_RR_REFERENCE_5_IS_DESCRIPTIVE_ONLY" in SQL
    assert "rr_ge_5_current_reference_observations" in SQL
    assert "NO_VARIANT_PROMOTION_FROM_THIS_VIEW" in SQL
    assert "Preregister a separate prospective holdout" in SQL

    forbidden = [
        "money_entry_threshold_sets",
        "status='ACTIVE'",
        "stage_eligible=true",
        "trade_permission=true",
        "production_execution_enabled=true",
    ]
    for marker in forbidden:
        assert marker not in SQL


def test_v03_measures_path_survivability_not_rr_alone():
    required = [
        "alpha_hunter_big_mover_money_scorecard_candidates",
        "alpha_hunter_big_mover_money_scorecard_outcomes",
        "mfe_pct",
        "mae_pct",
        "research_stop_touched",
        "research_target_touched",
        "stop_survival_pct",
        "target_touched_without_stop_pct",
        "BOTH_TOUCHED_PATH_ORDER_UNKNOWN",
        "MFE_MAE_TOUCH_TEST_REUSES_EXISTING_SCORECARD; BOTH_TOUCHED_HAS_UNKNOWN_ORDER",
    ]
    for marker in required:
        assert marker in SQL


def test_v03_preserves_noise_context_for_tighter_stops():
    required = [
        "{behaviour,spread_pct}",
        "{timeframes,15m,indicators,atr_pct}",
        "{timeframes,1H,indicators,atr_pct}",
        "stop_to_spread_multiple",
        "stop_to_atr_15m_multiple",
        "stop_to_atr_1h_multiple",
    ]
    for marker in required:
        assert marker in SQL


def test_v03_views_are_service_role_only():
    required = [
        "revoke all on public.alpha_hunter_geometry_multitimeframe_observations_v03",
        "grant select on public.alpha_hunter_geometry_multitimeframe_observations_v03",
        "revoke all on public.alpha_hunter_geometry_multitimeframe_status_v03",
        "grant select on public.alpha_hunter_geometry_multitimeframe_status_v03",
        "to service_role",
    ]
    for marker in required:
        assert marker in SQL
