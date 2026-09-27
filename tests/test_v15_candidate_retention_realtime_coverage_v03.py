from pathlib import Path

SQL_PATH = Path("ops/sql/v15_candidate_retention_realtime_coverage_v03.sql")
SQL = SQL_PATH.read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_realtime_coverage_is_ops_only():
    assert SQL_PATH.parent.as_posix() == "ops/sql"
    assert "alpha_hunter_candidate_retention_realtime_coverage_v03" in LOWER
    assert "alpha_hunter_candidate_retention_realtime_status_v03" in LOWER


def test_realtime_denominator_counts_only_due_closed_candles():
    assert "expected_closed_1h_candles_by_now" in LOWER
    assert "least(clock_timestamp(),t.retention_horizon_end_utc)" in LOWER
    assert "- t.retention_start_utc" in LOWER
    assert "/3600.0" in LOWER
    assert "least(" in LOWER


def test_waiting_and_recently_closed_candles_are_not_labeled_lagging():
    assert "waiting_for_first_due_candle" in LOWER
    assert "complete_to_now" in LOWER
    assert "within_capture_sla" in LOWER
    assert "lagging_capture_sla" in LOWER
    assert "interval '90 minutes'" in LOWER
    assert "expected_capture_due_by_sla" in LOWER
    assert (
        "when j.expected_closed_1h_candles_by_now=0"
        in LOWER
    )


def test_forward_and_total_capture_are_reported_separately():
    assert "retention_coverage_to_date_pct" in LOWER
    assert "forward_first_cycle_coverage_to_date_pct" in LOWER
    assert "late_backfill_rows" in LOWER
    assert "forward_first_cycle_rows" in LOWER


def test_realtime_health_uses_sla_due_candles_not_full_horizon():
    assert "realtime_capture_health" in LOWER
    assert "pass_sla" in LOWER
    assert "degraded_sla" in LOWER
    assert "targets_with_due_candles" in LOWER
    assert "lagging_capture_sla_targets" in LOWER
    assert "retention_coverage_against_sla_due_pct" in LOWER


def test_metric_is_not_profitability_rule_and_v14_excluded():
    assert "ops_realtime_coverage_not_profitability_rule" in LOWER
    assert "false as coverage_metric_is_profitability_rule" in LOWER
    assert "false as counted_in_v14" in LOWER
    assert "false as mutation_permitted" in LOWER
    assert "false as trade_permission" in LOWER
    assert "false as production_promotion_permitted" in LOWER
    assert "'none'::text as order_path" in LOWER


def test_views_are_read_only():
    assert LOWER.count("security_invoker=true") >= 2
    assert LOWER.count("security_barrier=true") >= 2
    for forbidden in [
        "insert into ",
        "update public.",
        "delete from ",
        "truncate ",
        "place_order",
        "cancel_order",
        "modify_order",
    ]:
        assert forbidden not in LOWER
