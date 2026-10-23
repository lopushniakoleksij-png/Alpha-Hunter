"""Forward-only research contract for exchange quote-source lineage.

A quote label must be DERIVED at the original transport-capture boundary,
not guessed from a stored quote's numeric values or the latest scanner result.
No network call is made. Supplied transport metadata can be spoofed; it is
NOT an independently authenticated Bitget response until a trusted collector
and a separately sealed custody log are implemented. Never relabel history.
"""
from __future__ import annotations

from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from hashlib import sha256
import json
from typing import Any

VERSION="P2-FORWARD-QUOTE-CUSTODY-RESEARCH-V0.1"
ENDPOINT_SOURCE={
    "/api/v2/mix/market/ticker":"BITGET_V2_MIX_MARKET_TICKER_SYMBOL_CAPTURE",
    "/api/v2/mix/market/tickers":"BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE",
}
MAX_EXCHANGE_AGE_SECONDS=120  # Matches existing canonical ticker freshness ceiling; no 35m change.
MAX_FUTURE_SKEW_SECONDS=60

class QuoteCustodyIncomplete(ValueError):
    pass

def _time(s:Any):
    if not isinstance(s,str):return None
    try:
        t=datetime.fromisoformat(s.replace("Z","+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except ValueError:return None

def _positive(x:Any):
    if x is None or isinstance(x,bool):return None
    try:
        d=Decimal(str(x))
        return d if d.is_finite() and d>0 else None
    except (TypeError,ValueError,InvalidOperation):return None

def _text(v:Any)->str:
    return v.strip() if isinstance(v,str) else ""

def canonical_json(obj:Any)->str:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)

def raw_book_digest(raw:dict[str,Any])->str:
    return sha256(canonical_json(raw).encode("utf-8")).hexdigest()

def build_transport_quote_capture(
    *,
    endpoint:str,
    requested_symbol:str,
    observed_at_utc:str,
    transport_request_id:str,
    raw_response_row:dict[str,Any],
    upstream_call_succeeded:bool,
    run_id:str,
)->dict[str,Any]:
    """Capture source lineage prospectively, without trusting downstream fields.

    Caller must be the future authorized Bitget transport wrapper. This PURE
    function does NOT prove it really called the venue. The response-row hash
    only proves byte-consistency inside the *supplied* data.
    """
    if endpoint not in ENDPOINT_SOURCE or upstream_call_succeeded is not True:
        raise QuoteCustodyIncomplete("SOURCE_ENDPOINT_OR_TRANSPORT_UNKNOWN")
    sym=_text(requested_symbol).upper()
    rid=_text(transport_request_id)
    run=_text(run_id)
    row=raw_response_row
    if (not sym.endswith("USDT") or not sym.isalnum() or not rid or not run
            or not isinstance(row,dict) or row.get("symbol")!=sym):
        raise QuoteCustodyIncomplete("SOURCE_REQUEST_SYMBOL_OR_IDENTITY_INVALID")
    ts=_time(observed_at_utc)
    try:
        ms=int(row.get("ts"))
        if ms<=0:raise ValueError
        exchange_time=datetime.fromtimestamp(ms/1000,timezone.utc)
    except (TypeError,ValueError,OverflowError,OSError):
        raise QuoteCustodyIncomplete("EXCHANGE_TIMESTAMP_MISSING_OR_INVALID")
    if ts is None:raise QuoteCustodyIncomplete("TRANSPORT_CAPTURE_TIME_INVALID")
    age=(ts-exchange_time).total_seconds()
    if not -MAX_FUTURE_SKEW_SECONDS<=age<=MAX_EXCHANGE_AGE_SECONDS:
        raise QuoteCustodyIncomplete("EXCHANGE_QUOTE_NOT_FRESH_AT_CAPTURE")
    bid=_positive(row.get("bidPr"))
    ask=_positive(row.get("askPr"))
    bid_size=_positive(row.get("bidSz"))
    ask_size=_positive(row.get("askSz"))
    if None in (bid,ask,bid_size,ask_size) or ask<bid:
        raise QuoteCustodyIncomplete("EXCHANGE_TOP_BOOK_INCOMPLETE_OR_CROSSED")
    row_sha=raw_book_digest(row)
    capture={
        "capture_contract_version":VERSION,
        "source":ENDPOINT_SOURCE[endpoint],
        "source_endpoint":endpoint,
        "source_run_id":run,
        "symbol":sym,
        "request_id":rid,
        "transport_captured_at_utc":ts.isoformat(),
        "exchange_timestamp_ms":ms,
        "exchange_timestamp_utc":exchange_time.isoformat(),
        "exchange_age_at_capture_seconds":age,
        "raw_response_row_sha256":row_sha,
        "bid_price":str(bid),"ask_price":str(ask),
        "bid_size":str(bid_size),"ask_size":str(ask_size),
        "source_authentication":"SUPPLIED_TRANSPORT_METADATA_NOT_INDEPENDENTLY_VERIFIED",
        "trade_permission":False,"exchange_authority":False,
        "production_promotion_permitted":False,
        "scientific_pass_permitted":False,
    }
    # Self-digest prevents accidental mismatched fields, not forgery.
    capture["capture_manifest_sha256"]=sha256(
        canonical_json(capture).encode("utf-8")
    ).hexdigest()
    return capture

def build_shadow_quote_attempt(capture:dict[str,Any],*,entry_order_id:str,
                               symbol:str,direction:str,source_run_id:str,
                               scan_collected_at_utc:str,
                               quote_window_seconds:int=120)->dict[str,Any]:
    """Produce per-position quote evidence ONLY from the transport receipt."""
    if not isinstance(capture,dict) or not _text(entry_order_id):
        raise QuoteCustodyIncomplete("TRANSPORT_CAPTURE_MISSING")
    if type(quote_window_seconds) is not int or not 0<quote_window_seconds<=120:
        raise QuoteCustodyIncomplete("PROPOSED_QUOTE_WINDOW_INVALID")
    scan=_time(scan_collected_at_utc)
    captured=_time(capture.get("transport_captured_at_utc"))
    if scan is None or captured is None:
        raise QuoteCustodyIncomplete("SCAN_OR_TRANSPORT_TIME_MISSING")
    if abs((captured-scan).total_seconds())>quote_window_seconds:
        raise QuoteCustodyIncomplete("TRANSPORT_CAPTURE_OUTSIDE_EXPLICIT_POLICY")
    if (capture.get("symbol")!=symbol or capture.get("source_run_id")!=source_run_id
            or direction not in ("LONG","SHORT")
            or capture.get("source") not in ENDPOINT_SOURCE.values()
            or capture.get("source_authentication")!=
             "SUPPLIED_TRANSPORT_METADATA_NOT_INDEPENDENTLY_VERIFIED"):
        raise QuoteCustodyIncomplete("SOURCE_POSITION_OR_RUN_MISMATCH")
    sha=capture.get("capture_manifest_sha256")
    unsigned={key:value for key,value in capture.items()
              if key!="capture_manifest_sha256"}
    if sha!=sha256(canonical_json(unsigned).encode()).hexdigest():
        raise QuoteCustodyIncomplete("SOURCE_CAPTURE_MANIFEST_CHANGED")
    return {
        "entry_order_id":entry_order_id,"source_run_id":source_run_id,
        "symbol":symbol,"direction":direction,
        "attempt_id":sha256(
            f"{VERSION}|{source_run_id}|{entry_order_id}".encode()
        ).hexdigest()[:32],
        "outcome":"NO_TRIGGER","blockers":[],
        "observed_at_utc":capture["transport_captured_at_utc"],
        "best_bid":capture["bid_price"],"best_ask":capture["ask_price"],
        "best_bid_size":capture["bid_size"],"best_ask_size":capture["ask_size"],
        "evidence":{
            "quote_source":capture["source"],
            "transport_request_id":capture["request_id"],
            "exchange_timestamp_ms":capture["exchange_timestamp_ms"],
            "raw_response_row_sha256":capture["raw_response_row_sha256"],
            "capture_manifest_sha256":capture["capture_manifest_sha256"],
            "source_authentication":capture["source_authentication"],
            "never_captured_from_historical_row":True,
        },
        "shadow_only":True,"trade_permission":False,"exchange_authority":False,
        "scientific_pass_permitted":False,
    }
