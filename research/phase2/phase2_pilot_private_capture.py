"""Private, opt-in capture for the frozen Alpha Hunter Phase 2 48h pilot.

Only three public Bitget HTTP GETs; no Supabase credentials, DB queries,
trading, deployments, background jobs, or full-universe scans.
Must be invoked manually in the existing authorized private Codespace.
Never commit the output folder or the market raw responses to Git.
"""
import argparse
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from phase2_backfill_planner import plan
from phase2_bitget_response_verifier import verify_response

SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
START="2026-11-08T00:00:00Z"
END="2026-11-10T00:00:00Z"
MAX_RESPONSE=1048576

def capture(out:Path, *,fetch=urlopen):
    out=Path(out)
    if not out.is_absolute():
        raise ValueError("use an absolute private evidence directory")
    if out.exists():
        raise ValueError("output folder must not already exist; no overwrites")
    if out.parent.is_symlink() or (out.parent.exists() and out.parent.is_file()):
        raise ValueError("unsafe output parent")
    old_umask=os.umask(0o077)
    try:
        out.mkdir(mode=0o700,parents=True,exist_ok=False)
        os.chmod(out,0o700)
        items=[]
        specs=plan(SYMBOLS,START,END,max_hours=48)
        if len(specs)!=3 or any(x.expected_hours!=48 for x in specs):
            raise ValueError("unexpected planner scope")
        for spec in specs:
            if spec.symbol not in SYMBOLS or "history-candles?" not in spec.url:
                raise ValueError("not an approved public market-data endpoint")
            req=Request(spec.url,headers={"Accept":"application/json","User-Agent":"AlphaHunter-Phase2-Research/1.0"},method="GET")
            with fetch(req,timeout=20) as response:
                raw=response.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:
                raise ValueError("response exceeds bounded size")
            result=verify_response(raw,symbol=spec.symbol,start_ms=spec.start_ms,end_ms=spec.end_ms)
            if result.status!="PASS" or result.observed_hours!=48:
                raise ValueError(spec.symbol+": "+result.reason)
            digest=hashlib.sha256(raw).hexdigest()
            if digest!=result.raw_sha256:
                raise ValueError("digest disagreement")
            filename=f"{spec.symbol}_{digest}.json"
            with (out/filename).open("xb") as fp:
                fp.write(raw)
            items.append({"symbol":spec.symbol,"source_url":spec.url,
                          "product_type":"USDT-FUTURES","granularity":"1H",
                          "candle_type":"market","start_ms":spec.start_ms,
                          "end_ms":spec.end_ms,"expected_hours":spec.expected_hours,
                          "observed_hours":result.observed_hours,
                          "request_time_ms":result.request_time_ms,
                          "capture_utc":datetime.now(timezone.utc).isoformat(),
                          "filename":filename,"sha256":digest,
                          "validation":"PASS"})
        manifest={"dataset":"ALPHA_HUNTER_PHASE2_PRIVATE_RECAPTURE_V1",
                  "note":"New recapture; not the same HTTP response bytes as earlier live pilot",
                  "source_count":3,"sources":items,
                  "signals_snapshot":"NOT_YET_ARCHIVED",
                  "historical_universe_certified":False,
                  "real_order_permission":False}
        with (out/"manifest.json").open("x",encoding="utf-8") as fp:
            json.dump(manifest,fp,indent=2)
        return {"directory":str(out),"sources":len(items),
                "verified_hourly_candles":sum(x["observed_hours"] for x in items),
                "sha256_verified":True,
                "signals_snapshot":"NOT_YET_ARCHIVED"}
    finally:
        os.umask(old_umask)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True,type=Path)
    print(json.dumps(capture(p.parse_args().out),indent=2))
