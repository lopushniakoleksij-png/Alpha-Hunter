from pathlib import Path

PATH = Path(".github/workflows/v15-retention-drift-fallback-v01.yml")
TEXT = PATH.read_text(encoding="utf-8")
LOWER = TEXT.lower()


def test_fallback_runs_hourly_and_bootstraps_on_its_own_merge():
    assert 'cron: "8 * * * *"' in TEXT
    assert "push:" in TEXT
    assert "- main" in TEXT
    assert (
        '- ".github/workflows/v15-retention-drift-fallback-v01.yml"'
        in TEXT
    )


def test_fallback_is_strictly_deployment_drift_gated():
    assert 'if status == "DRIFT":' in TEXT
    assert 'elif status == "MATCHED":' in TEXT
    assert "unexpected deployment status" in TEXT
    assert "fail closed" in TEXT
    assert "steps.drift.outputs.should_run == 'true'" in TEXT
    assert "steps.drift.outputs.should_run == 'false'" in TEXT


def test_fallback_runs_only_targeted_retention_collector():
    assert "python ops/collect_candidate_retention_shadow.py" in TEXT
    for forbidden in [
        "python run.py",
        "python hourly.py",
        "run.py --",
        "hourly.py --",
        "universe discovery",
    ]:
        assert forbidden not in LOWER


def test_no_private_bitget_or_order_authority():
    for forbidden in [
        "BITGET_API_KEY",
        "BITGET_SECRET_KEY",
        "BITGET_API_PASSPHRASE",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer",
    ]:
        assert forbidden not in TEXT


def test_supabase_secrets_are_used_without_printing_values():
    assert "SUPABASE_URL: ${{ secrets.SUPABASE_URL }}" in TEXT
    assert (
        "SUPABASE_SERVICE_ROLE_KEY: "
        "${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}"
    ) in TEXT
    assert "print(key)" not in TEXT
    assert 'print(os.environ["SUPABASE_SERVICE_ROLE_KEY"])' not in TEXT


def test_matched_runtime_explicitly_skips_fallback():
    assert (
        'echo "Render runtime is MATCHED; fallback collector skipped."'
        in TEXT
    )
