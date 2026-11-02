"""P2 offline acceptance red-team: no Supabase/Bitget network or credential access.

Independent HMAC keys are TEST FIXTURES ONLY; a green test does not attest any
real source identity, public venue pricing, journal durability, or forward 35m.
"""
import base64,copy,hashlib,json,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlencode

import pytest

REVIEWS=Path(__file__).resolve().parents[1]/"ops"/"reviews"
sys.path.insert(0,str(REVIEWS))
from successor_p2_source_quote_provenance_contract_v01 import (
    accept,seal,digest,source_manifest,ENDPOINT,SCIENTIFIC_FINGERPRINT,
    FROZEN_MAX_GAP_SECONDS
)
from successor_forward_asof_inventory_v01 import TABLES

K_SOURCE=b"S"*32
K_QUOTE=b"Q"*32
K_MONITOR=b"M"*32
NOW=datetime(2026,10,15,12,30,tzinfo=timezone.utc)

def utc(t):
    return t.isoformat()

def fixture(n_managed=2,kind=None,gap=2100):
    asof=NOW-timedelta(seconds=1)
    ordertime=NOW-timedelta(minutes=12)
    fills_at=NOW-timedelta(minutes=10)
    orders=[]
    entry=[]
    positions=[]
    names=[f"SYNTH{i}USDT" for i in range(n_managed+(1 if kind else 0))]
    for i,sym in enumerate(names):
        oid="synthetic-entry-"+str(i)
        orders.append({"order_id":oid,"symbol":sym,"direction":"LONG",
                       "submitted_at_utc":utc(ordertime),"created_at":utc(ordertime),
                       "paper_only":True,"trade_permission":False,
                       "exchange_authority":False,"order_path":"NONE"})
        entry.append({"fill_id":"synthetic-fill-"+str(i),"order_id":oid,
                      "quantity":"1.5","filled_at_utc":utc(fills_at),
                      "created_at":utc(fills_at),"source_run_id":"synthetic-p2-prior",
                      "paper_only":True,"trade_permission":False,
                      "exchange_authority":False,"order_path":"NONE"})
        p={"entry_order_id":oid,"state":"MANAGED_WITH_STOP_TP",
           "stop_id":"synthetic-stop-"+str(i),"target_id":"synthetic-target-"+str(i)}
        if kind and i==len(names)-1:
            p={"entry_order_id":oid,"state":kind,"reason":"historical unresolved"}
        positions.append(p)
    rows={name:v for name,v in zip(TABLES,[orders,entry,[]])}
    source={
        "run_id":"synthetic-p2-provenance-forward",
        "asof_utc":utc(asof),"captured_at_utc":utc(NOW),
        "fingerprint":SCIENTIFIC_FINGERPRINT,
        "db_read":{"isolation":"REPEATABLE READ","transaction_read_only":True,
             "role":"DEDICATED_SELECT_ONLY_READER",
             "source_identity":"SUPABASE_PG_SOURCE_TEST_ONLY",
             "session_identity":"synthetic-local-pg16-session",
             "snapshot_token":"synthetic-local-transaction-snapshot"},
        "tables":{t:{"rows":v,"count":len(v),"rows_sha256":digest(v),
                       "snapshot_token":"synthetic-local-transaction-snapshot"}
                  for t,v in rows.items()},
        "dispositions":positions}
    se=seal("SOURCE_REPEATABLE_READ",source,K_SOURCE)
    q=[]
    priors=[]
    obs=[]
    _,manifest,_=source_manifest(se,K_SOURCE,NOW)
    for i in range(n_managed):
        sym=names[i]
        oid="synthetic-entry-"+str(i)
        row={"symbol":sym,"ts":str(int((NOW-timedelta(seconds=2)).timestamp()*1000)),
             "bidPr":"1","askPr":"1.01","bidSz":"10","askSz":"20"}
        raw=json.dumps({"code":"00000","data":[row]},separators=(",",":")).encode()
        payload={"run_id":source["run_id"],"symbol":sym,
            "url":ENDPOINT+"?"+urlencode({"symbol":sym,"productType":"USDT-FUTURES"}),
            "method":"GET","http_status":200,"content_type":"application/json",
            "tls_hostname_verified":True,"redirected":False,
            "request_id":"synthetic-request-"+str(i)+"-nonce",
            "transport_captured_at_utc":utc(NOW),"raw_response_b64":base64.b64encode(raw).decode(),
            "raw_response_sha256":hashlib.sha256(raw).hexdigest(),
            "venue_price_signature_verified":False}
        quote=seal("PUBLIC_BITGET_QUOTE_BYTES",payload,K_QUOTE)
        q.append(quote)
        old=seal("PAPER_POSITION_OBSERVATION",{
            "run_id":"synthetic-p2-older","entry_order_id":oid,
            "symbol":sym,"direction":"LONG",
            "observed_at_utc":utc(NOW-timedelta(seconds=gap)),
            "trade_permission":False,"exchange_authority":False},K_MONITOR)
        priors.append(old)
        now_event={
            "run_id":source["run_id"],"entry_order_id":oid,"symbol":sym,
            "direction":"LONG","observed_at_utc":utc(NOW),
            "source_manifest_sha256":manifest["manifest_sha256"],
            "source_receipt_digest":se["digest_sha256"],
            "quote_receipt_digest":quote["digest_sha256"],
            "previous_receipt_digest":old["digest_sha256"],
            "stop_id":"synthetic-stop-"+str(i),"target_id":"synthetic-target-"+str(i),
            "top_book":["1","1.01","10","20"],
            "trade_permission":False,"exchange_authority":False}
        obs.append(seal("PAPER_POSITION_OBSERVATION",now_event,K_MONITOR))
    return {"source":se,"quotes":q,"previous":priors,"current":obs}

