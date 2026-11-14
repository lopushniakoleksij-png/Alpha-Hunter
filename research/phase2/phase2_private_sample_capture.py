"""Explicit, bounded research-only Bitget capture to a PRIVATE local directory.

Not invoked by CI or production. Never writes to Supabase or places orders.
Usage: python research/phase2/phase2_private_sample_capture.py --out /private/qa/path
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

from phase2_backfill_planner import plan
from phase2_bitget_response_verifier import verify_response

def capture(out: Path, *, fetch=urlopen):
    if not out.is_absolute():
        raise ValueError("absolute private output path required")
    if out.exists() and (out.is_symlink() or any(out.iterdir())):
        raise ValueError("destination must be empty and not symlinked")
    out.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(out,0o700)
    requests=plan(["BTCUSDT"],"2026-11-08T00:00:00Z","2026-11-09T00:00:00Z",max_hours=24)
    manifest=[]
    for spec in requests:
        req=Request(spec.url,headers={"User-Agent":"AlphaHunter-Research-QA/1.0","Accept":"application/json"},method="GET")
        with fetch(req,timeout=15) as response:
            raw=response.read(1024*1024+1)
        if len(raw)>1024*1024:
            raise ValueError("response size limit exceeded")
        result=verify_response(raw,symbol=spec.symbol,start_ms=spec.start_ms,end_ms=spec.end_ms)
        if result.status!="PASS":
            raise ValueError("sample rejected: "+result.reason)
        name=result.raw_sha256+".json"
        target=out/name
        with target.open("xb") as file:
            os.chmod(target,0o600)
            file.write(raw)
        manifest.append({"source_url":spec.url,"symbol":spec.symbol,
                         "product_type":"USDT-FUTURES","granularity":"1H",
                         "start_ms":spec.start_ms,"end_ms":spec.end_ms,
                         "sha256":result.raw_sha256,"filename":name,
                         "observed_hours":result.observed_hours,
                         "status":result.status,"request_time_ms":result.request_time_ms})
    with (out/"manifest.json").open("x") as file:
        os.chmod(out/"manifest.json",0o600)
        json.dump(manifest,file,indent=2)
    return manifest

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(capture(args.out),indent=2))
