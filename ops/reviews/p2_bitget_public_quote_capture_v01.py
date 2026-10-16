#!/usr/bin/env python3
"""P2 one-shot public Bitget USDT-M ticker evidence collector.

Success here means an isolated runner made exactly one HTTPS GET, validated
the certificate against system CAs and captured a public exchange API response.
It is NOT exchange-signed proof, protected paper monitoring, a real position
ledger, financial advice or an executable order. Never imported by the live
health-only Render web service. No cron, no Supabase, no Bitget credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import ssl
from typing import Any
from urllib.parse import urlencode
from urllib.request import (
    HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener
)

VERSION="P2_PUBLIC_BITGET_TLS_CAPTURE_V0.1"
HOST="api.bitget.com"
PATH="/api/v2/mix/market/ticker"
PRODUCT_TYPE="USDT-FUTURES"
SYMBOLS=frozenset(("BTCUSDT","ETHUSDT","QUSDT"))
MAX_AGE_SECONDS=120
MAX_FUTURE_SKEW_SECONDS=60
MAX_RESPONSE_BYTES=65536
TIMEOUT_SECONDS=8
FORBIDDEN_ENV=(
 "SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","DATABASE_URL",
 "BITGET_API_KEY","BITGET_SECRET_KEY","BITGET_API_PASSPHRASE",
 "PAPER_ORDER_AUTHORITY","REAL_ORDER_AUTHORITY",
)

class CaptureRejected(ValueError):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise CaptureRejected("PUBLIC_TICKER_REDIRECT_REFUSED")

def canonical(value:Any)->bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False).encode("utf-8")

def _now():
    return datetime.now(timezone.utc)

def _decimal(value:Any)->Decimal:
    if value is None or isinstance(value,bool):
        raise CaptureRejected("INVALID_ORDERBOOK_VALUE")
    try:
        result=Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError) as exc:
        raise CaptureRejected("INVALID_ORDERBOOK_VALUE") from exc
    if not result.is_finite() or result<=0:
        raise CaptureRejected("INVALID_ORDERBOOK_VALUE")
    return result

def guarded_symbol(symbol:str)->str:
    if not isinstance(symbol,str) or symbol not in SYMBOLS:
        raise CaptureRejected("PUBLIC_SYMBOL_NOT_ALLOWLISTED")
    return symbol

def endpoint(symbol:str)->str:
    sym=guarded_symbol(symbol)
    query=urlencode({"symbol":sym,"productType":PRODUCT_TYPE})
    return f"https://{HOST}{PATH}?{query}"

def guard_runtime(env:dict[str,str]|None=None)->None:
    variables=os.environ if env is None else env
    if any(variables.get(k) for k in FORBIDDEN_ENV):
        raise CaptureRejected("NO_BITGET_OR_PRODUCTION_DATABASE_SECRETS_ALLOWED")
    if any(variables.get(k) for k in ("HTTPS_PROXY","https_proxy","HTTP_PROXY","http_proxy","ALL_PROXY","all_proxy")):
        # Do not silently allow a proxy MITM to be recorded as a directly
        # observed Bitget TLS connection. CI unsets proxy env explicitly.
        raise CaptureRejected("PROXY_ENV_NOT_ALLOWED_FOR_DIRECT_TLS_ATTESTATION")

def parse_public_response(body:bytes,symbol:str,observed_at_utc:datetime)->dict[str,Any]:
    guarded_symbol(symbol)
    if not isinstance(body,bytes) or not 0<len(body)<=MAX_RESPONSE_BYTES:
        raise CaptureRejected("BOUNDED_PUBLIC_RESPONSE_MISSING")
    if observed_at_utc.tzinfo is None:
        raise CaptureRejected("CAPTURE_CLOCK_NOT_TIMEZONE_AWARE")
    try:
        document=json.loads(body)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise CaptureRejected("INVALID_JSON") from exc
    if not isinstance(document,dict) or document.get("code")!="00000":
        raise CaptureRejected("BITGET_API_CODE_NOT_SUCCESS")
    rows=document.get("data")
    if not isinstance(rows,list) or len(rows)!=1:
        raise CaptureRejected("SINGLE_SYMBOL_RESPONSE_REQUIRED")
    row=rows[0]
    if not isinstance(row,dict) or row.get("symbol")!=symbol:
        raise CaptureRejected("RESPONSE_SYMBOL_MISMATCH")
    bid=_decimal(row.get("bidPr"))
    ask=_decimal(row.get("askPr"))
    bid_size=_decimal(row.get("bidSz"))
    ask_size=_decimal(row.get("askSz"))
    if ask<bid:
        raise CaptureRejected("CROSSED_ORDERBOOK_REFUSED")
    try:
        if isinstance(row.get("ts"),bool):raise ValueError
        ms=int(row["ts"])
        if ms<1_500_000_000_000 or ms>4_000_000_000_000:
            raise ValueError
        exchange=datetime.fromtimestamp(ms/1000,timezone.utc)
    except (KeyError,TypeError,ValueError,OverflowError,OSError) as exc:
        raise CaptureRejected("EXCHANGE_TIMESTAMP_INVALID") from exc
    observed=observed_at_utc.astimezone(timezone.utc)
    age=(observed-exchange).total_seconds()
    if not -MAX_FUTURE_SKEW_SECONDS<=age<=MAX_AGE_SECONDS:
        raise CaptureRejected("SOURCE_TIMESTAMP_OUTSIDE_FRESHNESS_CEILING")
    return {
        "symbol":symbol,"bid_price":str(bid),"ask_price":str(ask),
        "bid_size":str(bid_size),"ask_size":str(ask_size),
        "exchange_timestamp_ms":ms,
        "exchange_time_utc":exchange.isoformat(),
        "captured_at_utc":observed.isoformat(),
        "exchange_age_at_capture_seconds":round(age,3),
        "raw_row_sha256":sha256(canonical(row)).hexdigest(),
    }

def collect_once(symbol:str, *,
    transport=None, now=None)->dict[str,Any]:
    """Real transport is FIXED TLS endpoint, one GET, no redirect/proxy.

    Injection args are pure-test hooks. Callers cannot choose a URL, HTTP
    method, API key, position ID, trade side, interval or target order.
    """
    sym=guarded_symbol(symbol)
    guard_runtime()
    url=endpoint(sym)
    request=Request(url,method="GET",headers={
        "Accept":"application/json",
        "User-Agent":"AlphaHunter-P2-Public-Quote-Research/0.1",
        "Cache-Control":"no-cache",
    })
    if transport is None:
        tls=ssl.create_default_context()
        opener=build_opener(
            ProxyHandler({}),HTTPSHandler(context=tls),NoRedirect()
        )
        transport=opener.open
    started=_now() if now is None else now()
    try:
        with transport(request,timeout=TIMEOUT_SECONDS) as response:
            if response.status!=200:
                raise CaptureRejected("UNEXPECTED_HTTP_STATUS")
            if response.geturl()!=url:
                raise CaptureRejected("PUBLIC_HOST_OR_ENDPOINT_REDIRECT")
            if "application/json" not in response.headers.get("Content-Type","").lower():
                raise CaptureRejected("NON_JSON_CONTENT_TYPE")
            raw=response.read(MAX_RESPONSE_BYTES+1)
            observed=_now() if now is None else now()
    except CaptureRejected:
        raise
    except Exception as exc:
        raise CaptureRejected("PUBLIC_TLS_TRANSPORT_FAILED:"+type(exc).__name__) from exc
    if len(raw)>MAX_RESPONSE_BYTES:
        raise CaptureRejected("PUBLIC_RESPONSE_OVERSIZE")
    book=parse_public_response(raw,sym,observed)
    capture={
        "version":VERSION,
        "status":"PUBLIC_TLS_QUOTE_CAPTURED_NOT_EXCHANGE_SIGNED",
        "source_api_host":HOST,
        "source_endpoint":PATH,
        "product_type":PRODUCT_TYPE,
        "http_method":"GET",
        "requested_url":url,
        "capture_started_utc":started.astimezone(timezone.utc).isoformat(),
        "origin_verification":"SYSTEM_CA_TLS_HOSTNAME_VALIDATION_NOT_VENUE_SIGNED",
        "response_body_sha256":sha256(raw).hexdigest(),
        "raw_response_body_utf8":raw.decode("utf-8"),
        "raw_response_public_data":json.loads(raw),
        "quote":book,
        "scientific_pass_permitted":False,
        "paper_monitoring_proven":False,
        "live_order_authority":False,
        "paper_admission_authority":False,
        "authenticated_exchange_signature":False,
        "independent_journal_receipt_committed":False,
        "previous_position_observation_verified":False,
    }
    capture["evidence_sha256"]=sha256(canonical(capture)).hexdigest()
    return capture

def verify_receipt(capture:dict[str,Any])->bool:
    """SELF-consistency only; SHA is not an exchange signature or HMAC."""
    if not isinstance(capture,dict) or capture.get("version")!=VERSION:
        raise CaptureRejected("QUOTE_CAPTURE_VERSION_UNKNOWN")
    sha=capture.get("evidence_sha256")
    unsigned={k:v for k,v in capture.items() if k!="evidence_sha256"}
    if not isinstance(sha,str) or sha!=sha256(canonical(unsigned)).hexdigest():
        raise CaptureRejected("QUOTE_CAPTURE_FINGERPRINT_MISMATCH")
    sym=capture.get("quote",{}).get("symbol")
    if sym not in SYMBOLS or capture.get("requested_url")!=endpoint(sym):
        raise CaptureRejected("QUOTE_CAPTURE_REQUEST_NOT_APPROVED")
    if capture.get("source_api_host")!=HOST or capture.get("http_method")!="GET":
        raise CaptureRejected("QUOTE_CAPTURE_SOURCE_CHANGED")
    if capture.get("independent_journal_receipt_committed") is not False:
        raise CaptureRejected("CANNOT_MANUFACTURE_INDEPENDENT_CUSTODY")
    for field in ("scientific_pass_permitted","paper_monitoring_proven",
                  "live_order_authority","paper_admission_authority",
                  "authenticated_exchange_signature"):
        if capture.get(field) is not False:
            raise CaptureRejected("UNAUTHORIZED_QUOTE_RECEIPT_PROMOTION")
    # Preserve and validate the exact original public HTTP bytes, rather
    # than calling re-serialized JSON an authentic response-body hash.
    raw_body=capture.get("raw_response_body_utf8")
    if not isinstance(raw_body,str):
        raise CaptureRejected("RAW_RESPONSE_BODY_MISSING")
    raw_bytes=raw_body.encode("utf-8")
    if capture.get("response_body_sha256")!=sha256(raw_bytes).hexdigest():
        raise CaptureRejected("RAW_HTTP_BYTES_DIGEST_MISMATCH")
    try:
        parsed=json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise CaptureRejected("RAW_BODY_NOT_JSON") from exc
    if parsed!=capture.get("raw_response_public_data"):
        raise CaptureRejected("RAW_SOURCE_ENVELOPE_CHANGED")
    when=datetime.fromisoformat(capture["quote"]["captured_at_utc"])
    # Validate freshness at original capture time, never at verification.
    verified_book=parse_public_response(raw_bytes,sym,when)
    if verified_book!=capture["quote"]:
        raise CaptureRejected("RAW_SOURCE_ROW_OR_BOOK_MISMATCH")
    return True

def save_local_artifact(capture:dict[str,Any],output_path:str)->None:
    verify_receipt(capture)
    path=Path(output_path)
    if not path.is_absolute():
        raise CaptureRejected("OUTPUT_MUST_BE_ABSOLUTE_PATH")
    # GitHub Actions whitelisted /tmp is local only; no accidental writing
    # to a production project directory, cloud secrets mount or live DB.
    if not str(path).startswith("/tmp/"):
        raise CaptureRejected("ONLY_TEMPORARY_EPHEMERAL_ARTIFACTS")
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,"wb") as writer:
        writer.write(canonical(capture)+b"\n")

def main():
    parser=argparse.ArgumentParser(description="P2 one-shot public-only quote capture")
    parser.add_argument("--symbol",choices=sorted(SYMBOLS),required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    capture=collect_once(args.symbol)
    save_local_artifact(capture,args.output)
    q=capture["quote"]
    print("P2_LIVE_PUBLIC_BITGET_READONLY_CAPTURE_PASS",
          json.dumps({"symbol":q["symbol"],
            "source":capture["source_api_host"]+capture["source_endpoint"],
            "bid_price":q["bid_price"],"ask_price":q["ask_price"],
            "exchange_age_at_capture_seconds":q["exchange_age_at_capture_seconds"],
            "evidence_sha256":capture["evidence_sha256"],
            "source_signature_verified":False,
            "independent_journal_receipt_committed":False,
            "paper_monitoring_proven":False,"real_order_authority":False},
            sort_keys=True))

if __name__=="__main__":
    main()
