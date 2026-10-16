"""P3 offline-only negative red-team for partial and fragmented fills."""
from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"ops"/"reviews"))
from p3_offline_partial_fill_cost_integrity_v01 import review, LIFECYCLE_COMPONENTS
from p3_offline_execution_cost_completeness_v01 import FROZEN_SCIENTIFIC_SPEC

NOW="2026-10-15T15:00:00Z"

def row(i=0):
    prefix=f"synthetic-p3-{i}-"
    def fill(kind,n,t,qty,side,role):
        return {
            "trade_id":prefix+kind+"trade-"+str(n),
            "order_id":prefix+("intended" if kind=="entry" else "exit-order"),
            "at_utc":t,"quantity":qty,"fill_price":"1.01",
            "trade_side":side,"liquidity_role":role,"fee_amount_usdt":"0.006",
            "fee_receipt_id":prefix+kind+"fee-"+str(n),
            "signed_slippage_usdt":"-0.002",
            "slippage_receipt_id":prefix+kind+"slip-"+str(n),
            "quote_receipt_id":prefix+kind+"quote-"+str(n),
            "fee_currency":"USDT","slippage_currency":"USDT",
            "evidence_class":"SYNTHETIC_TEST_ONLY"
        }
    return {
        "decision":{
            "decision_id":prefix+"decision",
            "source_run_id":prefix+"source-run",
            "intended_order_id":prefix+"intended",
            "symbol":"QUSDT","direction":"LONG",
            "spec_id":FROZEN_SCIENTIFIC_SPEC,
            "frozen_at_utc":"2026-10-15T12:00:00Z",
            "requested_quantity":"3.2",
            "entry_price":"1","stop_price":"0.9",
            "trade_permission":False,"exchange_authority":False,
        },
        "entry_fills":[
            fill("entry",1,"2026-10-15T12:01:00Z","1.5","BUY","MAKER"),
            fill("entry",2,"2026-10-15T12:02:00Z","1.7","BUY","TAKER"),
        ],
        "exit_fills":[
            fill("exit",1,"2026-10-15T12:03:00Z","1.1","SELL","TAKER"),
            fill("exit",2,"2026-10-15T12:04:00Z","2.1","SELL","MAKER"),
        ],
        "full_exit_disposition_receipt":prefix+"verified-full-exit",
        "components":{k:{"receipt_id":prefix+"component-"+k,"amount":"-0.001" if
                 k in ("realized_funding_usdt","signed_post_fill_markout_usdt") else "0.01",
                 "currency":"USDT","evidence_class":"SYNTHETIC_TEST_ONLY"}
            for k in LIFECYCLE_COMPONENTS}
    }

def go(groups):return review(groups,now_utc=NOW)

def fails(groups,code):
    result=go(groups)
    assert code in result["blockers"],result
    assert result["historical_actual_verified_execution_rows"]==0
    assert result["realistic_net_r"] is None
    assert result["scientific_pass_permitted"] is False
    assert result["trade_permission"] is False
    assert result["production_promotion_permitted"] is False

def test_multiple_entry_and_exit_fills_reconciled_but_never_real():
    r=go([row()])
    assert r["status"]=="LOCAL_SYNTHETIC_MULTI_FILL_STRUCTURE_ONLY",r
    assert r["synthetic_complete_orders"]==1
    assert r["synthetic_multi_entry_fill_orders"]==1
    assert r["synthetic_multi_exit_fill_orders"]==1
    assert r["synthetic_mixed_liquidity_orders"]==1
    assert r["validated_cost_model"] is False
    assert r["realistic_net_r"] is None

def test_unreconciled_partial_exit_never_qualifies():
    a=row()
    a["exit_fills"][1]["quantity"]="1.9"
    fails([a],"ENTRY_MINUS_EXIT_RESIDUAL_UNRESOLVED")

