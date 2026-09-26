from pathlib import Path

SQL = Path("sealed_profitability_integrity_gate_v04.sql").read_text(
    encoding="utf-8"
).lower()


def test_positive_edge_gates_require_cadence_and_sample_integrity():
    assert "coalesce(i.cadence_ok,false)" in SQL
    assert "coalesce(i.sample_integrity_ok,false)" in SQL
    assert "conservative_floor_edge_gate_met" in SQL
    assert "modeled_net_edge_gate_met" in SQL


def test_failed_integrity_invalidates_profitability_test():
    assert "invalidated_by_cadence_integrity" in SQL
    assert "invalidated_by_sample_integrity" in SQL


def test_integrity_guard_never_grants_trading_authority():
    assert "false as live_money_claim_permitted" in SQL
    assert "true as shadow_only" in SQL
    assert "false as trade_permission" in SQL
    assert "false as production_promotion_permitted" in SQL
    assert "'none'::text as order_path" in SQL
