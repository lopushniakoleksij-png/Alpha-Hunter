from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github/workflows/render-cron-deploy-v01.yml"
).read_text(encoding="utf-8")


def test_cron_deploy_uses_render_autodeploy_truth_not_redundant_hooks():
    assert "RENDER_CRON_DEPLOY_HOOK_URL" not in WORKFLOW
    assert "secrets.RENDER_DEPLOY_HOOK_URL" not in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW
    assert "Render auto-deployed a release containing the target" in WORKFLOW


def test_cron_deploy_verifies_actual_canonical_cron_scan():
    required = [
        "TARGET_SCIENTIFIC_FINGERPRINT",
        "RENDER_CRON",
        "alpha_hunter_snapshots",
        "collected_at_utc.desc",
        "scientific_fingerprint_sha256",
        "canonical cron did not converge to target science",
        "collected >= not_before",
        'source == "RENDER_CRON"',
        'role == "RENDER_CRON"',
        "target_is_ancestor_of_live(commit)",
        "fingerprint == target",
        '"merge-base", "--is-ancestor"',
    ]
    for marker in required:
        assert marker in WORKFLOW


def test_autodeploy_verification_fails_closed_on_missing_runtime_evidence():
    assert "canonical cron did not converge to target science and target ancestry" in WORKFLOW
    assert "target_is_ancestor_of_live(commit)" in WORKFLOW
    assert 'source == "RENDER_CRON"' in WORKFLOW
    assert 'role == "RENDER_CRON"' in WORKFLOW
    assert "fingerprint == target" in WORKFLOW


def test_workflow_has_no_trading_authority():
    lower = WORKFLOW.lower()
    for forbidden in (
        "place_order(",
        "cancel_order(",
        "modify_order(",
        "set_leverage(",
        "bitget_api_secret",
        "bitget_secret",
        "bitget_passphrase",
    ):
        assert forbidden not in lower


def test_runtime_changes_trigger_cron_deploy():
    for path in (
        '"alpha_hunter/**"',
        '"run.py"',
        '"hourly.py"',
        '"config.json"',
        '"requirements.txt"',
        '".python-version"',
    ):
        assert path in WORKFLOW


def test_cron_verification_waits_long_enough_for_hourly_schedule():
    assert "timeout-minutes: 75" in WORKFLOW
    assert "range(1, 211)" in WORKFLOW
    assert "time.sleep(20)" in WORKFLOW


def test_descendant_ops_only_release_is_allowed_only_with_exact_science():
    assert '["git", "merge-base", "--is-ancestor", target_commit, live_commit]' in WORKFLOW
    assert "fingerprint == target" in WORKFLOW
    assert "fetch-depth: 0" in WORKFLOW
