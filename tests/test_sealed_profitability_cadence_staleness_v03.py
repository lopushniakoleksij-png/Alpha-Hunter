from pathlib import Path

SQL = Path("sealed_profitability_cadence_staleness_v03.sql").read_text(
    encoding="utf-8"
).lower()


def test_stale_scanner_is_explicit_failure():
    assert "fail_scan_stale" in SQL
    assert "latest_counted_scan_at_utc" in SQL
    assert "maximum_interval_minutes*interval '1 minute'" in SQL


def test_staleness_is_source_scoped():
    assert "required_run_source" in SQL
    assert "validation_identity" in SQL
    assert "run_source" in SQL


def test_cadence_fix_is_audit_only():
    assert "true as audit_only" in SQL
    assert "true as paper_only" in SQL
    assert "false as trade_permission" in SQL
    assert "false as production_promotion_permitted" in SQL
    assert "'none'::text as order_path" in SQL
