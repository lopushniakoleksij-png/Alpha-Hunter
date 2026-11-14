"""Bounded public recapture for frozen Alpha Hunter OOS V1.2 days.

Exactly nine 48-hour Bitget USDT-FUTURES 1H market-candle HTTP GETs plus one
five-day BTCUSDT 1Dutc PRE-ENTRY regime-evidence GET. No trading, private DB,
orders, broad universe scan, or production changes. Creates NEW private
output directory; never modifies sealed V1.0/V1.1 artifacts.
"""
import argparse
import hashlib
import json
import os
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen

DAYS=("2026-10-20","2026-10-21","2026-10-23")
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
BASE=(Path.home()/".alpha-hunter-phase2-private").resolve()
HOUR_MS=3600000
DAY_MS=86400000
DAILY_START=1792281600000 # 2026-10-18 00 UTC
DAILY_END=1792713600000   # 2026-10-23 00 UTC, exclusive
MAX_BYTES=1048576

def start_ms(day):
    return int(datetime.fromisoformat(day+"T00:00:00+00:00").timestamp()*1000)

def requests():
    specs=[]
    for day in DAYS:
        for symbol in SYMBOLS:
            start=start_ms(day)
            specs.append({"name":f"{day}_{symbol}_1H","day":day,"symbol":symbol,
                          "granularity":"1H","start_ms":start,
                          "end_ms":start+48*HOUR_MS,"count":48,
                          "url":("https://api.bitget.com/api/v2/mix/market/history-candles?"
                                 f"symbol={symbol}&productType=USDT-FUTURES&granularity=1H&"
                                 f"startTime={start}&endTime={start+48*HOUR_MS}&limit=48")})
    specs.append({"name":"2026-10-18_to_23_BTCUSDT_1Dutc",
                  "day":"pre-entry-regime","symbol":"BTCUSDT","granularity":"1Dutc",
                  "start_ms":DAILY_START,"end_ms":DAILY_END,"count":5,
                  "url":("https://api.bitget.com/api/v2/mix/market/history-candles?"
                         f"symbol=BTCUSDT&productType=USDT-FUTURES&granularity=1Dutc&"
                         f"startTime={DAILY_START}&endTime={DAILY_END}&limit=5")})
    return specs

def check_payload(raw,spec):
    p=json.loads(raw)
    if p.get("code")!="00000" or not isinstance(p.get("data"),list):
        raise ValueError("public Bitget market-data response invalid")
    rows=p["data"]
    if len(rows)!=spec["count"]:
        raise ValueError(f"{spec['name']}: expected {spec['count']} bars, got {len(rows)}")
    step=DAY_MS if spec["granularity"]=="1Dutc" else HOUR_MS
    for i,row in enumerate(rows):
        if not isinstance(row,list) or len(row)<5:
            raise ValueError("invalid OHLC row")
        when=int(row[0]);o,h,l,c=map(float,row[1:5])
        if (when!=spec["start_ms"]+i*step or not all(__import__("math").isfinite(v) for v in (o,h,l,c))
                or l<=0 or l>min(o,c) or h<max(o,c)):
            raise ValueError(f"{spec['name']}: timestamp/ohlc failure {i}")
    if spec["start_ms"]+spec["count"]*step!=spec["end_ms"]:
        raise ValueError("frozen request geometry invalid")
    return {"request_time_ms":p.get("requestTime"),"rows":len(rows)}

def capture(out,fetch=None):
    fetch=fetch or urlopen
    out=Path(out)
    if not out.is_absolute() or out.parent.resolve()!=BASE or out.exists() or out.is_symlink():
        raise ValueError("output must be a NEW direct child of the authorized private QA folder")
    old=os.umask(0o077)
    try:
        out.mkdir(parents=False,mode=0o700,exist_ok=False)
        entries=[]
        for spec in requests():
            req=Request(spec["url"],method="GET",headers={"Accept":"application/json","User-Agent":"AlphaHunter-Phase2-OOS-Private-QA"})
            with fetch(req,timeout=20) as resp:
                raw=resp.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:
                raise ValueError("public response exceeded maximum bound")
            summary=check_payload(raw,spec)
            digest=hashlib.sha256(raw).hexdigest()
            filename=f"{spec['name']}_{digest}.json"
            with (out/filename).open("xb") as f:
                f.write(raw)
            entries.append(dict(spec,filename=filename,sha256=digest,
                                capture_utc=datetime.now(timezone.utc).isoformat(),
                                **summary))
        manifest={"dataset":"AH_PHASE2_OOS_V12_20261020_21_23_RECAPTURE",
                  "regime_selection_protocol":"OOS_V12_PREDECLARED_PROTOCOL_20261114.md",
                  "frozen_days":["2026-10-20","2026-10-21","2026-10-23"],
                  "raw_sources":entries,"source_count":len(entries),
                  "signal_snapshot":"NOT_CAPTURED_BY_PUBLIC_PRICE_TOOL",
                  "real_orders_allowed":False,"historical_eligibility_certified":False,
                  "note":"Fresh recapture, NOT identical original live-result response bytes"}
        with (out/"manifest.json").open("x",encoding="utf-8") as f:
            json.dump(manifest,f,indent=2)
        return {"sources":len(entries),"hourly_bars":sum(x["rows"] for x in entries if x["granularity"]=="1H"),
                "daily_prior_bars":sum(x["rows"] for x in entries if x["granularity"]=="1Dutc"),
                "sha256_manifest":"PASS","directory":str(out)}
    finally:
        os.umask(old)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",required=True,type=Path)
    print(json.dumps(capture(p.parse_args().out),indent=2))
