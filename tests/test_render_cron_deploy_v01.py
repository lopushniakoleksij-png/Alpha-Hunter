from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (
    ROOT / ".github/workflows/render-cron-deploy-v01.yml"
).read_text(encoding="utf-8")


def test_cron_deploy_uses_dedicated_hook_not_web_hook():
    assert "RENDER_CRON_DEPLOY_HOOK_URL" in WORKFLOW
    assert "RENDER_DEPLOY_HOOK_URL" not in WORKFLOW
    assert "workflow_dispatch:" in WORKFLOW


def test_cron_deploy_verifies_actual_canonical_cron_scan():
    required = [
        "TARGET_SCIENTIFIC_FINGERPRINT",
        "RENDER_CRON",
        "alpha_hunter_snapshots",
        "collected_at_utc.desc",
        "scientific_fingerprint_sha256",
        "canonical cron did not converge to target science",
        "collected >= not_before and fingerprint == target",
    ]
    for marker in required:
        assert marker in WORKFLOW


def test_missing_hook_fails_safe_without_using_wrong_service():
    assert "CRON_DEPLOY_HOOK_NOT_CONFIGURED" in WORKFLOW
    assert "configured=false" in WORKFLOW
    assert "Add the dedicated Render cron deploy hook" in WORKFLOW


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
