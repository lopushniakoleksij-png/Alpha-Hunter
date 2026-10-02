from pathlib import Path

SQL = Path(
    "ops/sql/profit_management_shadow_challenger_v01.sql"
).read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_challengers_reuse_existing_lifecycle_milestones():
    required = [
        "BE_AFTER_3PCT",
        "LOCK_25_AFTER_5PCT",
        "LOCK_50_AFTER_5PCT",
        "EXISTING_LIFECYCLE_3PCT_MILESTONE",
        "EXISTING_LIFECYCLE_5PCT_MILESTONE",
    ]
    for marker in required:
        assert marker in SQL


def test_running_favorable_path_is_direction_correct():
    required = [
        "when e.direction='LONG' then",
        "max(p.mark_price) over",
        "else",
        "min(p.mark_price) over",
        "100.0 * (s.running_favorable_mark-s.opening_vwap)",
        "100.0 * (s.opening_vwap-s.running_favorable_mark)",
    ]
    for marker in required:
        assert marker in SQL


def test_shadow_stop_is_monotonic_fraction_of_running_favorable_move():
    required = [
        "s.opening_vwap",
        "p.lock_fraction*(s.running_favorable_mark-s.opening_vwap)",
        "p.lock_fraction*(s.opening_vwap-s.running_favorable_mark)",
        "shadow_stop_price",
    ]
    for marker in required:
        assert marker in SQL


def test_trigger_requires_observed_canonical_mark_cross():
    required = [
        "c.mark_price <= c.shadow_stop_price",
        "c.mark_price >= c.shadow_stop_price",
        "OBSERVED_CANONICAL_MARK_CROSS",
        "sampled_mark_used_as_shadow_exit",
        "sampled_path_limitation",
    ]
    for marker in required:
        assert marker in SQL


def test_shadow_exit_does_not_invent_stop_fill():
    assert "then t.shadow_trigger_observed_mark" in SQL
    assert "shadow_stop_at_trigger" in SQL
    assert "shadow_exit_price" in SQL


def test_counterfactual_cost_and_net_claims_are_withheld():
    required = [
        "false as counterfactual_fee_claim_permitted",
        "false as counterfactual_funding_claim_permitted",
        "false as counterfactual_net_pnl_claim_permitted",
    ]
    for marker in required:
        assert marker in SQL


def test_minimum_cohort_gate_blocks_small_sample_promotion():
    required = [
        "30::bigint as minimum_total_episode_gate",
        "10::bigint as minimum_per_direction_gate",
        "INSUFFICIENT_TOTAL_COHORT",
        "INSUFFICIENT_LONG_COHORT",
        "INSUFFICIENT_SHORT_COHORT",
        "MINIMUM_COHORT_MET_REQUIRES_FORWARD_VALIDATION",
        "false as statistical_validation_claim_permitted",
        "false as production_superiority_claim_permitted",
    ]
    for marker in required:
        assert marker in SQL


def test_no_live_management_or_exchange_authority():
    required = [
        "false as management_change_permitted",
        "false as stop_change_permitted",
        "false as target_change_permitted",
        "false as promotion_permitted",
        "false as trade_permission",
        "'NONE'::text as order_path",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "api.bitget.com",
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "withdraw",
        "transfer(",
        "trade_permission=true",
        "trade_permission = true",
        "promotion_permitted=true",
        "promotion_permitted = true",
        "management_change_permitted=true",
        "stop_change_permitted=true",
        "target_change_permitted=true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_views_are_service_role_read_only():
    for view in [
        "alpha_hunter_profit_management_shadow_v01",
        "alpha_hunter_profit_management_shadow_status_v01",
    ]:
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER
        assert f"grant insert on public.{view}" not in LOWER
        assert f"grant update on public.{view}" not in LOWER
        assert f"grant delete on public.{view}" not in LOWER
