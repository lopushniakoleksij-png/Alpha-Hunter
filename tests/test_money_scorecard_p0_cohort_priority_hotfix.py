from pathlib import Path


SQL = Path("money_scorecard_p0_cohort_priority_hotfix.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_prioritizes_only_clean_v02_cohort_before_global_due_rows():
    assert "prospective-early-mover-cohort-v0.2" in SQL
    assert "case when exists" in LOWER
    assert "e.scorecard_id = o.scorecard_id" in SQL
    assert "o.horizon_due_at_utc" in SQL
    assert "o.created_at" in SQL


def test_preserves_existing_evaluator_budget_and_does_not_create_second_runner():
    assert "limit 80" in LOWER
    assert "cron.schedule" not in LOWER
    assert "http_get" not in LOWER
    assert "market/candles" not in LOWER


def test_hotfix_is_exact_fail_closed_and_idempotent():
    assert "pg_get_functiondef" in LOWER
    assert "position(v_new in v_def) > 0" in SQL
    assert "ordering clause not found; refusing non-exact hotfix" in SQL
    assert "p0 cohort priority verification failed" in SQL


def test_safety_boundary_is_not_relaxed():
    forbidden = (
        "trade_permission=true",
        "production_execution_enabled=true",
        "place_order",
        "submit_order",
        "create_order",
    )
    for token in forbidden:
        assert token not in LOWER