def evaluate_case(case,**kwargs):
    return accept(case["source"],case["quotes"],case["previous"],case["current"],
            source_key=kwargs.get("source_key",K_SOURCE),
            quote_key=kwargs.get("quote_key",K_QUOTE),
            custody_key=kwargs.get("custody_key",K_MONITOR),
            now_utc=kwargs.get("now",utc(NOW)))

def reject(case,expected,**kwargs):
    out=evaluate_case(case,**kwargs)
    assert out["status"]=="FAIL_CLOSED_UNKNOWN_OR_INCIDENT",out
    assert any(expected in reason for reason in out["blockers"]),out
    assert out["locally_receipt_qualified"]==0
    assert out["scientific_pass_permitted"] is False
    assert out["trade_permission"] is False
    assert out["actual_alert_delivery_verified"] is False
    return out

def replace_source(case,modify):
    p=copy.deepcopy(case["source"]["payload"])
    modify(p)
    case["source"]=seal("SOURCE_REPEATABLE_READ",p,K_SOURCE)

def replace_quote(case,index,modify):
    p=copy.deepcopy(case["quotes"][index]["payload"])
    modify(p)
    case["quotes"][index]=seal("PUBLIC_BITGET_QUOTE_BYTES",p,K_QUOTE)

def replace_current(case,index,modify):
    p=copy.deepcopy(case["current"][index]["payload"])
    modify(p)
    case["current"][index]=seal("PAPER_POSITION_OBSERVATION",p,K_MONITOR)

def test_complete_local_signed_evidence_is_not_scientific_authentication():
    c=fixture()
    r=evaluate_case(c)
    assert r["status"]=="LOCAL_SIGNED_EVIDENCE_CANDIDATE_NOT_UPSTREAM_AUTHENTICATED",r
    assert r["expected_managed_count"]==2 and r["locally_receipt_qualified"]==2
    assert r["source_authenticated_by_independent_live_connection"] is False
    assert r["venue_quote_signed_by_bitget"] is False
    assert r["operational_independent_custody_proven"] is False
    assert r["continuous_prospective_35m_proven"] is False
    assert r["scientific_pass_permitted"] is False
    assert r["frozen_max_gap_seconds"]==2100

