"""Offline Phase 2 pilot evidence certification from privately captured sources.

Accepts a manually exported read-only 175-row CSV signal snapshot and an
isolated 3-source Bitget raw-candle archive. No network, database, GitHub
modifications, order placement, or live trading authority.

Usage: python phase2_pilot_offline_certify.py --archive /absolute/private/path --signals /absolute/private/signals.csv --out /absolute/private/new-results
"""
import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from phase2_scientific_pilot_replay import replay, SYMBOLS, SOURCE_START_MS, SOURCE_END_MS

REQUIRED = {
    "signal_id","symbol","detected_at_utc","created_at","state",
    "direction","trade_permission","entry_price","stop_loss","take_profit",
    "reference_price","huge_rr_score","confidence_estimate_pct","reward_risk",
}
EXPECTED = {"BTCUSDT":59,"ETHUSDT":57,"SOLUSDT":59}
OUTCOME_EXPECTED = {"TP_FIRST":29,"AMBIGUOUS":3,"NO_ENTRY":11,"NOT_EVALUABLE":132}

def _safe_file(root, name):
    if not isinstance(name,str) or name!=Path(name).name or name in {".",".."}:
        raise ValueError("manifest filename is not a basename")
    file=root/name
    if file.is_symlink() or not file.is_file():
        raise ValueError("raw evidence file missing or symlinked")
    return file

def validate_sources(archive):
    archive=Path(archive)
    mpath=archive/"manifest.json"
    if mpath.is_symlink():
        raise ValueError("symlinked manifest not allowed")
    m=json.loads(mpath.read_text())
    if m.get("dataset")!="ALPHA_HUNTER_PHASE2_PRIVATE_RECAPTURE_V1":
        raise ValueError("unknown dataset")
    entries=m.get("sources")
    if not isinstance(entries,list) or len(entries)!=3 or m.get("source_count")!=3:
        raise ValueError("must have exactly three source entries")
    raw={}
    for item in entries:
        sym=item.get("symbol")
        if sym not in SYMBOLS or sym in raw:
            raise ValueError("wrong or duplicate source symbol")
        if item.get("product_type")!="USDT-FUTURES" or item.get("granularity")!="1H" or item.get("candle_type")!="market":
            raise ValueError("wrong exchange instrument or candle type")
        if item.get("start_ms")!=SOURCE_START_MS or item.get("end_ms")!=SOURCE_END_MS or item.get("validation")!="PASS":
            raise ValueError("wrong source period or verification")
        path=_safe_file(archive,item.get("filename"))
        content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=item.get("sha256"):
            raise ValueError("source SHA-256 mismatch")
        if not str(item.get("source_url","")).startswith("https://api.bitget.com/api/v2/mix/market/history-candles?"):
            raise ValueError("unapproved market-data endpoint")
        raw[sym]=content
    if set(raw)!=set(SYMBOLS):
        raise ValueError("not three complete source files")
    return raw, m

def validate_signals(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("signal CSV absent or symlinked")
    raw=path.read_bytes()
    with path.open(newline="",encoding="utf-8") as fh:
        r=csv.DictReader(fh)
        if not REQUIRED.issubset(r.fieldnames or []):
            raise ValueError("missing signal fields")
        rows=list(r)
    if len(rows)!=175 or len(set(x["signal_id"] for x in rows))!=175:
        raise ValueError("signal snapshot must contain 175 unique rows")
    found=Counter(x["symbol"] for x in rows)
    if dict(found)!=EXPECTED:
        raise ValueError("wrong symbol cohort")
    for x in rows:
        permission=x["trade_permission"].strip().lower()
        if permission not in ("false","f","0"):
            raise ValueError("source must contain only permission-blocked signals")
        x["trade_permission"]=False
        for key in ("entry_price","stop_loss","take_profit"):
            if x[key].strip()=="":
                x[key]=None
    return rows,hashlib.sha256(raw).hexdigest()

def certify(archive,signals,out):
    out=Path(out)
    if not out.is_absolute() or out.exists():
        raise ValueError("result folder must be new and absolute")
    raw,manifest=validate_sources(archive)
    cohort,snapshot_hash=validate_signals(signals)
    result=replay(cohort,raw)
    observed=result["outcomes"]
    if observed!=OUTCOME_EXPECTED:
        raise ValueError("pilot replay discrepancy: "+str(observed))
    outputs={
        "status":"REPLAY_MATCH_PRELIMINARY_COUNTS",
        "source_manifest":str(Path(archive)/"manifest.json"),
        "signals_sha256":snapshot_hash,
        "source_sha256":{x["symbol"]:x["sha256"] for x in manifest["sources"]},
        "signals":result["cohort_size"],"outcomes":observed,
        "by_symbol":result["by_symbol"],
        "zero_verified_fills":True,
        "research_only":True,
        "historical_universe_certified":False,
        "profitability_certified":False,
        "note":"Research-only independent frozen-cohort replay; not proof of trades, fills or net returns",
    }
    old=os.umask(0o077)
    try:
        out.mkdir(parents=True,mode=0o700,exist_ok=False)
        with (out/"certificate.json").open("x") as fh:
            json.dump(outputs,fh,indent=2)
        with (out/"findings_private.json").open("x") as fh:
            json.dump(result["findings"],fh,indent=2)
    finally:
        os.umask(old)
    return outputs

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--signals",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    result=certify(args.archive,args.signals,args.out)
    print(json.dumps({k:result[k] for k in ("status","signals","outcomes","zero_verified_fills")},indent=2))
