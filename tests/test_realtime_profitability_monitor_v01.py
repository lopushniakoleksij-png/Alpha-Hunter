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
