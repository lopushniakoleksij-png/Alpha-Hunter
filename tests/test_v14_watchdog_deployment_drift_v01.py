from pathlib import Path

BASE_PATH = Path("ops/sql/v14_control_tower_watchdog_v01.sql")
MIGRATION_PATH = Path("ops/sql/v14_watchdog_deployment_drift_v01.sql")
BASE = BASE_PATH.read_text(encoding="utf-8").lower()
MIGRATION = MIGRATION_PATH.read_text(encoding="utf-8").lower()


def test_watchdog_consumes_deployment_drift_status_internally():
    assert "alpha_hunter_production_deployment_drift_v01" in BASE
    assert "left join deployment d on true" in BASE
    assert "coalesce(d.deployment_drift,false)" in BASE


def test_watchdog_public_schema_is_not_expanded_by_drift_metadata():
    assert "deployment_target_git_commit" not in BASE
    assert "deployment_live_git_commit" not in BASE
    assert "deployment_target_recorded_at_utc" not in BASE


def test_watchdog_surfaces_render_cron_deployment_drift_warning():
    assert "render_cron_deployment_drift" in BASE
    assert "coalesce(d.deployment_drift,false)" in BASE


def test_deployment_drift_is_warning_not_critical():
    critical_segment = BASE.split("as critical_alerts", 1)[0]
    assert "render_cron_deployment_drift" not in critical_segment
    assert "render_cron_deployment_drift" in BASE


def test_explicit_migration_is_ops_only_and_preserves_safety():
    assert MIGRATION_PATH.parent.as_posix() == "ops/sql"
    assert "create or replace view public.alpha_hunter_v14_watchdog_status_v01" in MIGRATION
    assert "security_invoker=true" in MIGRATION
    assert "security_barrier=true" in MIGRATION
    assert "false as trade_permission" in MIGRATION
    assert "false as production_promotion_permitted" in MIGRATION
    assert "'none'::text as order_path" in MIGRATION


def test_no_deployment_or_trading_action_is_added():
    for forbidden in [
        "render api",
        "deploy hook",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in MIGRATION