def test_exact_35_minute_boundary_and_one_second_failure():
    reject(fixture(gap=2101),"FROZEN_35_MINUTE_MONITOR_GAP_BREACH")
    assert evaluate_case(fixture(gap=2100))["locally_receipt_qualified"]==2
    assert FROZEN_MAX_GAP_SECONDS==35*60

def test_partial_filled_all_cohort_quarantine_and_unprotected_fail_visible():
    c=fixture(kind="QUARANTINED_NOT_CLOSED")
    result=reject(c,"HISTORICAL_UNPROTECTED_OR_QUARANTINED")
    assert result["unresolved_positive_residual_incidents"]==1
    assert result["expected_managed_count"]==2
    c=fixture(kind="UNPROTECTED_INCIDENT")
    result=reject(c,"HISTORICAL_UNPROTECTED_OR_QUARANTINED")
    assert result["unresolved_positive_residual_incidents"]==1

def test_no_source_snapshot_or_incomplete_three_table_manifest():
    c=fixture()
    replace_source(c,lambda p:p["tables"].pop(TABLES[1]))
    reject(c,"SOURCE_TABLE_SET_INCOMPLETE")
    c=fixture()
    replace_source(c,lambda p:p["tables"][TABLES[1]].update(count=0))
    reject(c,"SOURCE_TABLE_COUNT_DIGEST_OR_SNAPSHOT_MISMATCH")
    c=fixture()
    replace_source(c,lambda p:p["tables"][TABLES[2]].update(snapshot_token="different"))
    reject(c,"SOURCE_TABLE_COUNT_DIGEST_OR_SNAPSHOT_MISMATCH")

def test_source_read_self_attestation_not_trusted():
    c=fixture()
    replace_source(c,lambda p:p["db_read"].update(transaction_read_only=False))
    reject(c,"SOURCE_READ_TRANSACTION_UNVERIFIED")
    c=fixture()
    replace_source(c,lambda p:p.update(external_live_source_authenticated=True))
    reject(c,"FALSE_SOURCE_AUTHENTICATION_CLAIM")
    c=fixture()
    replace_source(c,lambda p:p["dispositions"].pop())
    reject(c,"RESIDUAL_DISPOSITION_SET_MISMATCH")

def test_source_receipt_hmac_and_ledger_row_tampering():
    c=fixture()
    c["source"]["payload"]["tables"][TABLES[1]]["rows"][0]["quantity"]="9"
    reject(c,"RECEIPT_PAYLOAD_DIGEST_MISMATCH")
    reject(fixture(),"INDEPENDENT_SIGNATURE_INVALID",source_key=b"wrong"*8)
    c=fixture()
    replace_source(c,lambda p:p["tables"][TABLES[1]]["rows"][0].update(quantity="9"))
    reject(c,"SOURCE_TABLE_COUNT_DIGEST_OR_SNAPSHOT_MISMATCH")

def test_wrong_quote_hostname_endpoint_and_spoofed_venue_signature():
    c=fixture()
    replace_quote(c,0,lambda p:p.update(tls_hostname_verified=False))
    reject(c,"QUOTE_TRANSPORT_ENDPOINT_OR_TLS_INVALID")
    c=fixture()
    replace_quote(c,0,lambda p:p.update(url="https://evil.invalid/data"))
    reject(c,"QUOTE_TRANSPORT_ENDPOINT_OR_TLS_INVALID")
    c=fixture()
    replace_quote(c,0,lambda p:p.update(venue_price_signature_verified=True))
    reject(c,"FALSE_VENUE_AUTHENTICATION_CLAIM")

