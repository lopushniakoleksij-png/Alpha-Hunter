"""P2 successor-only all-residual per-POSITION monitoring proof gate (read-only).

Pure scorer of *supplied* source-reconciled positions, explicit quarantine vs
managed coverage, real modeled-paper exit-attempt fields, quote provenance and
strict previous-qualified 35-minute observations. Does NOT independently
authenticate the supplied source snapshot or previous receipts. It NEVER
creates protective orders, paper fills, scientific PASS or live authority.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from json import dumps
from typing import Any

VERSION="P2-SUCCESSOR-SUPPLIED-EVIDENCE-RECEIPT-V0.1"
MAX_MONITOR_INTERVAL_SECONDS=2100
MANAGED="MANAGED_PROTECTED"
QUARANTINED="QUARANTINED_UNVERIFIED"
UNPROTECTED="UNPROTECTED_INCIDENT"
STATES={MANAGED,QUARANTINED,UNPROTECTED}
ACCEPTED_OUTCOMES={"NO_TRIGGER","STOP_TRIGGERED","TARGET_TRIGGERED","HORIZON_CLOSED"}

def utc(value):
    if not isinstance(value,str):return None
    try:
        x=datetime.fromisoformat(value.replace("Z","+00:00"))
        return x.astimezone(timezone.utc) if x.tzinfo else None
    except ValueError:return None

def positive(value):
    if value is None or isinstance(value,bool):return None
    try:
        d=Decimal(str(value))
        return d if d.is_finite() and d>0 else None
    except (TypeError,ValueError,InvalidOperation):return None

def text(value):
    return value.strip() if isinstance(value,str) else ""

def score_monitoring_coverage(
    inventory: dict[str,Any],
    cycle: dict[str,Any],
    dispositions: list[dict[str,Any]],
    attempts: list[dict[str,Any]],
    prior_proofs: list[dict[str,Any]],
    *,
    approved_quote_sources: frozenset[str],
    quote_window_seconds: int=30,
)->dict[str,Any]:
    """Every outstanding modeled-paper residual gets exactly one disposition.

    An empty inventory from a supplied source receipt is NOT an authenticated
    empty live ledger. Only local evidence consistency is being classified.
    An attempt is NOT a qualified observation if quote provenance is absent.
    """
    blockers=[]
    if not isinstance(inventory,dict) or inventory.get("status")!=(
      "SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION"):
        return _output([],["SOURCE_ASOF_INVENTORY_UNKNOWN"],"SOURCE_INCOMPLETE",inventory)
    if not isinstance(inventory.get("positions"),list) or not isinstance(inventory.get("manifest_sha256"),str):
        return _output([],["SOURCE_RESIDUAL_MANIFEST_MISSING"],"SOURCE_INCOMPLETE",inventory)
    positions=inventory["positions"]
    # A matching supplied 'complete' flag is insufficient even for local
    # consistency: source positions must match the fill-minus-exit manifest
    # digest. This still does NOT authenticate the external data provider.
    recomputed_sha=sha256(dumps(positions,sort_keys=True,
       separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    if recomputed_sha!=inventory["manifest_sha256"]:
        blockers.append("SOURCE_RESIDUAL_MANIFEST_DIGEST_MISMATCH")
    identity=cycle.get("validation_identity") if isinstance(cycle,dict) else None
    identity=identity if isinstance(identity,dict) else {}
    run=text(cycle.get("run_id")) if isinstance(cycle,dict) else ""
    scan=utc(cycle.get("collected_at_utc")) if isinstance(cycle,dict) else None
    fingerprint=text(identity.get("scientific_fingerprint_sha256"))
    if (not run or scan is None or identity.get("run_source")!="RENDER_CRON"
      or identity.get("runtime_role")!="RENDER_CRON"
      or len(fingerprint)!=64 or any(c not in "0123456789abcdef" for c in fingerprint)):
        blockers.append("RUN_IDENTITY_NOT_CANONICAL")
    if type(quote_window_seconds) is not int or not 0<quote_window_seconds<=120:
        blockers.append("QUOTE_FRESHNESS_POLICY_INVALID")
    if not isinstance(approved_quote_sources,frozenset) or not approved_quote_sources:
        blockers.append("EXPLICIT_APPROVED_SOURCE_POLICY_MISSING")
    if any(not isinstance(x,list) for x in [dispositions,attempts,prior_proofs]):
        return _output([],["EVIDENCE_COLLECTION_MISSING"],"SOURCE_INCOMPLETE",inventory)
    expected={}
    for item in positions:
        if not isinstance(item,dict):blockers.append("INVALID_SOURCE_POSITION");continue
        oid=text(item.get("entry_order_id"))
        sym=text(item.get("symbol"))
        side=text(item.get("direction"))
        q=positive(item.get("residual_qty"))
        if not oid or not sym or side not in {"LONG","SHORT"} or q is None:
            blockers.append("INVALID_SOURCE_POSITION");continue
        if oid in expected:blockers.append("DUPLICATE_SOURCE_POSITION")
        expected[oid]=(sym,side,item)
    declared={}
    for d in dispositions:
        if not isinstance(d,dict):blockers.append("DISPOSITION_MALFORMED");continue
        oid=text(d.get("entry_order_id"))
        if oid in declared:blockers.append("DUPLICATE_DISPOSITION")
        if oid not in expected:blockers.append("EXTRANEOUS_DISPOSITION")
        state=text(d.get("state"))
        if state not in STATES:blockers.append("DISPOSITION_UNKNOWN")
        declared[oid]=d
    if set(declared)!=set(expected):blockers.append("RESIDUAL_DISPOSITION_COVERAGE_MISMATCH")
    observed={}
    for a in attempts:
        if not isinstance(a,dict):blockers.append("ATTEMPT_MALFORMED");continue
        oid=text(a.get("entry_order_id"))
        if oid not in expected:blockers.append("UNEXPECTED_ATTEMPT")
        observed.setdefault(oid,[]).append(a)
    prev={}
    for p in prior_proofs:
        if not isinstance(p,dict):blockers.append("PREVIOUS_EVIDENCE_MALFORMED");continue
        oid=text(p.get("entry_order_id"))
        if oid not in expected:blockers.append("UNEXPECTED_PREVIOUS_EVIDENCE")
        if oid in prev:blockers.append("DUPLICATE_PRIOR_PROOF")
        prev[oid]=p

    output=[]
    for oid,(sym,side,source) in sorted(expected.items()):
        d=declared.get(oid,{})
        state=d.get("state")
        failures=[]
        entries=observed.get(oid,[])
        if state==MANAGED:
            if d.get("protection_count")!=2:
                failures.append("MISSING_STOP_OR_TARGET_PROTECTION_RECORD")
            if len(entries)!=1:
                failures.append("POSITION_MONITOR_ATTEMPT_COUNT_NOT_ONE")
            else:
                a=entries[0]
                if (text(a.get("source_run_id"))!=run
                    or text(a.get("symbol"))!=sym
                    or text(a.get("direction"))!=side
                    or not text(a.get("attempt_id"))):
                    failures.append("ATTEMPT_RUN_POSITION_IDENTITY_CONFLICT")
                if text(a.get("outcome")) not in ACCEPTED_OUTCOMES:
                    failures.append("ATTEMPT_OUTCOME_INVALID")
                if a.get("blockers")!=[]:
                    failures.append("ATTEMPT_BLOCKERS_PRESENT_OR_UNKNOWN")
                bid=positive(a.get("best_bid"))
                ask=positive(a.get("best_ask"))
                bidsize=positive(a.get("best_bid_size"))
                asksize=positive(a.get("best_ask_size"))
                if None in (bid,ask,bidsize,asksize) or ask<bid:
                    failures.append("QUOTE_BOOK_INCOMPLETE")
                evidence=a.get("evidence")
                if not isinstance(evidence,dict):
                    failures.append("QUOTE_PROVENANCE_NOT_STRUCTURED")
                    evidence={}
                source_label=text(evidence.get("quote_source"))
                if not source_label:
                    failures.append("QUOTE_SOURCE_UNLABELED")
                elif source_label not in approved_quote_sources:
                    failures.append("QUOTE_SOURCE_NOT_APPROVED")
                at=utc(a.get("observed_at_utc"))
                if scan is None or at is None:
                    failures.append("QUOTE_OR_SCAN_TIME_MISSING")
                elif (type(quote_window_seconds) is int
                    and abs((at-scan).total_seconds())>quote_window_seconds):
                    failures.append("QUOTE_OUTSIDE_POLICY_WINDOW")
                # A historical position's last FILL is not a substitute for
                # actual observation continuity. Require a prior independently
                # sealed source proof, or a genuinely new fill within 35m.
                previous=prev.get(oid)
                if previous is not None:
                    prior_time=utc(previous.get("observed_at_utc"))
                    if (text(previous.get("entry_order_id"))!=oid
                        or text(previous.get("symbol"))!=sym
                        or text(previous.get("direction"))!=side
                        or not text(previous.get("previous_sealed_run_id"))
                        or previous.get("seal_verified") is not True):
                        failures.append("PRIOR_SEALED_POSITION_PROOF_UNVERIFIED")
                else:
                    prior_time=utc(source.get("latest_entry_fill_at_utc"))
                    if prior_time is None:failures.append("NO_FILL_OR_PREVIOUS_OBSERVATION_ANCHOR")
                if at is not None and prior_time is not None:
                    delta=(at-prior_time).total_seconds()
                    if delta<0 or delta>MAX_MONITOR_INTERVAL_SECONDS:
                        failures.append("FROZEN_35M_POSITION_CONTINUITY_BREACH")
            state_result="LOCAL_QUALIFIED_ATTEMPT_SUPPLIED_ONLY" if not failures else "UNKNOWN_OR_INCOMPLETE"
        elif state==QUARANTINED:
            if not text(d.get("quarantine_case_id")):
                failures.append("QUARANTINE_CASE_ID_MISSING")
            # Even fully documented quarantine does not establish continuous
            # protection and never qualifies the R10 35m scientific result.
            failures.append("QUARANTINED_RESIDUAL_UNMONITORED")
            state_result="QUARANTINED_BLOCKED"
        elif state==UNPROTECTED:
            failures.append("UNPROTECTED_FILLED_RESIDUAL_INCIDENT")
            state_result="UNPROTECTED_BLOCKED"
        else:
            failures.append("MISSING_RESIDUAL_DISPOSITION")
            state_result="UNKNOWN_OR_INCOMPLETE"
        output.append({"entry_order_id":oid,"symbol":sym,"direction":side,
           "disposition":state or "UNKNOWN","receipt_status":state_result,
           "blockers":sorted(set(failures)),
           "monitoring_claim_permitted":False,
           "scientific_pass_permitted":False})
    if blockers or any(x["blockers"] for x in output):
        status="FAIL_CLOSED_COVERAGE_OR_MONITORING_GAP"
    elif not output:
        status="EMPTY_SOURCE_INVENTORY_UNAUTHENTICATED_NO_LIVE_POSITION_CLAIM"
    else:
        status="ALL_SUPPLIED_MANAGED_ATTEMPTS_LOCALLY_QUALIFIED_NOT_AUTHENTICATED"
    return _output(output,blockers,status,inventory)

def _output(rows,blockers,status,inv):
    return {
      "version":VERSION,"status":status,
      "source_manifest_sha256":inv.get("manifest_sha256") if isinstance(inv,dict) else None,
      "expected_residuals":len(rows),
      "managed_locally_qualified":sum(x["receipt_status"]=="LOCAL_QUALIFIED_ATTEMPT_SUPPLIED_ONLY" for x in rows),
      "quarantined_or_unprotected":sum(x["disposition"] in {QUARANTINED,UNPROTECTED} for x in rows),
      "run_blockers":sorted(set(blockers)),
      "positions":rows,"scientific_pass_permitted":False,"trade_permission":False,
      "exchange_authority":False,"paper_authority":False,
      "independently_authenticated_source":False,
      "production_promotion_permitted":False,"order_path":"NONE",
      "caveat":"SOURCE ROWS AND PRIOR SEALS ARE SUPPLIED, NOT AUTHENTICATED AGAINST PRODUCTION",
    }