def test_partial_entry_requires_proven_canceled_unfilled_remainder():
    a=row()
    a["decision"]["requested_quantity"]="4.0"
    fails([a],"PARTIAL_ENTRY_REMAINDER_NOT_PROVEN_CANCELED")
    a["unfilled_remainder_disposition"]="CANCELED_AND_CONFIRMED"
    a["cancel_receipt_id"]="synthetic-p3-0-cancel-remainder"
    assert go([a])["synthetic_complete_orders"]==1

def test_exit_before_available_cumulative_entry_is_not_full_close():
    a=row()
    a["exit_fills"][0]["at_utc"]="2026-10-15T12:01:30Z"
    a["exit_fills"][0]["quantity"]="3"
    a["exit_fills"][1]["quantity"]="0.2"
    fails([a],"EXIT_BEFORE_AVAILABLE_ENTRY_QUANTITY")

def test_cross_group_trade_id_reuse_detected():
    a,b=row(0),row(1)
    b["exit_fills"][1]["trade_id"]=a["entry_fills"][0]["trade_id"]
    fails([a,b],"DUPLICATE_OR_UNVERIFIED_TRADE_ID")

def test_cross_group_fee_receipt_reuse_detected():
    a,b=row(0),row(1)
    b["entry_fills"][0]["fee_receipt_id"]=a["exit_fills"][0]["fee_receipt_id"]
    fails([a,b],"REUSED_OR_MISSING_COST_OR_QUOTE_RECEIPT")

def test_price_fee_and_slippage_require_evidenced_amount_and_currency():
    a=row()
    a["entry_fills"][0]["fee_currency"]="BNB"
    fails([a],"FEE_OR_SLIPPAGE_CURRENCY_UNVERIFIED")
    a=row()
    a["exit_fills"][0]["signed_slippage_usdt"]=None
    fails([a],"FILL_ECONOMIC_RECEIPT_MISSING")
    a=row()
    a["exit_fills"][0]["fee_amount_usdt"]="-0.1"
    fails([a],"FILL_AMOUNT_OR_COST_INVALID")

def test_signed_markout_and_funding_separate_not_implicitly_zero():
    a=row()
    del a["components"]["realized_funding_usdt"]
    fails([a],"LIFECYCLE_COMPONENTS_MISSING")
    a=row()
    a["components"]["signed_post_fill_markout_usdt"]["amount"]=None
    fails([a],"LIFECYCLE_COMPONENT_AMOUNT_UNKNOWN")

def test_evidence_origin_real_cannot_enter_synthetic_fixture():
    a=row()
    a["entry_fills"][0]["evidence_class"]="REAL_VERIFIED"
    fails([a],"FILL_PROVENANCE_UNVERIFIED")
    a=row()
    a["entry_fills"][0]["trade_id"]="real-bitget-trade-123"
    fails([a],"DUPLICATE_OR_UNVERIFIED_TRADE_ID")

def test_trade_side_and_duplicate_decision_fail_closed():
    a=row()
    a["exit_fills"][0]["trade_side"]="BUY"
    fails([a],"TRADE_FLOW_SIDE_INVALID")
    a,b=row(0),row(1)
    b["decision"]["decision_id"]=a["decision"]["decision_id"]
    fails([a,b],"DUPLICATE_DECISION")

def test_missing_exit_receipt_rejected():
    a=row()
    a["full_exit_disposition_receipt"]=None
    fails([a],"FULL_EXIT_DISPOSITION_UNVERIFIED")

def test_empty_sample_and_invalid_clock_never_claim_net_r():
    fails([],"NO_FULLY_LINKED_FILL_GROUPS")
    result=review([row()],now_utc="bad")
    assert "REVIEW_CLOCK_INVALID" in result["blockers"]
    assert result["realistic_net_r"] is None

def test_no_network_or_prod_module_import_in_review():
    source=(Path(__file__).resolve().parents[1]/
            "ops/reviews/p3_offline_partial_fill_cost_integrity_v01.py").read_text()
    assert "requests." not in source and "psycopg." not in source
    assert "place_order(" not in source and "realistic_net_r" in source
