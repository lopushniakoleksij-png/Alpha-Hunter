from pathlib import Path

from alpha_hunter.collector import last_closed_candle


SQL = Path("strategy_forward_outcome_ledger_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_last_closed_candle_excludes_current_forming_candle():
    candles = [
        {"timestamp": 1, "close": 10.0},
        {"timestamp": 2, "close": 11.0},
        {"timestamp": 3, "close": 12.0},
    ]
    assert last_closed_candle(candles) == {"timestamp": 2, "close": 11.0}
    assert last_closed_candle([{"timestamp": 1}]) is None


def test_normalized_strategy_observation_and_episode_ledgers_exist():
    required = [
        "alpha_hunter_strategy_observations_v01",
        "alpha_hunter_strategy_episodes_v01",
        "strategy_instance_id",
        "first_observed_at_utc",
        "earliest_identifiable_entry_price",
        "first_reward_risk",
    ]
    for marker in required:
        assert marker in SQL


def test_capture_is_driven_only_by_canonical_symbol_snapshots():
    assert "on public.alpha_hunter_symbol_snapshots" in SQL
    assert "new.payload->'multi_strategy_engine'->'strategies'" in SQL
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


def test_forward_horizons_are_frozen_and_prospective():
    assert "array[1,4,12,24]" in SQL
    assert "clock_timestamp() < v_horizon_end" in SQL
    assert "o.observed_at_utc<=v_horizon_end" in SQL
    assert "s.collected_at_utc>v_candidate.observed_at_utc" in SQL


def test_confirmation_tax_and_remaining_r_are_recorded():
    required = [
        "confirmation_tax_reference_pct",
        "confirmation_tax_entry_pct",
        "confirmation_tax_r",
        "remaining_r_at_candidate",
        "remaining_r_delta_from_first",
        "time_to_candidate_minutes",
    ]
    for marker in required:
        assert marker in SQL


def test_limit_fill_requires_future_fully_closed_candle_touch():
    required = [
        "v_candidate.action='PLACE_LIMIT'",
        "last_closed_candle",
        "last_closed_candle'->>'low',''",
        "::double precision <= v_candidate_entry",
        "last_closed_candle'->>'high',''",
        "::double precision >= v_candidate_entry",
        "v_trigger_known_at := v_trigger_candle_open+interval '1 hour'",
    ]
    for marker in required:
        assert marker in SQL


def test_intrabar_ordering_is_not_invented():
    required = [
        "trigger_candle_excluded boolean not null default true",
        "partial_signal_hour_excluded boolean not null default true",
        "v_measurement_start :=",
        "v_trigger_candle_open+interval '1 hour'",
        "target_stop_same_candle_ambiguous",
        "ordering_ambiguous",
    ]
    for marker in required:
        assert marker in LOWER


def test_mae_mfe_and_endpoint_return_are_direction_aware():
    required = [
        "max_favorable_excursion_pct",
        "max_adverse_excursion_pct",
        "direction_adjusted_endpoint_return_pct",
        "v_episode.direction='LONG'",
        "100.0*(v_max_high-v_fill_price)/v_fill_price",
        "100.0*(v_fill_price-v_min_low)/v_fill_price",
    ]
    for marker in required:
        assert marker in SQL


def test_cost_adjustment_fails_closed_instead_of_inventing_net_return():
    assert "gross_only boolean not null default true check(gross_only=true)" in LOWER
    assert "net_of_cost_return_pct double precision" in LOWER
    assert "not_bound_to_cost_evidence" in LOWER


def test_forward_evidence_is_append_only_and_cannot_grant_execution():
    for table in [
        "alpha_hunter_strategy_observations_v01",
        "alpha_hunter_strategy_episodes_v01",
        "alpha_hunter_strategy_forward_outcomes_v01",
    ]:
        assert f"alter table public.{table}" in LOWER
        assert f"before update or delete on public.{table}" in LOWER

    required = [
        "shadow_only boolean not null default true check(shadow_only=true)",
        "trade_permission boolean not null default false check(trade_permission=false)",
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


def test_hourly_evaluator_and_nonranking_scorecard_are_present():
    assert "alpha-hunter-strategy-forward-outcome-v01-hourly" in SQL
    assert "'53 * * * *'" in SQL
    assert "alpha_hunter_strategy_forward_scorecard_v01" in SQL
    assert "avg_confirmation_tax_reference_pct" in SQL
    assert "avg_mfe_pct" in SQL
    assert "avg_mae_pct" in SQL
