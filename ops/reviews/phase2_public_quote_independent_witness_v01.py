"""Prospective independent public-market quote witness. Research ONLY.

Never imports scanner/position/trading clients or credential material.
Public HTTPS requests originate from separate GitHub Actions runtime.
TLS hostname validation + exact raw response hashes + provider timestamps
are *transport/source custody*, NOT provider-signed quotes or executable fills.
"""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

BASE = "https://api.bitget.com"
TICKER_PATH = "/api/v2/mix/market/ticker"
DEPTH_PATH = "/api/v3/market/orderbook"
SYMBOL = "BTCUSDT"
PRODUCT = "USDT-FUTURES"
MAX_AGE_MS = 90000
MAX_TRANSFER_BYTES = 200000


class EvidenceInvalid(ValueError):
    pass


def positive(value, name):
    try:
        v = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise EvidenceInvalid(name + ": nonnumeric") from None
    if not v.is_finite() or v <= 0:
        raise EvidenceInvalid(name + ": not strictly positive")
    return v


def ts_millis(value):
    try:
        t = int(str(value))
    except (ValueError, TypeError):
        raise EvidenceInvalid("provider_timestamp_invalid") from None
    if t < 1000000000000 or t > 9999999999999:
        raise EvidenceInvalid("provider_timestamp_invalid")
    return t


def validate_ticker(raw: bytes, *, start_ms: int, end_ms: int):
    try:
        obj = json.loads(raw)
        if obj["code"] != "00000":
            raise EvidenceInvalid("provider_rejected_ticker")
        rows = obj["data"]
        if not isinstance(rows, list) or len(rows) != 1:
            raise EvidenceInvalid("ticker_not_exactly_one_symbol")
        row = rows[0]
        if row.get("symbol") != SYMBOL:
            raise EvidenceInvalid("ticker_symbol_mismatch")
        ts = ts_millis(row["ts"])
        bid, ask = positive(row["bidPr"], "ticker_bid"), positive(row["askPr"], "ticker_ask")
        bsz, asz = positive(row["bidSz"], "ticker_bid_size"), positive(row["askSz"], "ticker_ask_size")
    except (KeyError, ValueError, TypeError) as exc:
        raise EvidenceInvalid("ticker_json_or_schema_invalid: "+str(exc)) from exc
    if ts < start_ms-MAX_AGE_MS or ts > end_ms+5000:
        raise EvidenceInvalid("ticker_source_timestamp_stale_or_future")
    if bid > ask:
        raise EvidenceInvalid("ticker_crossed_book")
    return {"provider_ts_ms":ts,"symbol":SYMBOL,"bid":str(bid),"ask":str(ask),
            "bid_size":str(bsz),"ask_size":str(asz),"provider_request_ts_ms":ts_millis(obj["requestTime"])}


def validate_depth(raw: bytes, *, start_ms: int, end_ms: int):
    try:
        obj=json.loads(raw)
        if obj["code"]!="00000":
            raise EvidenceInvalid("provider_rejected_depth")
        d=obj["data"]
        if not isinstance(d["a"], list) or not isinstance(d["b"], list) or not d["a"] or not d["b"]:
            raise EvidenceInvalid("depth_levels_missing")
        bids=d["b"];asks=d["a"]
        bid=positive(bids[0][0],"depth_bid");ask=positive(asks[0][0],"depth_ask")
        bsz=positive(bids[0][1],"depth_bid_size");asz=positive(asks[0][1],"depth_ask_size")
        ts=ts_millis(d["ts"])
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        raise EvidenceInvalid("depth_json_or_schema_invalid: "+str(exc)) from exc
    if ts<start_ms-MAX_AGE_MS or ts>end_ms+5000:
        raise EvidenceInvalid("depth_source_timestamp_stale_or_future")
    if bid>ask:
        raise EvidenceInvalid("depth_crossed_book")
    return {"provider_ts_ms":ts,"symbol":SYMBOL,"bid":str(bid),"ask":str(ask),
            "bid_size":str(bsz),"ask_size":str(asz),"levels":{"bids":len(bids),"asks":len(asks)},
            "provider_request_ts_ms":ts_millis(obj["requestTime"])}


