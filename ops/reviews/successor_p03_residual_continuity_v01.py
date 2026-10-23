"""P0.3 successor-only, pure per-position continuity and failure-alert classifier.

All residual positions must be supplied from an independently read AS-OF source.
Source completeness, market-data authenticity and HMAC prior seals are NOT
established by a supplied boolean. This returns diagnostic classification only,
and cannot grant scientific or order authority. No IO or production imports.
"""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from json import dumps

MAX_GAP_SECONDS = 35 * 60  # frozen R10 maximum; NEVER enlarge
QUOTE_TIME_WINDOW_SECONDS = 120  # research quote alignment, not monitoring cadence

def utc(v):
    if not isinstance(v,str):
        return None
    try:
        d=datetime.fromisoformat(v.replace("Z","+00:00"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc) if d.tzinfo else None

def posnum(v):
    if v is None or isinstance(v,bool):
        return None
    try:
        x=Decimal(str(v))
        return x if x.is_finite() and x>0 else None
    except (TypeError,ValueError,InvalidOperation):
        return None

def sha(payload):
    return sha256(dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def evaluate(inventory,scan,attempts,quotes,prior_seals,*,approved_sources):
    inventory=inventory if isinstance(inventory,dict) else {}
    scan=scan if isinstance(scan,dict) else {}
    positions=inventory.get("positions")
    positions=positions if isinstance(positions,list) else []
    attempts=attempts if isinstance(attempts,list) else []
    quotes=quotes if isinstance(quotes,list) else []
    prior_seals=prior_seals if isinstance(prior_seals,list) else []
    run=scan.get("run_id")
    at=utc(scan.get("collected_at_utc"))
    blockers=[]
    if not isinstance(run,str) or not run or at is None:
        blockers.append("CANONICAL_CLOCK_OR_RUN_MISSING")
    if inventory.get("status")!="SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION":
        blockers.append("SOURCE_ROWS_NOT_LOCALLY_RECONCILED")
    if inventory.get("manifest_sha256")!=sha(positions):
        blockers.append("SOURCE_MANIFEST_MISMATCH")
    if not isinstance(approved_sources,(set,frozenset)) or not approved_sources:
        blockers.append("SOURCE_POLICY_MISSING")
    if not positions:
        blockers.append("INVENTORY_EMPTY_NOT_EVIDENCE_OF_ZERO_EXPOSURE")
    if any(not isinstance(p,dict) or not p.get("entry_order_id") for p in positions):
        blockers.append("MALFORMED_RESIDUAL_POSITION")
    ids=[p.get("entry_order_id") for p in positions if isinstance(p,dict)]
    if len(set(ids))!=len(ids):
        blockers.append("DUPLICATE_RESIDUAL_ID")
    expected=set(ids)
    seen_attempts=[a for a in attempts if isinstance(a,dict)]
    if len(seen_attempts)!=len(attempts) or any(a.get("entry_order_id") not in expected for a in seen_attempts):
        blockers.append("UNKNOWN_ATTEMPT_POSITION")
    if len([p for p in prior_seals if isinstance(p,dict)])!=len(prior_seals):
        blockers.append("MALFORMED_PRIOR_SEAL")
    alerts=[]
    rows=[]
    for p in sorted((p for p in positions if isinstance(p,dict) and p.get("entry_order_id")),
                    key=lambda p:p["entry_order_id"]):
        oid=p["entry_order_id"]
        symbol=p.get("symbol")
        direction=p.get("direction")
        disposition=p.get("disposition")
        errors=[]
        if posnum(p.get("residual_qty")) is None or direction not in ("LONG","SHORT") or not symbol:
            errors.append("RESIDUAL_IDENTITY_OR_QUANTITY_INVALID")
        if disposition=="QUARANTINED_NOT_CLOSED":
            errors.append("QUARANTINED_NOT_VERIFIED_CLOSED")
        elif disposition=="UNPROTECTED_UNEXPLAINED":
            errors.append("UNPROTECTED_FILLED_RESIDUAL")
        elif disposition!="MANAGED_PROTECTED" or p.get("two_records") is not True:
            errors.append("STOP_TP_PROTECTION_UNVERIFIED")
        if disposition=="MANAGED_PROTECTED" and p.get("two_records") is True:
            matched=[a for a in seen_attempts if a.get("entry_order_id")==oid and a.get("source_run_id")==run]
            if len(matched)!=1:
                errors.append("PER_POSITION_ATTEMPT_NOT_EXACTLY_ONE")
            matching_quotes=[q for q in quotes if isinstance(q,dict) and q.get("source_run_id")==run and q.get("symbol")==symbol]
            if len(matching_quotes)!=1:
                errors.append("SOURCE_QUOTE_NOT_EXACTLY_ONE")
            seal=[s for s in prior_seals if s.get("entry_order_id")==oid] if all(isinstance(s,dict) for s in prior_seals) else []
            if len(seal)!=1 or seal[0].get("seal_verified") is not True:
                errors.append("INDEPENDENT_PREVIOUS_RECEIPT_MISSING_OR_UNVERIFIED")
            elif at is not None:
                prev=utc(seal[0].get("captured_at_utc"))
                if prev is None or seal[0].get("source_run_id")==run:
                    errors.append("PRIOR_RECEIPT_TIME_OR_RUN_INVALID")
                else:
                    gap=(at-prev).total_seconds()
                    if gap<0 or gap>MAX_GAP_SECONDS:
                        errors.append("FROZEN_35M_CONTINUITY_BREACH")
            if len(matched)==1 and len(matching_quotes)==1:
                a,q=matched[0],matching_quotes[0]
                captured=utc(q.get("captured_at_utc"))
                observed=utc(a.get("observed_at_utc"))
                if (not captured or not observed or at is None
                    or abs((captured-at).total_seconds())>QUOTE_TIME_WINDOW_SECONDS
                    or abs((observed-captured).total_seconds())>QUOTE_TIME_WINDOW_SECONDS):
                    errors.append("QUOTE_CAPTURE_ATTEMPT_TIME_UNVERIFIED")
                src=q.get("source")
                evidence=a.get("evidence") if isinstance(a.get("evidence"),dict) else {}
                if (src not in approved_sources or evidence.get("quote_source")!=src
                   or evidence.get("capture_manifest_sha256")!=q.get("capture_manifest_sha256")
                   or not isinstance(q.get("capture_manifest_sha256"),str)
                   or len(q["capture_manifest_sha256"])!=64):
                    errors.append("QUOTE_SOURCE_OR_RECEIPT_CHAIN_UNVERIFIED")
                if (a.get("blockers")!=[] or a.get("outcome") not in
                    ("NO_TRIGGER","STOP_TRIGGERED","TARGET_TRIGGERED","HORIZON_CLOSED")
                   or not a.get("attempt_id") or a.get("symbol")!=symbol
                   or a.get("direction")!=direction):
                    errors.append("ATTEMPT_OUTCOME_OR_IDENTITY_UNVERIFIED")
                for key,other in (("best_bid","bid_price"),("best_ask","ask_price"),
                                  ("best_bid_size","bid_size"),("best_ask_size","ask_size")):
                    if posnum(a.get(key)) is None or posnum(q.get(other))!=posnum(a.get(key)):
                        errors.append("QUOTE_BOOK_ATTEMPT_MISMATCH")
                        break
        status="LOCAL_OBSERVATION_CANDIDATE_NOT_AUTHENTICATED" if not errors and not blockers else "UNKNOWN_OR_FAIL"
        rows.append({"entry_order_id":oid,"symbol":symbol,"direction":direction,
                     "disposition":disposition,"status":status,
                     "blockers":sorted(set(errors))})
        if errors:
            alerts.append({"event_id":sha({"run":run,"order_id":oid,"reasons":sorted(set(errors))})[:32],
                "run_id":run,"entry_order_id":oid,"severity":"CRITICAL" if
                "FROZEN_35M_CONTINUITY_BREACH" in errors or "UNPROTECTED_FILLED_RESIDUAL" in errors else "HIGH",
                "reasons":sorted(set(errors)),"delivery_status":"NOT_DISPATCHED"})
    if blockers:
        alerts.append({"event_id":sha({"run":run,"global":sorted(set(blockers))})[:32],
            "run_id":run,"entry_order_id":None,"severity":"CRITICAL",
            "reasons":sorted(set(blockers)),"delivery_status":"NOT_DISPATCHED"})
    return {"run_id":run,"source_manifest_sha256":inventory.get("manifest_sha256"),
            "positions":rows,"residual_count":len(rows),
            "locally_observable":sum(p["status"]=="LOCAL_OBSERVATION_CANDIDATE_NOT_AUTHENTICATED" for p in rows),
            "alerts":alerts,"run_blockers":sorted(set(blockers)),
            "frozen_maximum_monitor_gap_seconds":MAX_GAP_SECONDS,
            "independent_source_authentication_verified":False,
            "actual_alert_delivery_verified":False,
            "scientific_pass_permitted":False,"trade_permission":False,
            "exchange_authority":False,"production_promotion_permitted":False,
            "shadow_only":True,"order_path":"NONE",
            "status":"FAIL_CLOSED_WITH_DIAGNOSTIC_ALERTS" if blockers or alerts else
                     "LOCAL_STRUCTURE_ONLY_NOT_SCIENTIFICALLY_VERIFIED"}
