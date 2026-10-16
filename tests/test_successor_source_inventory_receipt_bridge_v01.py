"""End-to-end pure SHADOW bridge: all residual fills => per-order attempts.

A current protection_open view is NEVER an authoritative as-of inventory.
All source-capture attestations here are SYNTHETIC; do not infer live proof.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load(relpath,key):
    s=importlib.util.spec_from_file_location(key,ROOT/relpath)
    m=importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m

inventory_test=load("tests/test_successor_forward_asof_inventory_v01.py","inventory_fixtures")
bridge=load("ops/reviews/successor_forward_source_linked_cycle_v01.py","forward_cycle_shadow")
run="synthetic-source-bridge-1"
asof="2026-10-12T12:00:00Z"
captured="2026-10-12T12:00:04Z"
fp="50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834"

def fixture():
    raw=inventory_test.source()
    initial=inventory_test.build(raw)
    assert initial["status"]=="SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION"
    expected=initial["positions"]
    symbols=sorted({p["symbol"] for p in expected})
    parent={"run_id":run,"collected_at_utc":asof,"symbol_count":len(symbols),
            "validation_identity":{"run_source":"RENDER_CRON",
                "runtime_role":"RENDER_CRON","scientific_fingerprint_sha256":fp}}
    children=[{"run_id":run,"symbol":s} for s in symbols]
    attempts=[{"source_run_id":run,"entry_order_id":p["entry_order_id"],
               "symbol":p["symbol"],"direction":p["direction"],
               "attempt_id":"synthetic-"+p["entry_order_id"],
               "outcome":"NO_TRIGGER","blockers":[],"observed_at_utc":captured,
               "best_bid":"1","best_ask":"1.01",
               "best_bid_size":"10","best_ask_size":"9",
               "evidence":{"quote_source":"BITGET_PUBLIC_ALL_TICKERS"}}
              for p in expected]
    quotes=[{"source_run_id":run,"symbol":s,"source":"BITGET_PUBLIC_ALL_TICKERS",
             "captured_at_utc":captured,"bid_price":"1","ask_price":"1.01",
             "bid_size":"10","ask_size":"9"} for s in symbols]
    return [raw,parent,children,attempts,quotes]

def score(data):
    raw,parent,children,attempts,quotes=data
    return bridge.evaluate_source_linked_cycle(
      parent,children,*raw,attempts,quotes,
      max_capture_lag_seconds=20,maximum_quote_offset_seconds=30,
      approved_quote_sources={"BITGET_PUBLIC_ALL_TICKERS"})

def test_old_partially_filled_order_not_in_current_managed_view_still_requires_attempt():
    data=fixture()
    assert {p["entry_order_id"] for p in inventory_test.build(data[0])["positions"]}=={
        "nmr-old-partial","q-new"}
    data[3]=[a for a in data[3] if a["entry_order_id"]=="q-new"]
    result=score(data)
    assert result["run_status"]=="UNKNOWN_OR_INCOMPLETE"
    nmr=next(r for r in result["receipts"] if r["symbol"]=="NMRUSDT")
    assert nmr["entry_order_ids"]==["nmr-old-partial"]
    assert "EXIT_ATTEMPT_MISSING" in nmr["blockers"]
    assert result["scientific_pass_permitted"] is False

def test_derived_manifest_and_all_position_attempts_only_pass_local_structure():
    data=fixture()
    original=deepcopy(data)
    result=score(data)
    assert data==original
    assert result["run_status"]=="RECEIPTS_OBSERVED_NOT_EXECUTION_PROOF"
    assert result["expected_position_count"]==2 and result["receipt_count"]==2
    assert result["source_manifest_sha256"]==inventory_test.build(data[0])["manifest_sha256"]
    assert result["paper_authority"] is False
    assert result["production_promotion_permitted"] is False
    assert result["exchange_authority"] is False
    assert result["scientific_pass_permitted"] is False

def test_missing_source_transaction_capture_is_refused_even_with_good_quotes():
    data=fixture()
    data[0][3]["alpha_hunter_paper_fills_v02"]["complete"]=False
    result=score(data)
    assert result["run_status"]=="SOURCE_RESIDUAL_INVENTORY_UNKNOWN_OR_INCOMPLETE"
    assert result["expected_positions"] is None
    assert "ALL_COHORT_FILL_EXIT_SOURCE_INCOMPLETE" in result["blockers"]
    assert result["scientific_pass_permitted"] is False

def test_late_order_record_refuses_monitoring_success():
    data=fixture()
    data[0][1][0]["created_at"]="2026-10-12T12:10:00Z"
    result=score(data)
    assert result["run_status"]=="SOURCE_RESIDUAL_INVENTORY_UNKNOWN_OR_INCOMPLETE"
    assert "ALL_COHORT_FILL_EXIT_SOURCE_INCOMPLETE" in result["blockers"]

def test_no_production_imports_or_runtime_wiring():
    source=ROOT/"ops/reviews/successor_forward_source_linked_cycle_v01.py"
    text=source.read_text()
    assert "supabase." not in text.lower()
    assert "bitget_client" not in text
    for path in ("alpha_hunter/storage.py","alpha_hunter/paper_exit.py","hourly.py"):
        assert "successor_forward_source_linked_cycle_v01" not in (ROOT/path).read_text()
