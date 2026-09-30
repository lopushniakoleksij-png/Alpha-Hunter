from pathlib import Path

SQL = Path("ops/sql/strict_trade_confidence_shadow_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_uses_path_aware_triggered_trade_outcomes():
    assert "target_first" in SQL
    assert "stop_first" in SQL
    assert "open_at_horizon" in SQL
    assert "triggered_execute_now" in SQL
    assert "triggered_limit" in SQL
    assert "path_aware_triggered_24h_gross_win" in SQL


def test_historical_cutoff_is_frozen():
    assert "2026-09-28 00:00:00+00" in SQL
    assert "first_observed_at_utc<v_spec.historical_cutoff_utc" in SQL


def test_requires_minimum_sample_or_marks_insufficient():
    assert "minimum_exact_sample" in SQL
    assert "minimum_base_sample" in SQL
    assert "insufficient_sample" in SQL
    assert "insufficient_evidence" in SQL


def test_reports_wilson_uncertainty():
    assert "wilson_95" in SQL
    assert "lower_95_pct" in SQL
    assert "upper_95_pct" in SQL
    assert "z_score_95" in SQL


def test_65_75_is_research_band_not_permission():
    assert "point_estimate_in_65_75_band_not_validated" in SQL
    assert "paper_eligible boolean not null default false" in SQL
    assert "paper_order_permission boolean not null default false" in SQL


def test_shadow_engine_has_no_execution_authority():
    for marker in [
        "trade_permission boolean not null default false",
        "threshold_change_permitted boolean not null default false",
        "production_promotion_permitted boolean not null default false",
        "order_path text not null default 'none'",
    ]:
        assert marker in SQL

    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "paper_eligible=true",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL


def test_cron_is_lightweight_hourly_research():
    assert "alpha-hunter-strict-trade-confidence-shadow-v01" in SQL
    assert "'12 * * * *'" in SQL
