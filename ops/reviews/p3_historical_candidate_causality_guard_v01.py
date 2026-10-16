"""P3 shadow decision -> manual venue order historical anti-attribution guard.

All inputs are SYNTHETIC fixtures. This is a fail-closed offline *classifier*
for stored heuristic pairs; it is not a means of confirming any user action,
binding real fills, measuring slippage or authorising an order.
"""
from __future__ import annotations

ALLOWED_STATUS={"UNIQUE_EVIDENCE_COMPLETE_MATCH","AMBIGUOUS_EVIDENCE_COMPLETE_MATCH"}
ALLOWED_ACTION={"PLACE_LIMIT","EXECUTE_NOW"}
ALLOWED_ORDER={"MARKET","LIMIT"}

def classify_candidate(row):
    if not isinstance(row,dict) or not row.get("synthetic_test_only"):
        return {"verdict":"EVIDENCE_UNKNOWN_NOT_AUTHORIZED","method_conflict":None,
                "verified_ah_execution":False,"automated_binding_permitted":False,
                "realistic_cost_eligible":False}
    if (row.get("candidate_status") not in ALLOWED_STATUS or
        row.get("action") not in ALLOWED_ACTION or
        row.get("order_type") not in ALLOWED_ORDER or
        row.get("decision_direction") not in {"LONG","SHORT"} or
        row.get("venue_trade_scope")!="OPEN" or
        row.get("venue_order_state")!="FILLED" or
        row.get("trace_complete") is not True or
        row.get("frozen_shadow_only") is not True or
        row.get("trade_permission") is not False or
        row.get("order_writer_present") is not False or
        row.get("explicit_exact_fill_binding") is not False):
        return {"verdict":"EVIDENCE_UNKNOWN_NOT_AUTHORIZED","method_conflict":None,
                "verified_ah_execution":False,"automated_binding_permitted":False,
                "realistic_cost_eligible":False}
    conflict=row["action"]=="PLACE_LIMIT" and row["order_type"]=="MARKET"
    ambiguous=row["candidate_status"]=="AMBIGUOUS_EVIDENCE_COMPLETE_MATCH"
    status=("HEURISTIC_AMBIGUOUS_NOT_CAUSAL" if ambiguous else
            "LIMIT_INTENT_MARKET_METHOD_CONFLICT_NOT_CAUSAL" if conflict else
            "EXECUTE_NOW_LIMIT_METHOD_UNVERIFIED_NOT_CAUSAL"
            if row["action"]=="EXECUTE_NOW" and row["order_type"]=="LIMIT"
            else "UNIQUE_METHOD_COMPATIBLE_CAUSALITY_NOT_PROVED")
    return {
        "verdict":status,
        "method_conflict":conflict,
        "verified_ah_execution":False,
        "automated_binding_permitted":False,
        "realistic_cost_eligible":False,
    }

def inspect_fixture(rows):
    if not isinstance(rows,list):
        return {"status":"UNKNOWN_FIXTURE","candidate_pairs":0,
                "verified_ah_executions":0,"cost_claim_permitted":False}
    seen_pairs=set()
    source_events=set()
    source_fills=set()
    outcomes=[]
    reused=set()
    for row in rows:
        result=classify_candidate(row)
        event=row.get("synthetic_event_id") if isinstance(row,dict) else None
        fill=row.get("synthetic_fill_id") if isinstance(row,dict) else None
        if not isinstance(event,str) or not event.startswith("synthetic-") or (
            not isinstance(fill,str) or not fill.startswith("synthetic-")):
            result["verdict"]="EVIDENCE_UNKNOWN_NOT_AUTHORIZED"
        if (event,fill) in seen_pairs:
            result["verdict"]="DUPLICATE_HEURISTIC_PAIR_NOT_CAUSAL"
            reused.add((event,fill))
        seen_pairs.add((event,fill))
        source_events.add(event)
        source_fills.add(fill)
        outcomes.append(result)
    counts={status:sum(v["verdict"]==status for v in outcomes)
            for status in sorted({v["verdict"] for v in outcomes})}
    return {
      "status":"OFFLINE_DESCRIPTIVE_ANTI_ATTRIBUTION_ONLY",
      "candidate_pairs":len(rows),
      "frozen_event_count":len(source_events),
      "venue_fill_row_count":len(source_fills),
      "pair_status_counts":counts,
      "duplicated_pairs":len(reused),
      "verified_ah_executions":0,
      "exact_decision_order_fill_bindings_written":0,
      "cost_claim_permitted":False,
      "realistic_net_r":None,
      "trade_permission":False,
      "scientific_pass_permitted":False,
      "production_promotion_permitted":False,
      "historical_r10_relabel_permitted":False,
      "new_trade_needed":False
    }
