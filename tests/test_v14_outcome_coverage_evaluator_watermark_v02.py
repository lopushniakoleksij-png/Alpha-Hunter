from pathlib import Path

SOURCE_PATH = Path("ops/sql/v14_outcome_coverage_audit_v01.sql")
MIGRATION_PATH = Path(
    "ops/sql/v14_outcome_coverage_evaluator_watermark_v02.sql"
)
SOURCE = SOURCE_PATH.read_text(encoding="utf-8").lower()
MIGRATION = MIGRATION_PATH.read_text(encoding="utf-8").lower()


def test_latest_successful_forward_evaluator_watermark_is_explicit():
    assert "alpha_hunter_latest_forward_outcome_evaluator_watermark_v01" in SOURCE
    assert "alpha-hunter-strategy-forward-outcome-v01-hourly" in SOURCE
    assert "d.status='succeeded'" in SOURCE
    assert "order by d.start_time desc" in SOURCE


def test_maturity_is_bounded_by_evaluator_start_time():
    assert "evaluator_watermark as" in SOURCE
    assert "c.first_candidate_at_utc+interval '24 hours'" in SOURCE
    assert "<=w.evaluated_through_utc" in SOURCE.replace(" ", "")
    assert "clock_timestamp()-interval '24 hours'" not in SOURCE


def test_heartbeat_function_is_read_only_service_role_accessible():
    assert "security definer" in SOURCE
    assert (
        "grant execute on function "
        "private.alpha_hunter_latest_forward_outcome_evaluator_watermark_v01()"
    ) in SOURCE
    for forbidden in [
        "insert into cron.",
        "update cron.",
        "delete from cron.",
    ]:
        assert forbidden not in SOURCE


def test_no_sealed_evidence_mutation_or_rule_change():
    for forbidden in [
        "insert into public.alpha_hunter_strategy_forward_outcomes_v01",
        "update public.alpha_hunter_strategy_forward_outcomes_v01",
        "delete from public.alpha_hunter_strategy_forward_outcomes_v01",
        "insert into public.alpha_hunter_strategy_paper_economics_v01",
        "update public.alpha_hunter_strategy_paper_economics_v01",
        "delete from public.alpha_hunter_strategy_paper_economics_v01",
        "trade_permission=true",
        "trade_permission = true",
    ]:
        assert forbidden not in MIGRATION
    assert "false as profitability_rule_change_permitted" in MIGRATION
    assert "false as mutation_permitted" in MIGRATION
    assert "false as trade_permission" in MIGRATION


def test_public_audit_view_name_is_preserved():
    assert "create or replace view public.alpha_hunter_v14_outcome_coverage_audit_v01" in MIGRATION
