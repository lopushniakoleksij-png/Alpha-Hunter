"""P3 partial/multi-fill cost receipt reconciliation, SYNTHETIC ONLY.

Each execution may have many entry fills and exit fills. Complete quantity
coverage, unique venue trade/fee/quote references and cancellation/disposition
evidence are required before even synthetic structural qualification.

NEVER performs I/O, estimates actual costs or net R, activates a model,
links historical Alpha Hunter decisions or grants trading permission.
"""
from __future__ import annotations

from decimal import Decimal

from p3_offline_execution_cost_completeness_v01 import (
    FROZEN_SCIENTIFIC_SPEC, clock, number
)

GATE_NAME = "SYNTHETIC_MULTI_FILL_ONLY"
LIFECYCLE_COMPONENTS = (
    "observed_entry_spread_usdt", "observed_exit_spread_usdt",
    "observed_market_impact_usdt", "signed_post_fill_markout_usdt",
    "realized_funding_usdt",
)
SIGNED_COMPONENTS = {"signed_post_fill_markout_usdt","realized_funding_usdt"}
REQUIRED_FILL = (
    "trade_id","order_id","at_utc","quantity","fill_price",
    "trade_side","liquidity_role","fee_amount_usdt","fee_receipt_id",
    "signed_slippage_usdt","slippage_receipt_id","quote_receipt_id",
)
DECISION = (
    "decision_id","source_run_id","intended_order_id","symbol","direction",
    "spec_id","frozen_at_utc","requested_quantity","entry_price",
    "stop_price",
)

def token(value):
    return isinstance(value,str) and value.startswith("synthetic-") and len(value)>10

