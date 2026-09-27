from pathlib import Path

SQL_PATH = Path("ops/sql/v14_outcome_coverage_audit_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_outcome_coverage_audit_is_ops_only():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "alpha_hunter_v14_outcome_coverage_audit_v01" in LOWER


def test_audit_measures_matured_to_counted_attrition():
    for marker in [
        "matured_candidate_episodes",
        "matured_without_24h_outcome",
        "outcome_24h_rows",
        "complete_enough_24h_rows",
        "incomplete_candle_coverage_24h_rows",
        "completed_paper_economics_rows",
        "matured_to_counted_paper_trade_pct",
    ]:
        assert marker in LOWER


def test_audit_preserves_sealed_evaluator():
    assert "audit_only_no_sealed_evaluator_change" in LOWER
    assert "false as profitability_rule_change_permitted" in LOWER
    assert "false as mutation_permitted" in LOWER


def test_view_is_read_only_and_trade_disabled():
    assert "security_invoker=true" in LOWER
    assert "security_barrier=true" in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER


def test_no_scientific_or_evidence_mutation():
    for forbidden in [
        "insert into public.alpha_hunter_strategy_forward_outcomes_v01",
        "update public.alpha_hunter_strategy_forward_outcomes_v01",
        "delete from public.alpha_hunter_strategy_forward_outcomes_v01",
        "insert into public.alpha_hunter_strategy_paper_economics_v01",
        "update public.alpha_hunter_strategy_paper_economics_v01",
        "delete from public.alpha_hunter_strategy_paper_economics_v01",
        "trade_permission=true",
        "trade_permission = true",
        "place_order",
        "cancel_order",
        "modify_order",
    ]:
        assert forbidden not in LOWER
