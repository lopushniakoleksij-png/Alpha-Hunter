from pathlib import Path


SQL = Path("cost_evidence_public_fee_binding_v01.sql").read_text()
LOWER = SQL.lower()


def test_fee_binding_is_exact_run_symbol_and_non_future():
    assert "u.selection_run_id=s.source_run_id" in LOWER
    assert "u.symbol=s.symbol" in LOWER
    assert "u.observed_at_utc<=s.source_captured_at_utc" in LOWER
    assert "u.trade_permission=false" in LOWER
    assert "order by u.observed_at_utc desc" in LOWER
    assert "limit 1" in LOWER


def test_public_fees_are_evidence_not_model_activation():
    assert "coalesce(v_maker_fee_bps,n.observed_public_maker_fee_bps)" in LOWER
    assert "coalesce(v_taker_fee_bps,n.observed_public_taker_fee_bps)" in LOWER
    assert "'public_fee_evidence_used_as_cost_model',false" in LOWER
    assert "'fee_model_verified',v_cost_model_id is not null" in LOWER
    assert "status='active'" not in LOWER
    assert "insert into public.alpha_hunter_execution_cost_model_versions" not in LOWER


def test_slippage_and_full_cost_stay_fail_closed_without_model():
    assert "case when v_cost_model_id is not null then 2.0*v_taker_fee_bps+v_entry_slippage_bps+v_exit_slippage_bps end" in LOWER
    assert "'slippage_model_verified',v_cost_model_id is not null" in LOWER
    assert "'realistic_net_r_claim_permitted',false" in LOWER
    assert "withheld_no_active_validated_cost_model" in LOWER
    assert "realistic_net_r" not in LOWER or "realistic_net_r_claim_permitted" in LOWER


def test_no_execution_or_permission_change_is_introduced():
    assert "trade_permission=true" not in LOWER
    assert "production_execution_enabled=true" not in LOWER
    assert "place-order" not in LOWER
    assert "place_order" not in LOWER
    assert "cancel-order" not in LOWER
    assert "cancel_order" not in LOWER
    assert "http_post(" not in LOWER


def test_patch_fails_closed_if_function_contract_drifted():
    assert "expected execution cost evidence function not found" in SQL
    assert "execution cost base binding contract drifted; refusing patch" in SQL
    assert "execution cost fee value contract drifted; refusing patch" in SQL
    assert "execution cost evidence payload contract drifted; refusing patch" in SQL
