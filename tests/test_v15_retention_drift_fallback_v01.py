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


def test_fallback_is_strictly_deployment_and_recent_run_gated():
    assert 'if status == "MATCHED":' in TEXT
    assert 'elif status == "DRIFT" and recent_pass:' in TEXT
    assert 'elif status == "DRIFT":' in TEXT
    assert "unexpected deployment status" in TEXT
    assert "fail closed" in TEXT
    assert "steps.ownership.outputs.should_run == 'true'" in TEXT
    assert "steps.ownership.outputs.should_run == 'false'" in TEXT
    assert "RECENT_SUCCESSFUL_RETENTION_RUN" in TEXT
    assert "DRIFT_WITHOUT_RECENT_SUCCESS" in TEXT


def test_recent_success_window_is_20_minutes():
    assert "timedelta(minutes=20)" in TEXT
    assert 'result_class == "PASS"' in TEXT
    assert "checked_at_utc,result_class" in TEXT


def test_ownership_check_happens_before_checkout_and_install():
    ownership = TEXT.index("Check fallback ownership")
    checkout = TEXT.index("Checkout production main")
    install = TEXT.index("Install production dependencies")
    assert ownership < checkout < install
    assert "if: steps.ownership.outputs.should_run == 'true'" in TEXT


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


def test_skip_reason_is_explicit():
    assert "V15 retention fallback skipped:" in TEXT
    assert "steps.ownership.outputs.reason" in TEXT
