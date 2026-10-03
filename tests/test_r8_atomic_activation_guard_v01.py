from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "ops/sql/r8_atomic_activation_guard_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_r8_atomic_activation_sql_parses():
    assert parse_sql(SQL)


def test_generic_profitability_activation_is_interlocked_for_r8():
    required = [
        "alpha_hunter_guard_r8_profitability_activation_v01",
        "trg_ah_r8_profitability_activation_interlock_v01",
        "before insert on public.alpha_hunter_profitability_test_activations_v01",
        "if v_exec.activation_id is null then",
        "return null;",
    ]
    for marker in required:
        assert marker in LOWER


def test_r8_profitability_activation_must_match_execution_timestamp_and_fingerprint():
    required = [
        "r8 profitability activation timestamp must match paper execution activation",
        "r8 profitability activation fingerprint must match paper execution activation",
        "v_exec.activated_at_utc<>new.started_at_utc",
        "v_exec.scientific_fingerprint_sha256",
        "new.baseline_scientific_fingerprint_sha256",
    ]
    for marker in required:
        assert marker in LOWER


def test_dedicated_activation_uses_one_verified_canonical_baseline():
    required = [
        "alpha_hunter_activate_r8_executed_paper_v01",
        "render_cron",
        "scientific_fingerprint_sha256",
        "configured_strategy_count",
        "total_evaluations",
        "previous_snapshot_context",
        "catalyst_summary",
        "order by p.collected_at_utc",
        "limit 1",
    ]
    for marker in required:
        assert marker in LOWER


def test_dedicated_activation_requires_deployment_truth_match():
    required = [
        "alpha_hunter_production_deployment_runtime_status_v03",
        "r8 production runtime is still in deployment drift",
        "coalesce(v_deploy.deployment_drift,true)",
        "target_runtime_fingerprint_sha256",
        "live_runtime_fingerprint_sha256",
    ]
    for marker in required:
        assert marker in LOWER


def test_execution_cadence_and_profitability_baselines_share_same_timestamp():
    required = [
        "'paper_execution_r8'",
        "v_baseline",
        "'render_cron_aligned_00_20_40'",
        "v_parent.run_id",
        "paper_execution_activation_aligned",
        "cadence_contract_aligned",
    ]
    for marker in required:
        assert marker in LOWER

    assert LOWER.count("v_baseline") >= 8


def test_activation_switches_only_test_engine_evaluator():
    assert "alpha-hunter-test-engine-db-refresh-v02" in LOWER
    assert "private.alpha_hunter_refresh_test_engine_v06_r8()" in LOWER
    assert "schedule:='5,25,45 * * * *'" in LOWER


def test_partial_existing_activation_state_fails_closed():
    assert "r8 partial activation state detected; refusing non-atomic repair" in LOWER
    assert "r8 existing activation rows are misaligned" in LOWER


def test_activation_is_transactional_and_not_auto_scheduled():
    assert LOWER.startswith("begin;")
    assert LOWER.rstrip().endswith("commit;")
    assert "cron.schedule(" not in LOWER
    assert "alpha-hunter-profitability-test-activation-v01-hourly" not in LOWER


def test_no_live_order_authority_is_added():
    required = [
        "paper_only",
        "trade_permission",
        "production_promotion_permitted",
        "order_path",
        "true,false,false,false,'none'",
    ]
    for marker in required:
        assert marker in LOWER

    forbidden = [
        "place_order(",
        "cancel_order(",
        "modify_order(",
        "set_leverage(",
        "trade_permission,true",
        "production_promotion_permitted,true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_historical_evidence_is_not_mutated():
    forbidden = [
        "delete from public.alpha_hunter_paper_",
        "update public.alpha_hunter_paper_",
        "delete from public.alpha_hunter_profitability_",
        "update public.alpha_hunter_profitability_test_activations_v01",
    ]
    for marker in forbidden:
        assert marker not in LOWER
