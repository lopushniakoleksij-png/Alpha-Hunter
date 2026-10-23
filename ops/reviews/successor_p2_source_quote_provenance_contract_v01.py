"""P2 source and quote receipt acceptance *contract*, research only.

Cryptographic verification is done using VERIFIER-held keys, not caller-supplied
seal_verified / complete flags. An HMAC proves the claimed bytes were signed
by the key-holder; it does NOT certify that Supabase supplied every row, that
Bitget digitally signed a quote, or that journal custody is operational.
No network access, credentials, orders, source writes or runtime imports.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from successor_forward_asof_inventory_v01 import build_forward_asof_inventory,TABLES

FROZEN_MAX_GAP_SECONDS = 2100
MAX_SOURCE_CAPTURE_SECONDS = 35
MAX_SOURCE_AGE_SECONDS = 180
MAX_QUOTE_AGE_SECONDS = 120
MAX_QUOTE_FUTURE_SKEW_SECONDS = 60
MAX_SOURCE_TO_QUOTE_SECONDS = 120
ENDPOINT = "https://api.bitget.com/api/v2/mix/market/ticker"
SCIENTIFIC_FINGERPRINT = "50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834"

class EvidenceRejected(ValueError):
    pass

def canonical(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def digest(x):
    return hashlib.sha256(canonical(x)).hexdigest()

def seal(kind,payload,key):
    """TEST/collector helper. Real acceptance MUST use separate custody admin."""
    if not isinstance(key,bytes) or len(key)<32:raise EvidenceRejected("SIGNING_KEY_INVALID")
    body={"kind":kind,"payload":payload}
    h=digest(body)
    return {**body,"digest_sha256":h,
            "hmac_sha256":hmac.new(key,h.encode(),"sha256").hexdigest()}

def unseal(envelope,key,expected_kind):
    if not isinstance(envelope,dict) or set(envelope)!={"kind","payload","digest_sha256","hmac_sha256"}:
        raise EvidenceRejected("SIGNED_ENVELOPE_INVALID")
    if envelope["kind"]!=expected_kind or not isinstance(envelope["payload"],dict):
        raise EvidenceRejected("WRONG_EVIDENCE_TYPE")
    expected=digest({"kind":envelope["kind"],"payload":envelope["payload"]})
    if not hmac.compare_digest(str(envelope["digest_sha256"]),expected):
        raise EvidenceRejected("RECEIPT_PAYLOAD_DIGEST_MISMATCH")
    if not isinstance(key,bytes) or len(key)<32 or not hmac.compare_digest(
        str(envelope["hmac_sha256"]),hmac.new(key,expected.encode(),"sha256").hexdigest()):
        raise EvidenceRejected("INDEPENDENT_SIGNATURE_INVALID")
    return envelope["payload"]

def stamp(value):
    if not isinstance(value,str):raise EvidenceRejected("TIMESTAMP_MISSING")
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
        if parsed.tzinfo is None:raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError,OverflowError):
        raise EvidenceRejected("TIMESTAMP_INVALID")

def require(ok,error):
    if not ok:raise EvidenceRejected(error)

def number(v):
    if isinstance(v,bool):raise EvidenceRejected("QUOTE_NUMERIC_INVALID")
    try:
        x=Decimal(str(v))
        if not x.is_finite() or x<=0:raise ValueError
        return x
    except (ValueError,TypeError,InvalidOperation):
        raise EvidenceRejected("QUOTE_NUMERIC_INVALID")

def source_manifest(signed,source_key,now):
    p=unseal(signed,source_key,"SOURCE_REPEATABLE_READ")
    context=p.get("db_read")
    require(isinstance(context,dict),"DB_READ_CONTEXT_MISSING")
    require(context.get("isolation")=="REPEATABLE READ" and
            context.get("transaction_read_only") is True and
            context.get("role")=="DEDICATED_SELECT_ONLY_READER" and
            context.get("source_identity")=="SUPABASE_PG_SOURCE_TEST_ONLY" and
            isinstance(context.get("session_identity"),str) and
            bool(context["session_identity"]) and
            isinstance(context.get("snapshot_token"),str) and
            bool(context["snapshot_token"]),"SOURCE_READ_TRANSACTION_UNVERIFIED")
    a=stamp(p.get("asof_utc"))
    b=stamp(p.get("captured_at_utc"))
    require(a<=b<=a+timedelta(seconds=MAX_SOURCE_CAPTURE_SECONDS) and
            a<=now<=a+timedelta(seconds=MAX_SOURCE_AGE_SECONDS),
            "SOURCE_CAPTURE_AGE_OR_ORDER_INVALID")
    require(p.get("external_live_source_authenticated") in (None,False) and
            p.get("operational_custody_verified") in (None,False),
            "FALSE_SOURCE_AUTHENTICATION_CLAIM")
    require(p.get("fingerprint")==SCIENTIFIC_FINGERPRINT and
            isinstance(p.get("run_id"),str) and p["run_id"].startswith("synthetic-p2-"),
            "ISOLATED_R10_IDENTITY_OR_RUN_UNVERIFIED")
    tables=p.get("tables")
    require(isinstance(tables,dict) and set(tables)==set(TABLES),"SOURCE_TABLE_SET_INCOMPLETE")
    src=[]
    for t in TABLES:
        item=tables[t]
        require(isinstance(item,dict) and isinstance(item.get("rows"),list) and
                item.get("count")==len(item["rows"]) and
                item.get("rows_sha256")==digest(item["rows"]) and
                item.get("snapshot_token")==context["snapshot_token"],
                "SOURCE_TABLE_COUNT_DIGEST_OR_SNAPSHOT_MISMATCH")
        src.append(item["rows"])
    receipts={t:{"source_table":t,"complete":True,
                 "consistent_snapshot_id":context["snapshot_token"],
                 "captured_at_utc":p["captured_at_utc"]} for t in TABLES}
    inventory=build_forward_asof_inventory(*src,receipts,asof_utc=p["asof_utc"],
                        max_source_capture_lag_seconds=MAX_SOURCE_CAPTURE_SECONDS)
    require(inventory["status"]=="SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION",
            "LEDGER_RECONCILIATION_REJECTED:"+",".join(inventory["blockers"]))
    disposition=p.get("dispositions")
    require(isinstance(disposition,list) and
            len(disposition)==len(inventory["positions"]),"RESIDUAL_DISPOSITION_SET_MISMATCH")
    by_id={}
    for d in disposition:
        require(isinstance(d,dict) and isinstance(d.get("entry_order_id"),str) and
                d["entry_order_id"] not in by_id,"RESIDUAL_DISPOSITION_DUPLICATE")
        by_id[d["entry_order_id"]]=d
    require(set(by_id)=={x["entry_order_id"] for x in inventory["positions"]},
            "RESIDUAL_DISPOSITION_OMITTED_OR_UNKNOWN")
    positions=[]
    for raw in inventory["positions"]:
        d=by_id[raw["entry_order_id"]]
        kind=d.get("state")
        require(kind in ("MANAGED_WITH_STOP_TP","QUARANTINED_NOT_CLOSED",
                         "UNPROTECTED_INCIDENT"),"RESIDUAL_DISPOSITION_UNRECOGNISED")
        if kind=="MANAGED_WITH_STOP_TP":
            require(d.get("stop_id") and d.get("target_id") and
                    d["stop_id"]!=d["target_id"],"RECORDED_STOP_TARGET_MISSING")
        else:
            require(not d.get("stop_id") and not d.get("target_id") and
                    d.get("reason"),"UNRESOLVED_RESIDUAL_REASON_MISSING")
        positions.append({**raw,**d})
    return p,inventory,positions

def verify_quote(e,key,run,asof,expected_symbol):
    p=unseal(e,key,"PUBLIC_BITGET_QUOTE_BYTES")
    require(p.get("run_id")==run and p.get("symbol")==expected_symbol,
            "QUOTE_WRONG_RUN_OR_SYMBOL")
    url=ENDPOINT+"?"+urlencode({"symbol":expected_symbol,"productType":"USDT-FUTURES"})
    require(p.get("venue_price_signature_verified") in (None,False) and
            p.get("bitget_signed_response") in (None,False) and
            p.get("operational_custody_verified") in (None,False),
            "FALSE_VENUE_AUTHENTICATION_CLAIM")
    require(p.get("url")==url and p.get("method")=="GET" and
            p.get("http_status")==200 and p.get("content_type")=="application/json" and
            p.get("tls_hostname_verified") is True and
            p.get("redirected") is False and
            isinstance(p.get("request_id"),str) and len(p["request_id"])>=12,
            "QUOTE_TRANSPORT_ENDPOINT_OR_TLS_INVALID")
    try:
        raw=base64.b64decode(p.get("raw_response_b64"),validate=True)
        require(0<len(raw)<=65536,"RAW_QUOTE_LENGTH_INVALID")
        require(hashlib.sha256(raw).hexdigest()==p.get("raw_response_sha256"),
                "RAW_QUOTE_BYTES_HASH_MISMATCH")
        data=json.loads(raw)
    except EvidenceRejected:
        raise  # Preserve precise digest/size failure rather than hiding it.
    except (TypeError,ValueError,UnicodeDecodeError) as exc:
        raise EvidenceRejected("RAW_QUOTE_BODY_INVALID") from exc
    require(isinstance(data,dict) and data.get("code")=="00000" and
            isinstance(data.get("data"),list) and len(data["data"])==1,
            "QUOTE_RESPONSE_SHAPE_INVALID")
    book=data["data"][0]
    require(isinstance(book,dict) and book.get("symbol")==expected_symbol,
            "BITGET_RESPONSE_SYMBOL_MISMATCH")
    t=stamp(p.get("transport_captured_at_utc"))
    try: exchange=datetime.fromtimestamp(int(book["ts"])/1000,timezone.utc)
    except (TypeError,ValueError,OverflowError,KeyError) as exc:
        raise EvidenceRejected("EXCHANGE_TIMESTAMP_INVALID") from exc
    age=(t-exchange).total_seconds()
    require(-MAX_QUOTE_FUTURE_SKEW_SECONDS<=age<=MAX_QUOTE_AGE_SECONDS and
            abs((t-asof).total_seconds())<=MAX_SOURCE_TO_QUOTE_SECONDS,
            "QUOTE_STALE_FUTURE_OR_MISALIGNED")
    bid,ask=number(book.get("bidPr")),number(book.get("askPr"))
    size_bid,size_ask=number(book.get("bidSz")),number(book.get("askSz"))
    require(bid<=ask,"CROSSED_BITGET_BOOK")
    return p,t,(bid,ask,size_bid,size_ask)

def accept(source,quotes,previous,current,*,source_key,quote_key,custody_key,now_utc):
    """Return local evidence verdict only. Never production or scientific PASS."""
    reasons=[]
    managed_count=0
    incident_count=0
    qualified=0
    try:
        now=stamp(now_utc)
        sp,manifest,positions=source_manifest(source,source_key,now)
        asof=stamp(sp["asof_utc"])
        run=sp["run_id"]
        managed=[p for p in positions if p["state"]=="MANAGED_WITH_STOP_TP"]
        incident_count=len(positions)-len(managed)
        managed_count=len(managed)
        require(isinstance(quotes,list) and isinstance(previous,list) and
                isinstance(current,list),"POSITION_RECEIPT_COLLECTION_MISSING")
        expected_syms={p["symbol"] for p in managed}
        require(len(quotes)==len(expected_syms),"QUOTE_SYMBOL_COVERAGE_NOT_EXACT")
        book={}
        request_ids=set()
        for e in quotes:
            payload=unseal(e,quote_key,"PUBLIC_BITGET_QUOTE_BYTES")
            sym=payload.get("symbol")
            require(sym in expected_syms and sym not in book,"QUOTE_DUPLICATE_OR_UNEXPECTED_SYMBOL")
            q,ts,values=verify_quote(e,quote_key,run,asof,sym)
            require(q["request_id"] not in request_ids,"QUOTE_REQUEST_NONCE_REUSED")
            request_ids.add(q["request_id"])
            book[sym]=(e,ts,values)
        expected_ids={p["entry_order_id"] for p in managed}
        prior_by_id={}
        current_by_id={}
        for group,target in ((previous,prior_by_id),(current,current_by_id)):
            require(len(group)==len(expected_ids),"PER_POSITION_RECEIPT_COUNT_MISMATCH")
            for e in group:
                o=unseal(e,custody_key,"PAPER_POSITION_OBSERVATION")
                oid=o.get("entry_order_id")
                require(oid in expected_ids and oid not in target,
                        "DUPLICATE_OR_UNEXPECTED_MONITOR_RECEIPT")
                target[oid]=(e,o)
        for p in managed:
            oid=p["entry_order_id"]
            old_envelope,old=prior_by_id[oid]
            new_envelope,cur=current_by_id[oid]
            symbol=p["symbol"]
            qe,quote_time,book_values=book[symbol]
            require(old.get("entry_order_id")==oid and old.get("symbol")==symbol and
                    old.get("direction")==p["direction"] and
                    old.get("run_id")!=run and
                    old.get("trade_permission") is False and
                    old.get("exchange_authority") is False,
                    "PRIOR_RECEIPT_NOT_MATCHED")
            require(cur.get("entry_order_id")==oid and cur.get("symbol")==symbol and
                    cur.get("direction")==p["direction"] and cur.get("run_id")==run and
                    cur.get("source_manifest_sha256")==manifest["manifest_sha256"] and
                    cur.get("source_receipt_digest")==source["digest_sha256"] and
                    cur.get("quote_receipt_digest")==qe["digest_sha256"] and
                    cur.get("previous_receipt_digest")==old_envelope["digest_sha256"] and
                    cur.get("stop_id")==p["stop_id"] and cur.get("target_id")==p["target_id"] and
                    cur.get("trade_permission") is False and
                    cur.get("exchange_authority") is False,
                    "MONITOR_RECEIPT_SOURCE_QUOTE_OR_CHAIN_MISMATCH")
            prev_at=stamp(old.get("observed_at_utc"))
            cur_at=stamp(cur.get("observed_at_utc"))
            require(cur_at==quote_time and asof-timedelta(seconds=MAX_SOURCE_TO_QUOTE_SECONDS)<=cur_at<=
                    asof+timedelta(seconds=MAX_SOURCE_TO_QUOTE_SECONDS),
                    "MONITOR_ATTEMPT_TIMESTAMP_UNBOUND")
            interval=(cur_at-prev_at).total_seconds()
            require(0<interval<=FROZEN_MAX_GAP_SECONDS,
                    "FROZEN_35_MINUTE_MONITOR_GAP_BREACH")
            require(all(number(v)==n for v,n in zip(cur.get("top_book",[]),book_values)) and
                    len(cur.get("top_book",[]))==4,
                    "MONITOR_BOOK_MISMATCH")
            qualified+=1
        if incident_count:
            reasons.append("HISTORICAL_UNPROTECTED_OR_QUARANTINED_RESIDUALS_STILL_PRESENT")
    except (EvidenceRejected,TypeError,ValueError,KeyError,AttributeError,OverflowError) as exc:
        reasons.append(str(exc) if isinstance(exc,EvidenceRejected) else "UNVERIFIABLE_EVIDENCE_FORMAT")
    return {
        "status":("LOCAL_SIGNED_EVIDENCE_CANDIDATE_NOT_UPSTREAM_AUTHENTICATED"
                  if not reasons else "FAIL_CLOSED_UNKNOWN_OR_INCIDENT"),
        "blockers":sorted(set(reasons)),
        "expected_managed_count":managed_count,
        "locally_receipt_qualified":qualified if not reasons else 0,
        "unresolved_positive_residual_incidents":incident_count,
        "source_authenticated_by_independent_live_connection":False,
        "venue_quote_signed_by_bitget":False,
        "operational_independent_custody_proven":False,
        "continuous_prospective_35m_proven":False,
        "actual_alert_delivery_verified":False,
        "frozen_max_gap_seconds":FROZEN_MAX_GAP_SECONDS,
        "scientific_pass_permitted":False,
        "production_promotion_permitted":False,
        "trade_permission":False,
        "exchange_authority":False,
        "shadow_only":True,
        "order_path":"NONE",
        "alerts":[{"reasons":sorted(set(reasons)),"delivery_status":"NOT_DISPATCHED"}] if reasons else []
    }
