from pathlib import Path

SQL = Path("shadow_decision_quote_ledger_v01.sql").read_text(
    encoding="utf-8"
).lower()


def test_candidate_trigger_is_prospective_and_append_only():
    assert "after insert on public.alpha_hunter_strategy_observations_v01" in SQL
    assert "trg_ah_shadow_decision_quotes_append_only_v01" in SQL
    assert "before update or delete" in SQL
    assert "prospective_capture boolean not null default true" in SQL


def test_quote_capture_uses_canonical_microstructure_only():
    required = [
        "alpha_hunter_symbol_snapshots",
        "microstructure",
        "order_book",
        "recent_trades",
        "best_bid",
        "best_ask",
        "midpoint",
        "entry_cross_price",
        "entry_cross_half_spread_bps",
        "planned_entry_directional_distance_bps",
    ]
    for marker in required:
        assert marker in SQL


def test_quote_ledger_does_not_claim_fill_or_slippage():
    required = [
        "slippage_measured boolean not null default false",
        "fill_claim_permitted boolean not null default false",
        "cost_model_activation_permitted boolean not null default false",
        "realistic_net_r_claim_permitted boolean not null default false",
        "match_decision_quote_to_prospective_real_fill_before_slippage_claim",
    ]
    for marker in required:
        assert marker in SQL


def test_quote_ledger_has_no_execution_authority():
    required = [
        "shadow_only boolean not null default true",
        "trade_permission boolean not null default false",
        "production_promotion_permitted boolean not null default false",
        "order_path text not null default 'none'",
    ]
    for marker in required:
        assert marker in SQL

    forbidden = [
        "place_order",
        "cancel_order",
        "modify_order",
        "set_leverage",
        "trade_permission=true",
        "trade_permission = true",
    ]
    for marker in forbidden:
        assert marker not in SQL
