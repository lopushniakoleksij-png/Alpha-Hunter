from pathlib import Path

SQL = Path("h2_direction_sealed_evaluator_prereg_v01.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_h2_evaluator_is_preregistered_before_outcome_access():
    required = [
        "PREREGISTERED_LOCKED",
        "POLICY_REALISTIC_COST_ADJUSTED_NET_R_DELTA",
        "MEAN_H2_MINUS_LEGACY_POLICY_NET_R",
        "minimum_economic_effect_r=0.1000",
        "alpha=0.0500",
        "confidence_level=0.9500",
        "bootstrap_replicates=10000",
        "UTC_DAY_BLOCK_BOOTSTRAP_WITH_SYMBOL_SENSITIVITY",
    ]
    for marker in required:
        assert marker in SQL


def test_same_opportunity_policy_is_frozen():
    required = [
        "analysis_window_hours=24",
        "legacy_confirmation_window_hours=24",
        "legacy_no_confirmation_policy='NO_TRADE_0R'",
        "same_opportunity_window=true",
        "CONSERVATIVE_STOP_FIRST_MINUS_1R",
        "DIRECTION_ADJUSTED_HORIZON_CLOSE_R",
        "legacy receives no extra time for entering late",
    ]
    for marker in required:
        assert marker in SQL


def test_false_start_and_direction_guardrails_are_frozen():
    required = [
        "STOP_FIRST_OR_AMBIGUOUS_BEFORE_TARGET_WITHIN_24H",
        "false_start_noninferiority_margin_pp=10.0000",
        "LONG_AND_SHORT_MEAN_DELTA_MUST_BOTH_BE_NONNEGATIVE",
        "REMOVE_TOP_POSITIVE_SYMBOL_CONTRIBUTOR_SIGN_MUST_REMAIN_POSITIVE",
    ]
    for marker in required:
        assert marker in SQL


def test_validated_cost_model_is_mandatory_for_primary_economic_claim():
    required = [
        "validated_cost_model_required=true",
        "SINGLE_INDEPENDENT_VALIDATED_MODEL_FROZEN_BEFORE_UNSEAL",
        "if unavailable, confirmatory economic verdict is DATA_INSUFFICIENT",
    ]
    for marker in required:
        assert marker in SQL


def test_no_outcome_reader_or_result_exposure_exists():
    forbidden = [
        "alpha_hunter_h2_direction_outcomes",
        "realistic_net_r from",
        "primary_results_exposed=true",
        "outcome_access_permitted=true",
        "confirmatory_analysis_permitted=true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_append_only_and_safety_claim_ceiling():
    required = [
        "alpha_hunter_block_append_only_mutation",
        "independent_replication_required boolean not null default true",
        "t0_authorized boolean not null default false",
        "threshold_change_permitted boolean not null default false",
        "production_promotion_permitted boolean not null default false",
        "shadow_only boolean not null default true",
        "trade_permission boolean not null default false",
        "order_path text not null default 'NONE'",
    ]
    for marker in required:
        assert marker in SQL


def test_prereg_status_exposes_rules_not_results():
    assert "alpha_hunter_h2_direction_evaluator_prereg_status_v01" in SQL
    assert "BUILD_SEALED_OUTCOME_COLLECTOR_WITHOUT_EXPOSING_RESULTS" in SQL
    assert "grant select on public.alpha_hunter_h2_direction_evaluator_prereg_status_v01" in LOWER
