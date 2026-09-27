from pathlib import Path

PATH = Path("ops/sql/v15_retention_outcome_recovery_audit_v01.sql")
SQL = PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_recovery_audit_is_ops_only():
    assert PATH.parent.as_posix() == "ops/sql"
    assert "alpha_hunter_v15_retention_outcome_recovery_v01" in LOWER
    assert "alpha_hunter_v15_retention_outcome_recovery_status_v01" in LOWER


def test_audit_compares_v15_retention_with_v14_24h_outcomes():
    assert "alpha_hunter_candidate_retention_shadow_targets_v02" in LOWER
    assert "alpha_hunter_candidate_retention_shadow_candles_v01" in LOWER
    assert "alpha_hunter_candidate_retention_timing_v01" in LOWER
    assert "alpha_hunter_strategy_forward_outcomes_v01" in LOWER
    assert "where o.horizon_hours=24" in LOWER


def test_forward_recovery_requires_full_forward_first_cycle_coverage():
    assert "forward_retention_recovery_proven" in LOWER
    assert "j.forward_first_cycle_rows>=j.expected_closed_1h_candles" in LOWER
    assert "retention_forward_full_coverage" in LOWER


def test_backfill_is_diagnostic_only():
    assert "backfill_recovery_diagnostic_only" in LOWER
    assert "j.late_backfill_rows>0" in LOWER
    assert "backfill_recovery_diagnostic_rows" in LOWER


def test_v14_complete_and_incomplete_are_separated():
    assert "v14_already_complete" in LOWER
    assert "v14_complete_enough" in LOWER
    assert "v14_incomplete_canonical_candle_coverage" in LOWER


def test_forward_and_backfill_recovery_are_reported_separately():
    assert "forward_recovery_proven_rows" in LOWER
    assert "backfill_recovery_diagnostic_rows" in LOWER
    assert "forward_recovery_evidence_present" in LOWER
    assert "backfill_recovery_only" in LOWER


def test_no_v14_counting_or_profitability_rule_change():
    assert "false as counted_in_v14" in LOWER
    assert "false as profitability_rule_change_permitted" in LOWER
    assert "false as mutation_permitted" in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER


def test_views_are_read_only():
    assert LOWER.count("security_invoker=true") >= 2
    assert LOWER.count("security_barrier=true") >= 2
    for forbidden in [
        "insert into public.alpha_hunter_strategy_forward_outcomes_v01",
        "update public.alpha_hunter_strategy_forward_outcomes_v01",
        "delete from public.alpha_hunter_strategy_forward_outcomes_v01",
        "insert into public.alpha_hunter_strategy_paper_economics_v01",
        "update public.alpha_hunter_strategy_paper_economics_v01",
        "delete from public.alpha_hunter_strategy_paper_economics_v01",
        "place_order",
        "cancel_order",
        "modify_order",
    ]:
        assert forbidden not in LOWER
