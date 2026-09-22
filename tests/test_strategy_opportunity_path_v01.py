from pathlib import Path


SQL = Path("strategy_opportunity_path_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_opportunity_path_is_separate_from_execution_outcome():
    required = [
        "alpha_hunter_strategy_opportunity_paths_v01",
        "first_observation_opportunity_path",
        "descriptive_only",
        "descriptive_only_not_edge_proof",
    ]
    for marker in required:
        assert marker in LOWER


def test_source_is_only_canonical_persisted_evidence():
    assert "public.alpha_hunter_strategy_episodes_v01" in SQL
    assert "public.alpha_hunter_strategy_observations_v01" in SQL
    assert "public.alpha_hunter_symbol_snapshots" in SQL
    assert "last_closed_candle" in SQL

    forbidden = [
        "api.bitget.com",
        "market/tickers",
        "market/candles",
        "http_get",
        "requests.get",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_first_observation_path_excludes_partial_signal_hour():
    required = [
        "date_trunc('hour',v_episode.first_observed_at_utc)",
        "+ interval '1 hour'",
        "partial_signal_hour_excluded boolean not null default true",
        "first_observation_next_full_1h_candle",
    ]
    for marker in required:
        assert marker in LOWER


def test_frozen_horizons_are_1_4_12_24_hours():
    assert "array[1,4,12,24]" in SQL
    assert "clock_timestamp() < v_horizon_end" in SQL
    assert "make_interval(hours=>v_horizon)" in SQL


def test_opportunity_path_records_mfe_mae_and_endpoint_return():
    required = [
        "opportunity_max_favorable_excursion_pct",
        "opportunity_max_adverse_excursion_pct",
        "opportunity_direction_adjusted_endpoint_return_pct",
        "opportunity_max_favorable_excursion_r_from_reference",
        "opportunity_max_adverse_excursion_r_from_reference",
    ]
    for marker in required:
        assert marker in SQL


def test_candidate_conversion_and_confirmation_tax_are_preserved():
    required = [
        "first_candidate_at_utc",
        "time_to_candidate_minutes",
        "confirmation_tax_reference_pct",
        "confirmation_tax_r",
        "status='SHADOW_CANDIDATE'",
    ]
    for marker in required:
        assert marker in SQL


def test_planned_entry_touch_is_descriptive_not_execution():
    required = [
        "first_proposed_action",
        "planned_entry_touch_status",
        "toUCHED_AFTER_FIRST_OBSERVATION".lower(),
        "not_touched_within_horizon",
        "no_executable_entry_intent",
    ]
    for marker in required:
        assert marker in LOWER


def test_path_coverage_is_explicit_and_not_imputed():
    required = [
        "expected_path_candle_count",
        "observed_path_candle_count",
        "path_coverage_pct",
        "incomplete_canonical_candle_coverage",
        "insufficient_post_signal_window",
    ]
    for marker in required:
        assert marker in LOWER


def test_append_only_and_no_execution_authority():
    assert "before update or delete on public.alpha_hunter_strategy_opportunity_paths_v01" in LOWER

    required = [
        "descriptive_only boolean not null default true check(descriptive_only=true)",
        "shadow_only boolean not null default true check(shadow_only=true)",
        "trade_permission boolean not null default false check(trade_permission=false)",
        "threshold_change_permitted boolean not null default false",
        "production_promotion_permitted boolean not null default false",
        "order_path text not null default 'none' check(order_path='none')",
    ]
    for marker in required:
        assert marker in LOWER

    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled=true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_scorecard_is_nonranking_and_hourly_job_is_present():
    assert "alpha_hunter_strategy_opportunity_scorecard_v01" in SQL
    assert "alpha-hunter-strategy-opportunity-path-v01-hourly" in SQL
    assert "'54 * * * *'" in SQL
    assert "order by avg_opportunity" not in LOWER
    assert "rank()" not in LOWER
