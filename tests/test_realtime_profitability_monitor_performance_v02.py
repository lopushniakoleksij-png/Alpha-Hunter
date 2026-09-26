from pathlib import Path


SQL = Path("realtime_profitability_monitor_performance_v02.sql").read_text(
    encoding="utf-8"
)
LOWER = SQL.lower()


def test_source_time_and_forward_indexes_exist():
    required = [
        "idx_ah_snapshots_run_source_time_v02",
        "idx_ah_strategy_obs_time_run_status_v02",
        "idx_ah_strategy_outcome_24h_time_episode_v02",
    ]
    for marker in required:
        assert marker in LOWER


def test_monitor_uses_per_spec_lateral_aggregates():
    required = [
        "left join lateral",
        "real_scans_since_registration",
        "real_strategy_observations_since_registration",
        "real_shadow_candidates_since_registration",
        "real_24h_forward_outcomes_since_registration",
        "forward_only_source_isolated",
    ]
    for marker in required:
        assert marker in LOWER


def test_monitor_remains_source_isolated():
    assert (
        "p.payload->'validation_identity'->>'run_source'"
        in SQL
    )
    assert "=s.required_run_source" in LOWER
    assert "true as run_source_isolated" in LOWER


def test_monitor_preserves_paper_only_authority():
    required = [
        "false as historical_replay_counted",
        "false as backtest_counted",
        "true as paper_only",
        "false as live_money_claim_permitted",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]
    for marker in required:
        assert marker in LOWER
