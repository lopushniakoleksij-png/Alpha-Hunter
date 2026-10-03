from pathlib import Path

SQL = Path("ops/sql/t0_directional_threshold_holdout_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_long_candidate_is_direction_specific_and_preregistered():
    assert "me-t0-long-holdout-v01" in SQL
    assert "'long'" in SQL
    assert "15.0" in SQL
    assert "0.05" in SQL
    assert "230" in SQL
    assert "0.270180" in SQL


def test_short_stays_data_collection_only():
    assert "me-t0-short-collection-v01" in SQL
    assert "data_collection_only" in SQL
    assert "'numeric_threshold_inference_permitted',false" in SQL


def test_t1_t2_are_explicitly_unset():
    assert "check(min_t1_remaining_r is null)" in SQL
    assert "check(min_t2_remaining_r is null)" in SQL
    assert "'t1_t2_numeric_thresholds_frozen',false" in SQL


def test_forward_only_no_historical_backfill():
    assert "c.candidate_at_utc>=sp.holdout_not_before_utc" in SQL
    assert "'historical_backfill_permitted',false" in SQL


def test_base_gate_mirrors_threshold_independent_stage_rules():
    for marker in [
        "direction_12h='bullish'",
        "direction_1d='bullish'",
        "direction_12h='bearish'",
        "direction_1d='bearish'",
        "execution_setup_direction=src.direction",
        "liquidity_ok is true",
        "scanner_participation_confirmed is true",
        "participation_emerging is true",
        "scanner_structure_valid is true",
    ]:
        assert marker in SQL


def test_confirmatory_gate_requires_effect_ci_and_diversity():
    assert "minimum_completed_candidates" in SQL
    assert "minimum_distinct_symbols" in SQL
    assert "minimum_distinct_utc_days" in SQL
    assert "mean_r-1.96*sd_r/sqrt(completed_rows)<=0" in SQL
    assert "mean_r<minimum_economic_effect_r" in SQL
    assert "stop_survived_pct<90.0" in SQL


def test_no_activation_or_trade_authority():
    assert "no production threshold row is activated or numerically populated" in SQL
    for forbidden in [
        "status='active'",
        "status = 'active'",
        "trade_permission=true",
        "threshold_activation_permitted=true",
        "production_promotion_permitted=true",
        "place_order",
        "set_leverage",
    ]:
        assert forbidden not in SQL
