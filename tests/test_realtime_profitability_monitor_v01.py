from pathlib import Path


SQL = Path("realtime_profitability_monitor_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_monitor_uses_real_clock_and_forward_registration_boundary():
    assert "clock_timestamp()" in SQL
    assert "preregistered_at_utc" in SQL
    assert "FORWARD_ONLY_FROM_REGISTRATION" in SQL
    assert "REAL_PRODUCTION_TIMESTAMPS" in SQL


def test_monitor_does_not_count_backtests_or_replays():
    assert "false as historical_replay_counted" in LOWER
    assert "false as backtest_counted" in LOWER


def test_monitor_reports_live_scan_freshness_and_identity():
    required = [
        "latest_live_scan_at_utc",
        "latest_live_scan_age_seconds",
        "latest_live_git_commit",
        "latest_live_config_sha256",
        "previous_snapshot_source",
        "catalyst_version",
        "configured_strategy_count",
    ]
    for marker in required:
        assert marker in SQL


def test_monitor_reports_only_post_registration_evidence():
    assert "p.collected_at_utc>=s.preregistered_at_utc" in SQL
    assert "o.observed_at_utc>=s.preregistered_at_utc" in SQL
    assert "f.first_observed_at_utc>=s.preregistered_at_utc" in SQL


def test_monitor_never_grants_execution_authority():
    required = [
        "true as paper_only",
        "false as live_money_claim_permitted",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'NONE'::text as order_path",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "trade_permission = true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_monitor_avoids_cartesian_join_between_scans_observations_and_outcomes():
    assert "scan_counts as (" in LOWER
    assert "observation_counts as (" in LOWER
    assert "outcome_counts as (" in LOWER
    forbidden = (
        "left join public.alpha_hunter_snapshots p\n    on p.collected_at_utc>=s.preregistered_at_utc\n  left join public.alpha_hunter_strategy_observations_v01 o",
        "left join public.alpha_hunter_strategy_observations_v01 o\n    on o.observed_at_utc>=s.preregistered_at_utc\n  left join public.alpha_hunter_strategy_forward_outcomes_v01 f",
    )
    for marker in forbidden:
        assert marker not in LOWER


def test_monitor_has_time_indexes_for_forward_only_counts():
    required = [
        "idx_ah_snapshots_collected_at_realtime_v01",
        "idx_ah_strategy_obs_observed_at_realtime_v01",
        "idx_ah_strategy_forward_observed_horizon_realtime_v01",
    ]
    for marker in required:
        assert marker in LOWER


def test_monitor_exposes_only_the_latest_preregistered_spec():
    spec_cte = LOWER.split("with spec as (", 1)[1].split("),\nlatest_scan as (", 1)[0]
    assert "order by s.preregistered_at_utc desc" in spec_cte
    assert "limit 1" in spec_cte
