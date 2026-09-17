from pathlib import Path


SQL = Path("cost_fee_binding_single_writer_v02.sql").read_text()
LOWER = SQL.lower()


def test_canonical_pr52_trigger_must_exist_before_consolidation():
    assert "alpha_hunter_execution_cost_public_fee_evidence" in SQL
    assert "alpha_hunter_bind_public_fee_evidence" in SQL
    assert "canonical public fee trigger missing; refusing single-writer consolidation" in SQL
    assert "canonical public fee trigger contract drifted; refusing single-writer consolidation" in SQL


def test_trigger_contract_is_exact_run_hour_public_fee_evidence():
    assert "u.selection_run_id=new.source_run_id" in LOWER
    assert "u.hour_bucket_utc=date_trunc('hour',new.captured_at_utc)" in LOWER
    assert "u.fee_rate_source='bitget_v3_instrument_public'" in LOWER
    assert "'fee_evidence_is_not_cost_model',true" in LOWER
    assert "'fee_evidence_does_not_permit_realistic_net_r',true" in LOWER


def test_trigger_contract_needles_use_sql_string_literals_not_identifiers():
    assert 'position("' not in LOWER
    assert "$needle$u.hour_bucket_utc=date_trunc('hour',new.captured_at_utc)$needle$" in LOWER
    assert "$needle$u.fee_rate_source='bitget_v3_instrument_public'$needle$" in LOWER


def test_redundant_function_binding_is_reverted_not_trigger():
    assert "v_def := replace(v_def,v_new_base,v_old_base)" in LOWER
    assert "v_def := replace(v_def,v_new_fee_values,v_old_fee_values)" in LOWER
    assert "v_def := replace(v_def,v_new_evidence,v_old_evidence)" in LOWER
    assert "drop trigger" not in LOWER
    assert "drop function" not in LOWER


def test_no_historical_evidence_rewrite_or_execution_authority():
    assert "update public.alpha_hunter_execution_cost_evidence" not in LOWER
    assert "delete from public.alpha_hunter_execution_cost_evidence" not in LOWER
    assert "trade_permission=true" not in LOWER
    assert "production_execution_enabled=true" not in LOWER
    assert "place-order" not in LOWER
    assert "place_order" not in LOWER
    assert "http_post(" not in LOWER


def test_net_r_fail_closed_contract_is_required():
    assert "withheld_no_active_validated_cost_model" in LOWER
    assert "net-r fail-closed contract drifted; refusing consolidation" in LOWER
