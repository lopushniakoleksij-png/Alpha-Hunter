from pathlib import Path

SQL_PATH = Path("ops/sql/control_plane_stage_spacing_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_control_plane_spacing_is_outside_v14_fingerprint():
    assert SQL_PATH.parent.as_posix() == "ops/sql"


def test_stage_schedule_has_runtime_margin():
    expected = {
        "alpha-hunter-big-mover-shadow-hourly": "10 * * * *",
        "alpha-hunter-big-mover-parent-direction-hourly": "13 * * * *",
        "alpha-hunter-big-mover-money-entry-bridge-hourly": "14 * * * *",
        "alpha-hunter-money-entry-stage-hourly": "15 * * * *",
        "alpha-hunter-big-mover-money-scorecard-hourly": "16 * * * *",
        "alpha-hunter-execution-cost-evidence-hourly": "17 * * * *",
        "alpha-hunter-portfolio-risk-veto-hourly": "18 * * * *",
        "alpha-hunter-control-plane-finalize-hourly": "20 * * * *",
    }
    for job, schedule in expected.items():
        assert f"'{job}'" in SQL
        assert f"'{schedule}'" in SQL


def test_stage_commands_are_preserved():
    required = [
        "alpha_hunter_run_controlled_stage('ANSWER_KEY',clock_timestamp())",
        "alpha_hunter_run_controlled_stage('PARENT_DIRECTION',clock_timestamp())",
        "alpha_hunter_run_controlled_stage('MONEY_ENTRY_BRIDGE',clock_timestamp())",
        "alpha_hunter_run_money_entry_stage_with_geometry(clock_timestamp())",
        "alpha_hunter_run_controlled_stage('MONEY_SCORECARD',clock_timestamp())",
        "alpha_hunter_run_controlled_stage('COST_EVIDENCE',clock_timestamp())",
        "alpha_hunter_run_controlled_stage('PORTFOLIO_RISK',clock_timestamp())",
        "alpha_hunter_finalize_control_plane_hour(clock_timestamp())",
    ]
    for marker in required:
        assert marker in SQL


def test_no_gate_or_trade_permission_changes():
    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled=true",
        "production_execution_enabled = true",
        "alter function private.alpha_hunter_run_controlled_stage",
        "create or replace function private.alpha_hunter_run_controlled_stage",
        "active_validated_cost_model",
        "active_validated_risk_policy",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_old_unsafe_parent_and_bridge_minutes_are_not_rescheduled():
    assert "'alpha-hunter-big-mover-parent-direction-hourly',\n    '11 * * * *'" not in SQL
    assert "'alpha-hunter-big-mover-money-entry-bridge-hourly',\n    '12 * * * *'" not in SQL
