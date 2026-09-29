from pathlib import Path

SQL = Path("ops/sql/realistic_paper_execution_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_execute_now_uses_decision_time_cross_price():
    assert "filled_execute_now_at_cross" in SQL
    assert "v_fill_price:=new.entry_cross_price" in SQL
    assert "immutable_decision_quote_entry_cross" in SQL


def test_limit_order_requires_forward_trigger():
    assert "pending_limit_paper" in SQL
    assert "entry_trigger_status='triggered_limit'" in SQL
    assert "filled_limit_from_forward_path" in SQL
    assert "not_filled_within_24h" in SQL
    assert "no_trade_limit_not_filled" in SQL


def test_gross_r_uses_actual_paper_fill_geometry():
    assert "abs(v_fill_price-r.stop_price)" in SQL
    assert "abs(r.target_price-v_fill_price)" in SQL
    assert "v_gross_return_pct/v_risk_pct" in SQL


def test_net_r_stays_blocked_until_cost_model_validation():
    assert "paper_net_return_pct=null" in SQL
    assert "paper_net_r=null" in SQL
    assert "blocked_unvalidated_execution_cost_model" in SQL
    assert "realistic_net_r_claim_permitted',false" in SQL


def test_reconciliation_is_scheduled_off_core_minutes():
    assert "'7,37,57 * * * *'" in SQL
    assert "alpha-hunter-calibrated-paper-reconcile-v01" in SQL


def test_no_historical_backfill_or_live_exchange_authority():
    assert "no historical execution-decision freeze is inserted or backfilled" in SQL
    for forbidden in [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "live_exchange_order_sent=true",
        "trade_permission=true",
    ]:
        assert forbidden not in SQL
