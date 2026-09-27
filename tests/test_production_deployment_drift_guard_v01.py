from pathlib import Path

SQL_PATH = Path("ops/sql/production_deployment_drift_guard_v01.sql")
WORKFLOW_PATH = Path(
    ".github/workflows/production-deployment-target-sync-v01.yml"
)
SQL = SQL_PATH.read_text(encoding="utf-8").lower()
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8")


def test_deployment_drift_guard_is_ops_only():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "alpha_hunter_production_release_targets_v01" in SQL
    assert "alpha_hunter_production_deployment_drift_v01" in SQL


def test_release_target_ledger_is_append_only_and_service_role_only():
    assert "enable row level security" in SQL
    assert "alpha_hunter_block_append_only_mutation" in SQL
    assert (
        "grant select,insert on table "
        "public.alpha_hunter_production_release_targets_v01"
    ) in SQL
    assert "to service_role" in SQL


def test_deployment_status_is_exact_commit_equality():
    assert "when l.live_git_commit=t.target_git_commit then 'matched'" in SQL
    assert "else 'drift'" in SQL
    assert "deployment_drift" in SQL


def test_no_trade_authority_added():
    for marker in [
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
    ]:
        assert marker in SQL
    for forbidden in [
        "trade_permission=true",
        "trade_permission = true",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer",
    ]:
        assert forbidden not in SQL


def test_workflow_tracks_main_push_without_printing_secrets():
    assert "branches:" in WORKFLOW
    assert "- main" in WORKFLOW
    assert "SUPABASE_URL: ${{ secrets.SUPABASE_URL }}" in WORKFLOW
    assert (
        "SUPABASE_SERVICE_ROLE_KEY: "
        "${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}"
    ) in WORKFLOW
    assert "TARGET_SHA: ${{ github.sha }}" in WORKFLOW
    assert "resolution=ignore-duplicates,return=minimal" in WORKFLOW
    assert 'print("Production release target recorded' in WORKFLOW
    assert 'print(key)' not in WORKFLOW
    assert 'print(os.environ["SUPABASE_SERVICE_ROLE_KEY"])' not in WORKFLOW
