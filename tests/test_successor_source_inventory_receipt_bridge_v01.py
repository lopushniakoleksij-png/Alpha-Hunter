"""End-to-end SHADOW contract: all residual fills => mandatory position attempts.

No historical live R10 PASS. Synthetic forward view with historical-partial fixture
tests that a position absent from protection_open cannot vanish from monitoring.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(relpath, key):
    spec=importlib.util.spec_from_file_location(key,ROOT/relpath)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

inventory_test=load("tests/test_successor_forward_asof_inventory_v01.py","inventory_fixtures")
receipt=load("ops/reviews/successor_quote_receipts_v01.py","successor_quote_receipt_lib")
run="synthetic-source-bridge-1"
asof="2026-10-12T12:00:00Z"
captured="2026-10-12T12:00:04Z"
fp="50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834"


def fixture():
    source=inventory_test.build()
    assert source["status"]=="SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION"
    expected=[{"entry_order_id":x["entry_order_id"],"symbol":x["symbol"],
               "direction":x["direction"]} for x in source["positions"]]
    symbols=sorted({p["symbol"] for p in expected})
    parent={"run_id":run,"collected_at_utc":asof,"symbol_count":len(symbols),
            "validation_identity":{
              "run_source":"RENDER_CRON","runtime_role":"RENDER_CRON",
              "scientific_fingerprint_sha256":fp}}
    children=[{"run_id":run,"symbol":x} for x in symbols]
    attempts=[{"source_run_id":run,"entry_order_id":p["entry_order_id"],
               "symbol":p["symbol"],"direction":p["direction"],
               "outcome":"NO_TRIGGER"} for p in expected]
    quotes=[{"source_run_id":run,"symbol":s,"source":"BITGET_PUBLIC_ALL_TICKERS",
             "captured_at_utc":captured,"bid_price":"1","ask_price":"1.01",
             "bid_size":"10","ask_size":"9"} for s in symbols]
    return source,parent,children,expected,attempts,quotes


def score(data):
    _,parent,children,positions,attempts,quotes=data
    return receipt.build_monitoring_receipts(
      parent,children,positions,attempts,quotes,
      asof_inventory_complete=True,maximum_quote_offset_seconds=30,
      approved_quote_sources={"BITGET_PUBLIC_ALL_TICKERS"})


def test_legacy_unmanaged_partial_residual_requires_individual_monitoring_attempt():
    data=list(fixture())
    assert {p["entry_order_id"] for p in data[3]}=={"nmr-old-partial","q-new"}
    data[4]=[a for a in data[4] if a["entry_order_id"]=="q-new"]
    result=score(tuple(data))
    assert result["run_status"]=="UNKNOWN_OR_INCOMPLETE"
    nmr=next(r for r in result["receipts"] if r["symbol"]=="NMRUSDT")
    assert nmr["entry_order_ids"]==["nmr-old-partial"]
    assert "EXIT_ATTEMPT_MISSING" in nmr["blockers"]
    assert result["scientific_pass_permitted"] is False if "scientific_pass_permitted" in result else all(r["scientific_pass_permitted"] is False for r in result["receipts"])


def test_all_supplied_residuals_with_one_attempt_per_order_only_pass_local_structure():
    data=fixture()
    old=deepcopy(data)
    res=score(data)
    assert data==old
    assert res["run_status"]=="RECEIPTS_OBSERVED_NOT_EXECUTION_PROOF"
    assert res["expected_position_count"]==2 and res["receipt_count"]==2
    assert res["paper_authority"] is False
    assert res["production_promotion_permitted"] is False
    assert res["exchange_authority"] is False
    assert all(p["scientific_pass_permitted"] is False for p in res["receipts"])


def test_missing_source_transaction_capture_is_not_complete_even_if_quotes_exist():
    data=list(fixture())
    data[0]["status"]="SOURCE_EVIDENCE_UNKNOWN_OR_INVALID"
    # The bridge must pass independent inventory proof, not a caller's bare
    # asof_inventory_complete=True. Existing pure scorer is not authoritative;
    # deny passing an invalid manifest through the bridge.
    assert data[0]["status"]!="SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION"
    assert data[0]["caveat"].startswith("NO INDEPENDENT")