def test_quote_raw_bytes_timestamp_crossed_book_and_contract():
    c=fixture()
    replace_quote(c,0,lambda p:p.update(raw_response_sha256="f"*64))
    reject(c,"RAW_QUOTE_BYTES_HASH_MISMATCH")
    c=fixture()
    def symbol_change(p):
        raw=json.loads(base64.b64decode(p["raw_response_b64"]))
        raw["data"][0]["symbol"]="WRONGUSDT"
        b=json.dumps(raw).encode()
        p["raw_response_b64"]=base64.b64encode(b).decode()
        p["raw_response_sha256"]=hashlib.sha256(b).hexdigest()
    replace_quote(c,0,symbol_change)
    reject(c,"BITGET_RESPONSE_SYMBOL_MISMATCH")
    c=fixture()
    def aged(p):
        raw=json.loads(base64.b64decode(p["raw_response_b64"]))
        raw["data"][0]["ts"]=str(int((NOW-timedelta(seconds=123)).timestamp()*1000))
        b=json.dumps(raw).encode()
        p["raw_response_b64"]=base64.b64encode(b).decode()
        p["raw_response_sha256"]=hashlib.sha256(b).hexdigest()
    replace_quote(c,0,aged)
    reject(c,"QUOTE_STALE_FUTURE_OR_MISALIGNED")
    c=fixture()
    def crossed(p):
        raw=json.loads(base64.b64decode(p["raw_response_b64"]))
        raw["data"][0]["askPr"]="0.99"
        b=json.dumps(raw).encode()
        p["raw_response_b64"]=base64.b64encode(b).decode()
        p["raw_response_sha256"]=hashlib.sha256(b).hexdigest()
    replace_quote(c,0,crossed)
    reject(c,"CROSSED_BITGET_BOOK")

def test_quote_dedup_missing_and_wrong_keys():
    c=fixture()
    c["quotes"]=c["quotes"][:1]
    reject(c,"QUOTE_SYMBOL_COVERAGE_NOT_EXACT")
    c=fixture()
    c["quotes"][1]=c["quotes"][0]
    reject(c,"QUOTE_DUPLICATE_OR_UNEXPECTED_SYMBOL")
    reject(fixture(),"INDEPENDENT_SIGNATURE_INVALID",quote_key=b"x"*32)

def test_no_parent_only_or_missing_per_position_observations():
    c=fixture()
    c["current"].pop()
    reject(c,"PER_POSITION_RECEIPT_COUNT_MISMATCH")
    c=fixture()
    c["previous"].pop()
    reject(c,"PER_POSITION_RECEIPT_COUNT_MISMATCH")
    c=fixture()
    c["previous"][1]=c["previous"][0]
    reject(c,"DUPLICATE_OR_UNEXPECTED_MONITOR_RECEIPT")
    reject(fixture(),"INDEPENDENT_SIGNATURE_INVALID",custody_key=b"mismatch-key"*3)

def test_no_wrong_run_manifest_quote_chain_protection_or_price():
    for field,new,code in [
        ("run_id","synthetic-p2-other","MONITOR_RECEIPT_SOURCE_QUOTE_OR_CHAIN_MISMATCH"),
        ("source_manifest_sha256","f"*64,"MONITOR_RECEIPT_SOURCE_QUOTE_OR_CHAIN_MISMATCH"),
        ("quote_receipt_digest","f"*64,"MONITOR_RECEIPT_SOURCE_QUOTE_OR_CHAIN_MISMATCH"),
        ("previous_receipt_digest","f"*64,"MONITOR_RECEIPT_SOURCE_QUOTE_OR_CHAIN_MISMATCH"),
        ("stop_id","different-stop","MONITOR_RECEIPT_SOURCE_QUOTE_OR_CHAIN_MISMATCH"),
        ("top_book",["1","2","10","20"],"MONITOR_BOOK_MISMATCH")
    ]:
        c=fixture()
        replace_current(c,0,lambda p:p.update({field:new}))
        reject(c,code)

def test_invalid_source_age_and_no_clock_backdating():
    c=fixture()
    reject(c,"SOURCE_CAPTURE_AGE_OR_ORDER_INVALID",now=utc(NOW+timedelta(minutes=4)))
    c=fixture()
    replace_current(c,0,lambda p:p.update(observed_at_utc=utc(NOW-timedelta(seconds=35))))
    reject(c,"MONITOR_ATTEMPT_TIMESTAMP_UNBOUND")

def test_bare_complete_flag_is_not_cryptographic_evidence():
    c=fixture()
    c["source"]={"complete":True,"seal_verified":True,"positions":2}
    reject(c,"SIGNED_ENVELOPE_INVALID")
    assert evaluate_case(fixture())["scientific_pass_permitted"] is False
