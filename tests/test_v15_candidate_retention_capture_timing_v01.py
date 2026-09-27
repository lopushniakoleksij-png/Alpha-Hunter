from pathlib import Path

SQL_PATH = Path("ops/sql/v15_candidate_retention_capture_timing_v01.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_capture_timing_audit_is_ops_only():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "alpha_hunter_candidate_retention_timing_v01" in LOWER
    assert "alpha_hunter_candidate_retention_timing_status_v01" in LOWER


def test_timing_classes_distinguish_prompt_capture_from_backfill():
    assert "forward_first_cycle" in LOWER
    assert "late_backfill" in LOWER
    assert "interval '90 minutes'" in LOWER
    assert "capture_lag_minutes" in LOWER


def test_90_minute_boundary_is_not_profitability_rule():
    assert "ops_sla_90_minutes_not_profitability_rule" in LOWER
    assert "false as timing_class_is_profitability_rule" in LOWER


def test_v14_exclusion_and_safety_are_hard_coded():
    assert "false as counted_in_v14" in LOWER
    assert "false as mutation_permitted" in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER


def test_audit_is_read_only():
    assert "security_invoker=true" in LOWER
    assert "security_barrier=true" in LOWER
    for forbidden in [
        "insert into public.alpha_hunter_candidate_retention_shadow_candles_v01",
        "update public.alpha_hunter_candidate_retention_shadow_candles_v01",
        "delete from public.alpha_hunter_candidate_retention_shadow_candles_v01",
        "truncate ",
        "place_order",
        "cancel_order",
        "modify_order",
    ]:
        assert forbidden not in LOWER


def test_status_reports_forward_and_backfill_coverage_separately():
    assert "total_retention_coverage_pct" in LOWER
    assert "forward_first_cycle_coverage_pct" in LOWER
    assert "backfill_only" in LOWER
    assert "forward_capture_present" in LOWER