def fetch_public(path: str, query: dict):
    if path not in (TICKER_PATH,DEPTH_PATH):
        raise EvidenceInvalid("endpoint_not_allowlisted")
    if query.get("symbol")!=SYMBOL:
        raise EvidenceInvalid("symbol_not_allowlisted")
    url=BASE+path+"?"+urllib.parse.urlencode(query)
    req=urllib.request.Request(url,headers={
        "Accept":"application/json","User-Agent":"AlphaHunter-P0-Independent-Public-Quote-Witness/1.0"},
        method="GET")
    start=int(time.time()*1000)
    with urllib.request.urlopen(req,timeout=12,context=ssl.create_default_context()) as resp:
        if resp.status!=200 or resp.geturl()!=url:
            raise EvidenceInvalid("HTTP_status_or_redirect_invalid")
        raw=resp.read(MAX_TRANSFER_BYTES+1)
        if len(raw)>MAX_TRANSFER_BYTES or not raw:
            raise EvidenceInvalid("response_size_invalid")
        end=int(time.time()*1000)
        headers={"date":resp.headers.get("Date"),"content_type":resp.headers.get("Content-Type")}
    return dict(url=url,raw=raw,start_ms=start,end_ms=end,headers=headers)


def build_manifest(ticker: dict, depth: dict, *, run_sha: str="", run_id: str=""):
    for item in (ticker,depth):
        if not isinstance(item.get("raw"),bytes):
            raise EvidenceInvalid("raw_provider_body_missing")
    tk=validate_ticker(ticker["raw"],start_ms=ticker["start_ms"],end_ms=ticker["end_ms"])
    dp=validate_depth(depth["raw"],start_ms=depth["start_ms"],end_ms=depth["end_ms"])
    if abs(tk["provider_ts_ms"]-dp["provider_ts_ms"])>MAX_AGE_MS:
        raise EvidenceInvalid("independent_requests_not_temporally_comparable")
    artifacts={}
    for name,item,parsed in (("ticker",ticker,tk),("orderbook",depth,dp)):
        artifacts[name]={
            "request_url":item["url"],"method":"GET","transport":"HTTPS_verified_CA_TLS",
            "captured_start_ms":item["start_ms"],"captured_end_ms":item["end_ms"],
            "raw_body_sha256":hashlib.sha256(item["raw"]).hexdigest(),
            "raw_body_length":len(item["raw"]),"http_headers":item.get("headers",{}),
            "parsed":parsed}
    return {
        "status":"PUBLIC_PROVIDER_TRANSPORT_CUSTODY_CAPTURED_NOT_SIGNED",
        "witness_kind":"independent_READ_ONLY_GitHub_Actions_prospective",
        "symbol":SYMBOL,"product_type":PRODUCT,
        "observer_git_sha":run_sha,"github_actions_run_id":run_id,
        "provider_response_signed":False,"cryptographic_exchange_attestation":False,
        "historical_quote_reconstruction_permitted":False,
        "executable_fill_proven":False,"paper_only":True,"trade_permission":False,
        "order_path":"NONE",
        "artifacts":artifacts
    }


def main():
    target=pathlib.Path(os.environ.get("AH_WITNESS_OUTPUT_DIR","/tmp/ah-public-quote-evidence"))
    target.mkdir(parents=True,exist_ok=True)
    tick=fetch_public(TICKER_PATH,{"symbol":SYMBOL,"productType":PRODUCT})
    depth=fetch_public(DEPTH_PATH,{"category":PRODUCT,"symbol":SYMBOL,"limit":"5"})
    manifest=build_manifest(tick,depth,run_sha=os.getenv("GITHUB_SHA",""),run_id=os.getenv("GITHUB_RUN_ID",""))
    (target/"ticker_public_response.json").write_bytes(tick["raw"])
    (target/"orderbook_public_response.json").write_bytes(depth["raw"])
    (target/"custody_manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    print("Public provider source witness PASS; separately captured at "+datetime.now(timezone.utc).isoformat())
    print("Public SHA256 ticker "+manifest["artifacts"]["ticker"]["raw_body_sha256"])
    print("Public SHA256 depth "+manifest["artifacts"]["orderbook"]["raw_body_sha256"])
    print("Provider-signed: FALSE; historical verification: FALSE; fill proof: FALSE; trade permission: FALSE.")


if __name__=="__main__":
    try:
        main()
    except (OSError,ValueError,TimeoutError,urllib.error.URLError) as e:
        print("Independent source witness FAIL-CLOSED: "+type(e).__name__+" "+str(e),file=sys.stderr)
        sys.exit(1)