def review(groups, *, now_utc):
    blockers=set()
    accepted=[]
    all_trade_ids=set()
    all_receipts=set()
    all_decisions=set()
    now=clock(now_utc)
    if now is None:
        blockers.add("REVIEW_CLOCK_INVALID")
    if not isinstance(groups,list):
        groups=[]
        blockers.add("GROUPS_INVALID")
    for group in groups:
        errors=set()
        if not isinstance(group,dict):
            blockers.add("GROUP_NOT_OBJECT");continue
        d=group.get("decision")
        entries=group.get("entry_fills")
        exits=group.get("exit_fills")
        pieces=group.get("components")
        if not isinstance(d,dict) or any(not d.get(k) for k in DECISION):
            blockers.add("DECISION_SOURCE_UNKNOWN");continue
        ident=d["decision_id"]
        if ident in all_decisions:
            errors.add("DUPLICATE_DECISION")
        all_decisions.add(ident)
        if (not all(token(d.get(k)) for k in ("decision_id","source_run_id","intended_order_id"))
            or d.get("spec_id")!=FROZEN_SCIENTIFIC_SPEC
            or d.get("direction") not in ("LONG","SHORT")
            or not isinstance(d.get("symbol"),str)
            or d.get("symbol")==""
            or d.get("trade_permission") is not False
            or d.get("exchange_authority") is not False):
            errors.add("UNVERIFIED_SYNTHETIC_DECISION_OR_TRADE_AUTHORITY")
        frozen=clock(d.get("frozen_at_utc"))
        if frozen is None or (now is not None and frozen>now):
            errors.add("DECISION_CLOCK_INVALID")
        req=number(d.get("requested_quantity"),strictly_positive=True)
        en=number(d.get("entry_price"),strictly_positive=True)
        stop=number(d.get("stop_price"),strictly_positive=True)
        if req is None or en is None or stop is None or en==stop or (
            d.get("direction")=="LONG" and stop>=en) or (
            d.get("direction")=="SHORT" and stop<=en):
            errors.add("ORDER_SIZE_OR_RISK_GEOMETRY_INVALID")
        if not isinstance(entries,list) or not entries or not isinstance(exits,list) or not exits:
            blockers.add("ENTRY_OR_EXIT_FILL_SET_MISSING");continue
        chron=[]
        q_enter=Decimal(0)
        q_exit=Decimal(0)
        for flow,seq in (("ENTRY",entries),("EXIT",exits)):
            seen_fills=set()
            for row in seq:
                if not isinstance(row,dict) or any(row.get(k) in (None,"") for k in REQUIRED_FILL):
                    errors.add("FILL_ECONOMIC_RECEIPT_MISSING");continue
                tid=row["trade_id"]
                if not token(tid) or tid in seen_fills or tid in all_trade_ids:
                    errors.add("DUPLICATE_OR_UNVERIFIED_TRADE_ID")
                seen_fills.add(tid)
                all_trade_ids.add(tid)
                if (not token(row["order_id"]) or (
                    flow=="ENTRY" and row["order_id"]!=d["intended_order_id"])):
                    errors.add("FILL_ORDER_ID_MISMATCH")
                expected_side=("BUY" if d["direction"]=="LONG" else "SELL") if flow=="ENTRY" else (
                    "SELL" if d["direction"]=="LONG" else "BUY")
                if row["trade_side"]!=expected_side:
                    errors.add("TRADE_FLOW_SIDE_INVALID")
                if row["liquidity_role"] not in ("MAKER","TAKER"):
                    errors.add("LIQUIDITY_ROLE_UNKNOWN")
                at=clock(row["at_utc"])
                if at is None or frozen is None or now is None or not frozen<=at<=now:
                    errors.add("FILL_CLOCK_INVALID")
                qty=number(row["quantity"],strictly_positive=True)
                price=number(row["fill_price"],strictly_positive=True)
                fee=number(row["fee_amount_usdt"])
                slip=number(row["signed_slippage_usdt"],allow_negative=True)
                if qty is None or price is None or fee is None or slip is None:
                    errors.add("FILL_AMOUNT_OR_COST_INVALID")
                if row.get("fee_currency")!="USDT" or row.get("slippage_currency")!="USDT":
                    errors.add("FEE_OR_SLIPPAGE_CURRENCY_UNVERIFIED")
                if row.get("evidence_class")!="SYNTHETIC_TEST_ONLY":
                    errors.add("FILL_PROVENANCE_UNVERIFIED")
                for field in ("fee_receipt_id","slippage_receipt_id","quote_receipt_id"):
                    rid=row[field]
                    if not token(rid) or rid in all_receipts:
                        errors.add("REUSED_OR_MISSING_COST_OR_QUOTE_RECEIPT")
                    all_receipts.add(rid)
                if qty is not None:
                    if flow=="ENTRY":q_enter+=qty
                    else:q_exit+=qty
                    if at is not None:
                        chron.append((at,0 if flow=="ENTRY" else 1,
                                      qty if flow=="ENTRY" else -qty))
        chron.sort()
        balance=Decimal(0)
        for _,_,change in chron:
            balance+=change
            if balance<0:
                errors.add("EXIT_BEFORE_AVAILABLE_ENTRY_QUANTITY")
        if req is not None and q_enter>req:
            errors.add("FILLED_GREATER_THAN_REQUESTED")
        if q_enter<=0 or q_exit!=q_enter:
            errors.add("ENTRY_MINUS_EXIT_RESIDUAL_UNRESOLVED")
        if req is not None and q_enter<req:
            if group.get("unfilled_remainder_disposition")!="CANCELED_AND_CONFIRMED" or not token(
                group.get("cancel_receipt_id")):
                errors.add("PARTIAL_ENTRY_REMAINDER_NOT_PROVEN_CANCELED")
            else:
                rid=group["cancel_receipt_id"]
                if rid in all_receipts:errors.add("REUSED_OR_MISSING_COST_OR_QUOTE_RECEIPT")
                all_receipts.add(rid)
        if not token(group.get("full_exit_disposition_receipt")):
            errors.add("FULL_EXIT_DISPOSITION_UNVERIFIED")
        elif group["full_exit_disposition_receipt"] in all_receipts:
            errors.add("REUSED_OR_MISSING_COST_OR_QUOTE_RECEIPT")
        else:
            all_receipts.add(group["full_exit_disposition_receipt"])
        if not isinstance(pieces,dict) or set(pieces)!=set(LIFECYCLE_COMPONENTS):
            errors.add("LIFECYCLE_COMPONENTS_MISSING")
        else:
            for key in LIFECYCLE_COMPONENTS:
                comp=pieces[key]
                if not isinstance(comp,dict):
                    errors.add("LIFECYCLE_COMPONENT_INVALID");continue
                rid=comp.get("receipt_id")
                if not token(rid) or rid in all_receipts:
                    errors.add("REUSED_OR_MISSING_COST_OR_QUOTE_RECEIPT")
                all_receipts.add(rid)
                if comp.get("evidence_class")!="SYNTHETIC_TEST_ONLY" or comp.get("currency")!="USDT":
                    errors.add("LIFECYCLE_COMPONENT_SOURCE_UNKNOWN")
                if number(comp.get("amount"),allow_negative=key in SIGNED_COMPONENTS) is None:
                    errors.add("LIFECYCLE_COMPONENT_AMOUNT_UNKNOWN")
        if errors:
            blockers.update(errors)
        else:
            accepted.append({"decision":ident,"entry_fills":len(entries),"exit_fills":len(exits),
                             "mixed_liquidity_role":len({r.get("liquidity_role") for r in entries})>1})
    if not groups:
        blockers.add("NO_FULLY_LINKED_FILL_GROUPS")
    # Deliberately not attempting any economically meaningful cost or PnL
    # arithmetic; upstream provenance and quote delivery aren't authenticated.
    return {
        "status":("LOCAL_SYNTHETIC_MULTI_FILL_STRUCTURE_ONLY" if not blockers
                  else "DATA_INSUFFICIENT_FAIL_CLOSED"),
        "blockers":sorted(blockers),
        "synthetic_complete_orders":len(accepted),
        "synthetic_multi_entry_fill_orders":sum(r["entry_fills"]>1 for r in accepted),
        "synthetic_multi_exit_fill_orders":sum(r["exit_fills"]>1 for r in accepted),
        "synthetic_mixed_liquidity_orders":sum(r["mixed_liquidity_role"] for r in accepted),
        "historical_actual_verified_execution_rows":0,
        "realistic_net_r":None,
        "validated_cost_model":False,
        "calibration_qualified":False,
        "p2_live_authenticated_monitoring_proven":False,
        "scientific_pass_permitted":False,
        "trade_permission":False,
        "exchange_authority":False,
        "production_promotion_permitted":False,
        "order_path":"NONE",
    }
