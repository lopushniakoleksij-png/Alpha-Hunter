from __future__ import annotations

import importlib.util
import re
from pathlib import Path


FINGERPRINT_PATH = Path("ops/runtime_release_fingerprint.py")
SQL_PATH = Path("ops/sql/production_deployment_runtime_fingerprint_v03.sql")
WORKFLOW_PATH = Path(
    ".github/workflows/production-deployment-target-sync-v01.yml"
)
PERFORMANCE_PATH = Path("performance_job.py")

SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()
WORKFLOW = WORKFLOW_PATH.read_text(encoding="utf-8")
PERFORMANCE = PERFORMANCE_PATH.read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location(
    "runtime_release_fingerprint",
    FINGERPRINT_PATH,
)
assert spec is not None and spec.loader is not None
runtime_fp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime_fp)


def test_runtime_fingerprint_is_deterministic_sha256():
    first = runtime_fp.compute_runtime_release_fingerprint(Path('.'))
    second = runtime_fp.compute_runtime_release_fingerprint(Path('.'))
    assert first == second
    fingerprint = str(first["runtime_fingerprint_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    assert first["secret_values_included"] is False


def test_runtime_fingerprint_covers_cron_runtime_surface_only():
    result = runtime_fp.compute_runtime_release_fingerprint(Path('.'))
    files = set(result["runtime_files"])
    for required in [
        ".python-version",
        "requirements.txt",
        "config.json",
        "run.py",
        "hourly.py",
        "performance_job.py",
        "feature_job.py",
        "outcome_job.py",
        "ops/collect_execution_quality_readonly.py",
        "ops/collect_candidate_retention_shadow.py",
        "ops/runtime_release_fingerprint.py",
    ]:
        assert required in files
    assert any(path.startswith("alpha_hunter/") for path in files)
    assert not any(path.startswith("ops/sql/") for path in files)
    assert not any(path.startswith(".github/") for path in files)


def test_target_ledger_accepts_runtime_fingerprint():
    assert "add column if not exists runtime_fingerprint_sha256 text" in LOWER
    assert "runtime_fingerprint_sha256 ~ '^[0-9a-f]{64}$'" in LOWER


def test_deployment_guard_prefers_runtime_fingerprint_and_fails_closed():
    assert "runtime_fingerprint" in LOWER
    assert "comparison_mode" in LOWER
    assert "runtime_fingerprint" in LOWER
    assert "then 'runtime_fingerprint'" in LOWER
    assert (
        "when t.target_runtime_fingerprint_sha256 is not null"
        in LOWER
    )
    assert (
        "and l.live_runtime_fingerprint_sha256 is null"
        in LOWER
    )
    assert "then 'drift'" in LOWER
    assert (
        "lower(t.target_runtime_fingerprint_sha256)"
        in LOWER
    )
    assert "=l.live_runtime_fingerprint_sha256" in LOWER
    assert "then 'matched'" in LOWER


def test_legacy_commit_equality_is_only_fallback():
    assert "legacy_exact_git_commit" in LOWER
    assert "when c.live_git_commit=t.target_git_commit" in LOWER


def test_public_v01_view_schema_is_not_expanded():
    segment = LOWER.split(
        "create or replace view public.alpha_hunter_production_deployment_drift_v01",
        1,
    )[1]
    public_select = segment.split("from public.alpha_hunter_production_deployment_runtime_status_v03", 1)[0]
    assert "target_runtime_fingerprint_sha256" not in public_select
    assert "live_runtime_fingerprint_sha256" not in public_select
    for expected in [
        "release_target_id",
        "target_git_commit",
        "live_git_commit",
        "scientific_fingerprint_sha256",
        "deployment_status",
        "deployment_drift",
        "trade_permission",
        "order_path",
    ]:
        assert expected in public_select


def test_target_workflow_computes_and_persists_same_fingerprint():
    assert "python ops/runtime_release_fingerprint.py --github-output" in WORKFLOW
    assert "runtime_fingerprint_sha256" in WORKFLOW
    assert "TARGET_RUNTIME_FINGERPRINT" in WORKFLOW
    for path in [
        "feature_job.py",
        "outcome_job.py",
        "ops/runtime_release_fingerprint.py",
        "ops/collect_candidate_retention_shadow.py",
    ]:
        assert f'- "{path}"' in WORKFLOW


def test_live_performance_telemetry_persists_runtime_fingerprint():
    assert "_runtime_release_fingerprint" in PERFORMANCE
    assert "runtime_release_fingerprint_sha256" in PERFORMANCE
    assert "runtime_release_fingerprint_secret" in PERFORMANCE


def test_no_secret_or_trade_authority_added():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER
