from pathlib import Path

SQL_PATH = Path("ops/sql/control_plane_stage_latency_monitor_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_stage_latency_monitor_is_ops_only():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "alpha_hunter_control_plane_stage_runtime_samples_v01" in LOWER
    assert "alpha_hunter_control_plane_stage_latency_status_v01" in LOWER


def test_runtime_samples_are_append_only_and_service_role_only():
    assert "enable row level security" in LOWER
    assert "alpha_hunter_block_append_only_mutation" in LOWER
    assert (
        "grant select,insert on table "
        "public.alpha_hunter_control_plane_stage_runtime_samples_v01"
    ) in LOWER
    assert "to service_role" in LOWER


def test_timeout_detection_is_explicit():
    assert "statement timeout" in LOWER
    assert "timeout_detected" in LOWER
    assert "result_class='timeout'" in LOWER


def test_exact_seven_control_plane_stages_are_sampled():
    for stage in [
        "answer_key",
        "parent_direction",
        "money_entry_bridge",
        "money_entry_stage",
        "money_scorecard",
        "cost_evidence",
        "portfolio_risk",
    ]:
        assert stage in LOWER
    assert "count(*)=7" in LOWER


def test_capture_runs_at_22_each_hour():
    assert "alpha-hunter-control-plane-stage-runtime-hourly-v01" in SQL
    assert "'22 * * * *'" in SQL


def test_monitor_does_not_change_stage_commands_or_trade_authority():
    for forbidden in [
        "alter function private.alpha_hunter_run_controlled_stage",
        "create or replace function private.alpha_hunter_run_controlled_stage",
        "cron.schedule(\n    'alpha-hunter-big-mover-shadow-hourly'",
        "cron.schedule(\n    'alpha-hunter-big-mover-parent-direction-hourly'",
        "place_order",
        "cancel_order",
        "modify_order",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in LOWER
    assert "false as trade_permission" in LOWER
    assert "'none'::text as order_path" in LOWER



def test_scheduled_capture_uses_current_hour_but_seed_uses_previous_completed_hour():
    assert (
        "$cmd$select private.alpha_hunter_capture_control_plane_stage_runtime_v01("
        "clock_timestamp());$cmd$"
    ) in SQL
    assert (
        "date_trunc('hour',clock_timestamp())-interval '1 second'"
    ) in SQL
