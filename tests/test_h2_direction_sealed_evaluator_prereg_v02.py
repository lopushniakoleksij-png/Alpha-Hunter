from pathlib import Path

SQL = Path("h2_direction_sealed_evaluator_prereg_v02.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_v02_supersedes_v01_before_any_outcome_table():
    required = [
        "AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V01",
        "AH-H2-DIRECTION-SEALED-EVALUATOR-PREREG-V02",
        "cannot supersede after H2 outcome table creation",
        "previous_outcome_table_existed=false",
        "previous_outcome_accessed=false",
        "tuning_to_observed_outcome_permitted=false",
    ]
    for marker in required:
        assert marker in SQL


def test_exact_minute_path_alignment_is_frozen():
    required = [
        "path_interval_minutes=1",
        "path_page_hours=12",
        "path_page_count=2",
        "exact_anchor_alignment_required=true",
        "BITGET_PUBLIC_V3_1M_CANDLES",
        "TWO_NONOVERLAPPING_12H_PAGES_FROM_EXACT_ANCHOR_MINUTE",
        "two nonoverlapping 12h pages",
        "exact public Bitget 1m open",
    ]
    for marker in required:
        assert marker in SQL


def test_economic_and_false_start_rules_are_unchanged_from_v01():
    required = [
        "POLICY_REALISTIC_COST_ADJUSTED_NET_R_DELTA",
        "MEAN_H2_MINUS_LEGACY_POLICY_NET_R",
        "minimum_economic_effect_r=0.1000",
        "alpha=0.0500",
        "bootstrap_replicates=10000",
        "false_start_noninferiority_margin_pp=10.0000",
        "NO_TRADE_0R",
        "CONSERVATIVE_STOP_FIRST_MINUS_1R",
    ]
    for marker in required:
        assert marker in SQL


def test_v02_still_exposes_no_outcome_or_trade_authority():
    forbidden = [
        "primary_results_exposed=true",
        "outcome_access_permitted=true",
        "confirmatory_analysis_permitted=true",
        "trade_permission=true",
        "production_promotion_permitted=true",
        "place_order",
        "cancel_order",
        "modify_order",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_v02_status_is_rules_only():
    assert "alpha_hunter_h2_direction_evaluator_active_status_v02" in SQL
    assert "BUILD_EXACT_1M_SEALED_OUTCOME_COLLECTOR" in SQL
    assert "grant select on public.alpha_hunter_h2_direction_evaluator_active_status_v02" in LOWER
