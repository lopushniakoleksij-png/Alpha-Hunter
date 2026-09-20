from pathlib import Path

SQL = Path("roundtrip_outcome_evidence_v01.sql").read_text(encoding="utf-8")
LOWER = SQL.lower()


def test_hedge_mode_direction_and_inventory_semantics_are_explicit():
    required = [
        "when f.side='BUY' then 'LONG'",
        "when f.side='SELL' then 'SHORT'",
        "when e.trade_side='OPEN' then e.base_qty",
        "else -e.base_qty",
        "COMPLETE_FLAT_TO_FLAT",
        "PREWINDOW_POSITION_REQUIRED",
        "INVENTORY_NEGATIVE",
        "OPEN_OR_INCOMPLETE",
    ]
    for marker in required:
        assert marker in SQL


def test_order_identity_is_hashed_and_raw_order_id_not_exposed():
    assert "extensions.digest(f.order_id,'sha256')" in SQL
    assert "order_identity_sha256" in SQL

    event_select = SQL.split(
        "create or replace view public.alpha_hunter_roundtrip_order_events_v01",
        1,
    )[1].split(
        "create or replace view public.alpha_hunter_roundtrip_episodes_v01",
        1,
    )[0]

    assert "f.order_id as" not in event_select
    assert "order_id text" not in event_select


def test_episode_segmentation_starts_only_from_flat_open():
    required = [
        "lag(r.running_inventory,1,0.0)",
        "l.trade_side='OPEN'",
        "abs(l.previous_running_inventory)<=1e-8",
        "episode_no",
    ]
    for marker in required:
        assert marker in SQL


def test_outcome_claim_ceiling_excludes_funding_and_full_net_pnl():
    required = [
        "fee_adjusted_profit_ex_funding",
        "false as funding_bound",
        "false as full_economic_pnl_claim_permitted",
        "false as realistic_net_r_claim_permitted",
        "FEE_ADJUSTED_ONLY_FUNDING_AND_OTHER_BILLS_NOT_BOUND",
        "DESCRIPTIVE_FLAT_TO_FLAT_ACCOUNT_OUTCOME_EX_FUNDING",
    ]
    for marker in required:
        assert marker in SQL


def test_manual_and_system_origins_cannot_become_alpha_hunter_execution():
    required = [
        "contains_ios_origin",
        "contains_sys_origin",
        "contains_api_origin",
        "origin_set",
        "false as verified_alpha_hunter_execution",
        "false as alpha_hunter_execution_claim_permitted",
    ]
    for marker in required:
        assert marker in SQL


def test_views_are_service_role_only():
    for view in (
        "alpha_hunter_roundtrip_order_events_v01",
        "alpha_hunter_roundtrip_episodes_v01",
        "alpha_hunter_roundtrip_status_v01",
    ):
        assert f"revoke all on public.{view}" in LOWER
        assert f"grant select on public.{view}" in LOWER


def test_sql_does_not_activate_cost_risk_or_execution():
    forbidden = [
        "trade_permission=true",
        "trade_permission = true",
        "production_execution_enabled",
        "place_order",
        "cancel_order",
        "modify_order",
        "set-leverage",
        "cost_model_activation_permitted=true",
        "full_economic_pnl_claim_permitted=true",
        "realistic_net_r_claim_permitted=true",
    ]
    for marker in forbidden:
        assert marker not in LOWER


def test_profit_and_fee_are_kept_separate_before_fee_adjustment():
    required = [
        "sum(coalesce(f.profit,0)) as profit_field_sum",
        "sum(coalesce(f.fee_amount,0)) as signed_fee_sum",
        "sum(s.profit_field_sum) as profit_field_sum",
        "sum(s.signed_fee_sum) as signed_trading_fee_sum",
        "sum(s.profit_field_sum)+sum(s.signed_fee_sum)",
    ]
    for marker in required:
        assert marker in SQL
