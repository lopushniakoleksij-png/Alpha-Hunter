from pathlib import Path

from pglast import parse_sql


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "ops/sql/sealed_profitability_r8_executed_paper_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_r8_executed_paper_protocol_sql_parses():
    assert parse_sql(SQL)


def test_r8_preregistration_freezes_exact_scientific_identity():
    required = [
        "sealed-arch-v14r8-exec-paper-fp-20m-20261003",
        "sealed-profitability-v0.5-r8-executed-paper-integrity",
        "4f45f9d9ba343eccbbf8e4d49fe13a163ec7f2c8",
        "176b271ab6fe8b1905bfeb5118be77b6183cad6311925795cd912a7b055b99d1",
        "'render_cron'",
        "30",
        "100",
        "1.96",
    ]
    for marker in required:
        assert marker in LOWER


def test_preregistration_does_not_activate_r8_or_start_cron():
    forbidden = [
        "insert into public.alpha_hunter_profitability_test_activations_v01",
        "insert into public.alpha_hunter_paper_execution_integrity_activation_v08",
        "cron.alter_job",
        "cron.schedule",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_r8_sample_is_actual_clean_completed_paper_ledger():
    assert "alpha_hunter_paper_completed_trades_valid_v08" in LOWER
    assert "alpha_hunter_paper_completed_trades_quarantine_v08" in LOWER
    assert "alpha_hunter_strategy_paper_economics_v01" not in LOWER
    assert "paper_net_pnl_ex_funding" in LOWER
    assert "net_r_ex_funding" in LOWER
    assert "gross_r" in LOWER


def test_quarantine_nonzero_invalidates_instead_of_silent_exclusion():
    required = [
        "r8_completed_trade_quarantine_nonzero",
        "invalidated_by_r8_execution_integrity_defect",
        "quarantine_nonzero_invalidates_cohort",
        "v_quarantined>0",
    ]
    for marker in required:
        assert marker in LOWER


def test_r8_requires_one_exposure_guard_and_clean_monitoring_contract():
    required = [
        "alpha_hunter_paper_execution_integrity_status_v08",
        "duplicate_active_exposure_groups",
        "one_exposure_guard_integrity_ok",
        "r8_duplicate_active_exposure_detected",
        "r8_one_exposure_guard_integrity_failed",
        "cadence_integrity_failed",
    ]
    for marker in required:
        assert marker in LOWER


def test_r8_fingerprint_drift_fails_closed():
    required = [
        "live_scientific_fingerprint_mismatch",
        "r8_scientific_fingerprint_drift",
        "invalidated_by_r8_scientific_fingerprint_drift",
        "frozen_scientific_fingerprint_sha256",
    ]
    for marker in required:
        assert marker in LOWER


def test_profitability_math_is_actual_paper_net_ex_funding():
    required = [
        "avg(t.net_r_ex_funding)",
        "stddev_samp(t.net_r_ex_funding)",
        "paper_net_r_ex_funding_lower_95",
        "paper_net_r_ex_funding_profit_factor",
        "clean_win_rate_pct",
        "paper_total_net_pnl_ex_funding_usdt",
    ]
    for marker in required:
        assert marker in LOWER


def test_full_profitability_claim_still_requires_validated_cost_model():
    required = [
        "alpha_hunter_execution_cost_validation_readiness_v04",
        "full_cost_validation_evidence_complete",
        "cost_model_activation_permitted",
        "realistic_net_r_claim_permitted",
        "validated_execution_cost_model_missing",
        "paper_execution_edge_ex_funding_observed_cost_model_blocked",
    ]
    for marker in required:
        assert marker in LOWER


def test_r8_test_engine_remains_paper_only_and_trade_disabled():
    required = [
        "false as live_money_claim_permitted",
        "false as trade_permission",
        "false as production_promotion_permitted",
        "'none'::text as order_path",
        "false,false,false,false,'none'",
    ]
    for marker in required:
        assert marker in LOWER


def test_r8_protocol_preserves_historical_evidence():
    forbidden = [
        "delete from public.alpha_hunter_paper_",
        "update public.alpha_hunter_paper_",
        "delete from public.alpha_hunter_profitability_",
        "update public.alpha_hunter_profitability_test_specs_v01",
        "update public.alpha_hunter_profitability_test_activations_v01",
    ]
    for marker in forbidden:
        assert marker not in LOWER
