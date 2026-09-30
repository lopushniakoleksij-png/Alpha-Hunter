from pathlib import Path

SQL = Path("ops/sql/t0_threshold_forward_holdout_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_t0_candidate_is_draft_only():
    assert "'me-thresh-t0-holdout-20260930-v01'" in SQL
    assert "'draft'" in SQL
    assert "0.125" in SQL
    assert "5.0" in SQL
    assert "'not_estimable'" in SQL
    assert "validated_at_utc,activated_at_utc" in SQL
    assert "null,null" in SQL


def test_forward_only_no_backfill():
    assert "new.candidate_at_utc<v_spec.registered_at_utc" in SQL
    assert "after insert on public.alpha_hunter_big_mover_money_scorecard_candidates" in SQL
    assert "no historical scorecard candidate is inserted or backfilled" in SQL


def test_candidate_group_uses_only_candidate_time_fields():
    assert "future_outcome_used_for_group_assignment',false" in SQL
    assert "new.initial_remaining_r>=v_spec.min_t0_remaining_r" in SQL
    assert "new.risk_distance_pct<=v_spec.max_t0_stop_distance_pct" in SQL


def test_confirmatory_sample_and_effect_are_frozen():
    assert "320,1700,14,50,120,80" in SQL
    assert "0.10,0.05,0.80" in SQL
    assert "mean_path_r_pre_cost_test_minus_control" in SQL


def test_evaluator_requires_sample_gate():
    assert "sample_gate_not_ready" in SQL
    assert "v_delta>=v_spec.minimum_effect_delta_r" in SQL
    assert "v_test_lower95>0" in SQL
    assert "v_long_avg>0" in SQL
    assert "v_short_avg>0" in SQL


def test_pass_cannot_activate_thresholds():
    assert "threshold_activation_permitted boolean not null default false" in SQL
    assert "'threshold_table_status_after_evaluation','draft'" in SQL
    assert "this script does not set threshold status to validated or active" in SQL


def test_no_trade_or_order_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "threshold_activation_permitted=true",
        "production_promotion_permitted=true",
        "realistic_net_r_claim_permitted=true",
    ]:
        assert forbidden not in SQL


def test_outcome_capture_uses_24h_scorecard_outcome():
    assert "o.horizon_hours=24" in SQL
    assert "o.scorecard_id=c.scorecard_id" in SQL
    assert "path_r_pre_cost" in SQL


def test_cron_uses_free_minute():
    assert "'56 * * * *'" in SQL
