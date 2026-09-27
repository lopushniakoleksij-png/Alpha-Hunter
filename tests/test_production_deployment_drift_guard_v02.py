from pathlib import Path

PATH = Path("ops/sql/production_deployment_drift_guard_v02.sql")
SQL = PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_runtime_sources_are_added_without_deleting_history():
    assert "github_main_push" in LOWER
    assert "manual_audit" in LOWER
    assert "github_runtime_push" in LOWER
    assert "manual_runtime_target" in LOWER
    assert "delete from public.alpha_hunter_production_release_targets_v01" not in LOWER


def test_view_filters_to_runtime_targets_only():
    assert (
        "where r.source in ('github_runtime_push','manual_runtime_target')"
        in LOWER
    )
    assert "no_runtime_target" in LOWER


def test_current_canonical_render_commit_seeds_runtime_baseline():
    assert "runtime-baseline-" in LOWER
    assert "manual_runtime_target" in LOWER
    assert "run_source'='render_cron'" in LOWER.replace(" ", "")
    assert "validation_identity'->>'git_commit'" in LOWER


def test_exact_commit_equality_still_defines_drift():
    assert "when l.live_git_commit=t.target_git_commit then 'matched'" in LOWER
    assert "l.live_git_commit<>t.target_git_commit" in LOWER


def test_no_deployment_action_or_trade_authority_added():
    for forbidden in [
        "deploy hook",
        "render api",
        "place_order",
        "cancel_order",
        "modify_order",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER
