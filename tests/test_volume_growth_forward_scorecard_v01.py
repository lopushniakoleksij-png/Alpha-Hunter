from pathlib import Path

SQL = Path("ops/sql/volume_growth_forward_scorecard_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_capture_is_forward_only_latest_run():
    assert "post_preregistration_latest_selection_run_below_5pct" in SQL
    assert "s.selection_run_id=v_selection_run_id" in SQL
    assert "no candidate observed before the preregistered experiment start is admitted" in SQL


def test_capture_requires_pre_move_state():
    assert "abs(s.change_24h_pct)<5.0" in SQL
    assert "check(abs(start_change_24h_pct)<5.0)" in SQL


def test_outcome_is_future_new_5pct_event():
    assert "a.threshold_pct=5.0" in SQL
    assert "a.observed_at_utc>r.observed_at_utc" in SQL
    assert "a.observed_at_utc<=r.maturity_at_utc" in SQL
    assert "first_new_5pct_answer_key_event_after_sub5_capture" in SQL


def test_scorecard_compares_shadow_and_production():
    for marker in [
        "shadow_precision_pct",
        "production_precision_pct",
        "shadow_only_precision_pct",
        "production_only_precision_pct",
    ]:
        assert marker in SQL


def test_scheduled_away_from_core_minutes():
    assert "'6,31,51 * * * *'" in SQL


def test_no_production_or_trade_authority():
    assert "production_selector_changed',false" in SQL
    assert "production_promotion_permitted',false" in SQL
    assert "trade_permission',false" in SQL
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
    ]:
        assert forbidden not in SQL


def test_experiment_has_explicit_preregistration_boundary():
    assert "alpha_hunter_volume_growth_forward_specs_v01" in SQL
    assert "vg-forward-top30-v01" in SQL
    assert "experiment_started_at_utc" in SQL
    assert "s.observed_at_utc>=v_experiment_started_at_utc" in SQL
