from pathlib import Path

SQL = Path("ops/sql/cost_to_risk_forward_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_forward_boundary_and_no_backfill():
    assert "registered_at_utc" in SQL
    assert "f.frozen_at_utc>=v_spec.registered_at_utc" in SQL
    assert "no execution freeze before registered_at_utc is admitted" in SQL


def test_only_first_shadow_candidate_is_admitted():
    assert "so.status='shadow_candidate'" in SQL
    assert "from public.alpha_hunter_strategy_observations_v01 earlier" in SQL
    assert "earlier.observed_at_utc<so.observed_at_utc" in SQL


def test_cost_floor_is_expressed_in_r():
    assert "floor_median_bps/c.stop_distance_bps" in SQL
    assert "floor_p90_bps/c.stop_distance_bps" in SQL
    assert "floor_cost_r_median" in SQL
    assert "floor_cost_r_p90" in SQL


def test_exact_24h_outcome_binding_is_required():
    assert "o.horizon_hours=24" in SQL
    assert "o.first_candidate_at_utc=c.decision_observed_at_utc" in SQL
    assert "o.first_candidate_action=c.action" in SQL
    assert "complete_enough" in SQL
    assert "o.ordering_ambiguous=false" in SQL


def test_floor_adjusted_r_is_not_called_realistic_net_r():
    assert "descriptive_observed_fee_spread_floor_only" in SQL
    assert "realistic_net_r_claim_permitted boolean not null default false" in SQL
    assert "'validated_cost_model',false" in SQL
    assert "'slippage_included',false" in SQL
    assert "'latency_included',false" in SQL


def test_no_trade_or_production_authority():
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "production_promotion_permitted=true",
        "realistic_net_r_claim_permitted=true",
    ]:
        assert forbidden not in SQL


def test_hourly_cron_uses_free_minute():
    assert "'13 * * * *'" in SQL
    assert "alpha-hunter-cost-to-risk-forward-v01" in SQL
