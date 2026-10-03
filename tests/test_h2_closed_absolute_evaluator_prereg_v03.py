from pathlib import Path

SQL = Path("h2_closed_absolute_evaluator_prereg_v03.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_evaluator_is_bound_to_exact_corrected_capture_hash():
    assert "ah-direction-architecture-h2-closed-capture-v02" in LOWER
    assert "capture_spec_hash" in LOWER
    assert "v_capture.spec_hash" in LOWER
    assert "h2-direction-architecture-closed-capture-v0.2" in LOWER
    assert "corrected h2 v0.2 capture contract mismatch" in LOWER


def test_primary_question_is_absolute_h2_economic_edge_not_legacy_superiority():
    assert "h2_policy_realistic_cost_adjusted_net_r" in LOWER
    assert "mean_h2_policy_net_r" in LOWER
    assert "minimum_mean_realistic_net_r" in LOWER
    assert "primary_95pct_ci_lower_bound_must_exceed" in LOWER
    assert "legacy_superiority_claim_permitted boolean not null default false" in LOWER
    assert "not part of this primary evaluator" in LOWER


def test_support_and_falsification_are_frozen_before_outcomes():
    assert "minimum_economic_effect_r=0.1000" in LOWER
    assert "alpha=0.0500" in LOWER
    assert "confidence_level=0.9500" in LOWER
    assert "bootstrap_replicates=10000" in LOWER
    assert "primary_95pct_ci_upper_bound_below_or_equal_zero" in LOWER
    assert "mean_realistic_net_r_below_or_equal_minus_0_10r" in LOWER


def test_cost_model_is_required_and_realistic_net_r_claim_remains_locked():
    assert "validated_cost_model_required boolean not null default true" in LOWER
    assert "single_independent_validated_model_frozen_before_unseal" in LOWER
    assert "realistic_net_r_claim_permitted boolean not null default false" in LOWER
    assert "cost_model_currently_validated',false" in LOWER


def test_direction_and_concentration_guardrails_are_frozen():
    assert "long_and_short_mean_net_r_must_both_be_nonnegative" in LOWER
    assert "remove_top_positive_symbol_contributor_mean_must_remain_positive" in LOWER
    assert "utc_day_block_bootstrap_with_symbol_sensitivity" in LOWER


def test_preregistration_creates_no_outcome_or_collector_surface():
    forbidden = [
        "create table if not exists public.alpha_hunter_h2_closed_outcomes",
        "create or replace function private.alpha_hunter_run_h2_closed_outcome",
        "cron.schedule",
        "extensions.http_get",
        "h2_gross_r_pre_cost",
        "terminal_close double precision",
    ]
    for marker in forbidden:
        assert marker not in LOWER
    assert "false as outcome_table_created" in LOWER


def test_no_threshold_production_trade_or_order_authority():
    forbidden = [
        "trade_permission=true",
        "threshold_change_permitted=true",
        "production_promotion_permitted=true",
        "t0_authorized=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER
    assert "'none'::text as order_path" in LOWER


def test_evaluator_spec_is_append_only_and_service_role_read_only():
    assert "trg_ah_h2_closed_evaluator_specs_append_only_v03" in LOWER
    assert "alpha_hunter_block_append_only_mutation" in LOWER
    assert "grant select on public.alpha_hunter_h2_closed_evaluator_specs_v03" in LOWER
