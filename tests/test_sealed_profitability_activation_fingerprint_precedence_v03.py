from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
BASE = (
    ROOT / "ops/sql/sealed_profitability_activation_guard_v02.sql"
).read_text(encoding="utf-8")
MIGRATION = (
    ROOT / "ops/sql/sealed_profitability_activation_fingerprint_precedence_v03.sql"
).read_text(encoding="utf-8")


def test_activation_guard_and_migration_parse():
    assert parse_sql(BASE)
    assert parse_sql(MIGRATION)


def test_fingerprint_enabled_specs_do_not_require_exact_git_match():
    lower = MIGRATION.lower()
    assert "frozen_scientific_fingerprint_sha256 is not null" in lower
    assert "scientific_fingerprint_sha256" in lower
    assert "frozen_scientific_fingerprint_sha256 is null" in lower
    assert "=v_spec.frozen_git_commit" in lower

    fingerprint_branch = lower.index(
        "v_spec.frozen_scientific_fingerprint_sha256 is not null"
    )
    legacy_branch = lower.index(
        "v_spec.frozen_scientific_fingerprint_sha256 is null",
        fingerprint_branch,
    )
    exact_git = lower.index("=v_spec.frozen_git_commit", legacy_branch)
    assert fingerprint_branch < legacy_branch < exact_git


def test_baseline_records_observed_commit_for_diagnostics():
    lower = MIGRATION.lower()
    assert "baseline_observed_git_commit" in lower
    assert "git_anchor_commit" in lower
    assert "identity_mode" in lower
    assert "scientific_fingerprint" in lower
    assert "legacy_exact_git" in lower
    assert "nullif(v_parent.payload->'validation_identity'->>'git_commit','')" in lower


def test_prospective_and_cadence_boundaries_remain_enforced():
    lower = MIGRATION.lower()
    assert "v_spec.preregistered_at_utc" in lower
    assert "baseline_not_before_utc" in lower
    assert "p.collected_at_utc>=v_not_before" in lower
    assert "required_run_source" in lower
    assert "required_strategy_count" in lower
    assert "previous_snapshot_context" in lower
    assert "catalyst_summary" in lower


def test_cron_job_remains_on_same_schedule_and_function():
    lower = MIGRATION.lower()
    assert "alpha-hunter-profitability-test-activation-v01-hourly" in lower
    assert "schedule := '8,38 * * * *'" in lower
    assert (
        "select private.alpha_hunter_try_activate_profitability_test_v02();"
        in lower
    )


def test_no_trade_or_promotion_authority_added():
    lower = MIGRATION.lower()
    assert "'trade_permission',false" in lower
    assert "'production_promotion_permitted',false" in lower
    assert "'order_path','none'" in lower
    assert "place_order(" not in lower
    assert "cancel_order(" not in lower
    assert "modify_order(" not in lower
    assert "set_leverage(" not in lower
