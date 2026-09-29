from pathlib import Path


SQL = Path("ops/sql/cron_pressure_relief_v01.sql").read_text(
    encoding="utf-8"
).lower()
WORKFLOW = Path(
    ".github/workflows/production-deployment-target-sync-v01.yml"
).read_text(encoding="utf-8")


def test_cron_relief_changes_schedules_only():
    assert "cron.alter_job" in SQL
    for forbidden in [
        "cron.unschedule",
        "delete from",
        "update public.",
        "insert into public.",
        "trade_permission=true",
        "trade_permission = true",
        "minimum_execution",
        "minimum_reward_risk",
    ]:
        assert forbidden not in SQL


def test_test_engine_and_activation_cadence_are_reduced():
    assert "alpha_hunter_refresh_test_engine_v02" in SQL
    assert "schedule := '2 * * * *'" in SQL
    assert "alpha-hunter-profitability-test-activation-v01-hourly" in SQL
    assert "schedule := '6 * * * *'" in SQL


def test_control_plane_stages_are_spread_without_command_changes():
    expected = {
        "alpha-hunter-big-mover-shadow-hourly": "10 * * * *",
        "alpha-hunter-big-mover-parent-direction-hourly": "16 * * * *",
        "alpha-hunter-big-mover-money-entry-bridge-hourly": "21 * * * *",
        "alpha-hunter-money-entry-stage-hourly": "24 * * * *",
        "alpha-hunter-big-mover-money-scorecard-hourly": "29 * * * *",
        "alpha-hunter-execution-cost-evidence-hourly": "33 * * * *",
        "alpha-hunter-portfolio-risk-veto-hourly": "39 * * * *",
        "alpha-hunter-control-plane-finalize-hourly": "43 * * * *",
    }
    for job, schedule in expected.items():
        assert job in SQL
        assert schedule in SQL
    assert "command :=" not in SQL


def test_release_target_sync_retries_transient_supabase_failures():
    assert "max_attempts = 4" in WORKFLOW
    assert "retry_delays = (5, 10, 20)" in WORKFLOW
    assert "urlopen(request, timeout=30)" in WORKFLOW
    assert "urllib.error.httpError".lower() in WORKFLOW.lower()
    assert "socket.timeout" in WORKFLOW
    assert "ops/collect_v15_ranking_challenger.py" in WORKFLOW


def test_release_sync_preserves_fail_closed_final_outcome():
    assert "raise SystemExit" in WORKFLOW
    assert "resolution=ignore-duplicates,return=minimal" in WORKFLOW
