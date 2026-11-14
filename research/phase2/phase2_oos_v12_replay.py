"""Deterministic offline OOS Phase 2 V1.2 market-regime replay (private).

Input: newly saved private 10-source raw Bitget archive + exact read-only
450-row signal CSV. No network, DB, orders or production writes. Creates a
NEW private sibling output directory and never changes V1.0/V1.1 artifacts.
"""
import argparse
import csv
import hashlib
import json
import os
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path

from phase2_oos_v12_capture import DAYS,SYMBOLS,BASE,requests,check_payload
from phase2_oos_v12_export import inspect_export
from phase2_scientific_v11 import valid_price_geometry,model_return,TAKER_FEE,SLIPPAGE
from phase2_signal_investigator import Bar,Setup,investigate
from phase2_scientific_pilot_replay import as_utc_ms,HOUR_MS

EXPECTED_OUTCOMES={
 "2026-10-20":{"BTCUSDT":"SL_FIRST","ETHUSDT":"SL_FIRST","SOLUSDT":"TP_FIRST"},
 "2026-10-21":{"BTCUSDT":"AMBIGUOUS","ETHUSDT":"OPEN_AT_HORIZON","SOLUSDT":"SL_FIRST"},
 "2026-10-23":{"BTCUSDT":"TP_FIRST","ETHUSDT":"TP_FIRST","SOLUSDT":"TP_FIRST"},
}
EXPECTED_REGIMES={"2026-10-20":"SIDEWAYS","2026-10-21":"RISING","2026-10-23":"FALLING"}
EXPECTED_BASELINE=D("-55.290172")

def checked_archive(archive):
    archive=Path(archive)
    mf=archive/"manifest.json"
    if mf.is_symlink() or not mf.is_file():
        raise ValueError("private OOS archive manifest unavailable")
    manifest=json.loads(mf.read_text())
    if manifest.get("dataset")!="AH_PHASE2_OOS_V12_20261020_21_23_RECAPTURE":
        raise ValueError("wrong OOS evidence dataset")
    all_sources=manifest.get("raw_sources",[])
    if manifest.get("source_count")!=10 or len(all_sources)!=10:
        raise ValueError("expected exactly 10 bounded raw source files")
    by_name={}
    for entry in all_sources:
        name=entry.get("name")
        if name in by_name:raise ValueError("duplicate source name")
        by_name[name]=entry
    expected_specs=requests()
    if set(by_name)!={s["name"] for s in expected_specs}:
        raise ValueError("wrong OOS market/regime source set")
    verified={}
    for spec in expected_specs:
        entry=by_name[spec["name"]]
        for field in ("name","day","symbol","granularity","start_ms","end_ms","count","url"):
            if entry.get(field)!=spec[field]:
                raise ValueError("wrong frozen source "+field)
        name=entry.get("filename")
        if (not isinstance(name,str) or Path(name).name!=name
                or name in (".","..")):raise ValueError("unsafe source filename")
        file=archive/name
        if not file.is_file() or file.is_symlink():
            raise ValueError("source unavailable or symlinked")
        raw=file.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry.get("sha256"):
            raise ValueError("raw market-source SHA-256 mismatch")
        check_payload(raw,spec)
        verified[spec["name"]]=raw
    return verified,manifest

def checked_signals(signals):
    path=Path(signals)
    if path.is_symlink() or not path.is_file():
        raise ValueError("private signal snapshot missing or symlinked")
    info=inspect_export(path)
    with path.open(newline="",encoding="utf-8") as f:
        records=list(csv.DictReader(f))
    return records,info

def preday_regimes(raw_daily):
    data=json.loads(raw_daily)["data"]
    close={datetime.fromtimestamp(int(x[0])/1000,timezone.utc).date().isoformat():D(str(x[4])) for x in data}
    bounds={
      "2026-10-20":("2026-10-18","2026-10-19"),
      "2026-10-21":("2026-10-19","2026-10-20"),
      "2026-10-23":("2026-10-21","2026-10-22"),
    }
    result={}
    for day,(two_before,prev) in bounds.items():
        change=(close[prev]/close[two_before]-D("1"))*100
        regime="RISING" if change>D("1") else "FALLING" if change<D("-1") else "SIDEWAYS"
        if regime!=EXPECTED_REGIMES[day]:
            raise ValueError("frozen pre-day BTC regime mismatched captured source")
        result[day]={"regime":regime,"prior_close_return_pct":str(change.quantize(D("0.000001")))}
    return result

def select_first(cohort):
    chosen={}
    for row in sorted(cohort,key=lambda x:(as_utc_ms(x["detected_at_utc"]),x["signal_id"])):
        day=row["detected_at_utc"][:10]
        if day not in DAYS or row["symbol"] not in SYMBOLS:raise ValueError("out-of-sample cohort scope violation")
        if not valid_price_geometry(row):continue
        if not row.get("created_at"):continue
        ts=as_utc_ms(row["detected_at_utc"])
        if as_utc_ms(row["created_at"])>(ts//HOUR_MS+1)*HOUR_MS:continue
        chosen.setdefault((day,row["symbol"]),row)
    required={(d,s) for d in DAYS for s in SYMBOLS}
    if set(chosen)!=required:raise ValueError("missing a first complete as-of symbol/day opportunity")
    return chosen

def classify_gates(row):
    checks=json.loads(row["execution_checks_json"] or "{}")
    if not isinstance(checks,dict):raise ValueError("malformed original gate-state object")
    def one(k):
        value=checks.get(k)
        return "PASS" if value is True else "FAIL" if value is False else "MISSING"
    return {"reward_risk":one("rr_minimum_met"),
            "participation":one("participation_confirmed"),
            "momentum":one("momentum_confirmed")}

def model(cohort,verified):
    chosen=select_first(cohort)
    regimes=preday_regimes(verified["2026-10-18_to_23_BTCUSDT_1Dutc"])
    candidates=[]
    for day in DAYS:
        for symbol in SYMBOLS:
            row=chosen[(day,symbol)]
            raw=json.loads(verified[f"{day}_{symbol}_1H"])
            candles={int(x[0]):Bar(timestamp_utc=datetime.fromtimestamp(int(x[0])/1000,timezone.utc).isoformat(),
                                   high=D(str(x[2])),low=D(str(x[3]))) for x in raw["data"]}
            detected=as_utc_ms(row["detected_at_utc"])
            start=(detected//HOUR_MS+1)*HOUR_MS
            window=[candles.get(start+i*HOUR_MS) for i in range(24)]
            if any(v is None for v in window):raise ValueError("missing closed hourly outcome bars")
            outcome=investigate(Setup(signal_id=row["signal_id"],direction=row["direction"],
                                      entry=D(row["entry_price"]),stop=D(row["stop_loss"]),
                                      target=D(row["take_profit"]),disposition="BLOCKED"),window)
            costs={name:model_return(row["entry_price"],row["stop_loss"],row["take_profit"],
                                     row["direction"],outcome.status,TAKER_FEE,slip)
                   for name,slip in SLIPPAGE.items()}
            n=D("1000")/D(row["entry_price"])
            risk=n*abs(D(row["stop_loss"])-D(row["entry_price"]))
            candidates.append({
                "day":day,"regime":regimes[day]["regime"],"symbol":symbol,
                "signal_id":row["signal_id"],"detected_at_utc":row["detected_at_utc"],
                "direction":row["direction"],"trade_permission":False,
                "gate_states":classify_gates(row),
                "stored_rejection_reason":row["trade_permission_reason"],
                "entry":row["entry_price"],"stop":row["stop_loss"],"target":row["take_profit"],
                "status":outcome.status,"ambiguity_reason":outcome.reason,
                "entry_hour":outcome.entry_at,"exit_hour":outcome.exit_at,
                "reference_stop_risk_usdt":str(risk.quantize(D("0.000001"))),
                "hypothetical_costs":costs
            })
    # Reconciliation with the previously observed *read-only* bounded research
    # result; a changed source or inconsistent local replay must NOT certify.
    for c in candidates:
        if c["status"]!=EXPECTED_OUTCOMES[c["day"]][c["symbol"]]:
            raise ValueError("OOS replay mismatch for "+c["day"]+" "+c["symbol"])
    total=sum(D(c["hypothetical_costs"]["baseline"]["net_ex_funding_usdt"])
              for c in candidates if c["hypothetical_costs"]["baseline"] is not None)
    if abs(total-EXPECTED_BASELINE)>D("0.000010"):
        raise ValueError("baseline costs do not reconcile: "+str(total))
    filters={}
    for field in ("reward_risk","participation","momentum"):
        filters[field]={}
        for val in ("PASS","FAIL","MISSING"):
            group=[c for c in candidates if c["gate_states"][field]==val]
            resolved=[c for c in group if c["hypothetical_costs"]["baseline"] is not None]
            filters[field][val]={"candidates":len(group),
                "states":dict(Counter(c["status"] for c in group)),
                "resolved_only":len(resolved),
                "net_resolved_only_usdt":str(sum((D(c["hypothetical_costs"]["baseline"]["net_ex_funding_usdt"])
                                                 for c in resolved),D("0")).quantize(D("0.000001")))}
    sums={name:str(sum((D(c["hypothetical_costs"][name]["net_ex_funding_usdt"])
                        for c in candidates if c["hypothetical_costs"][name] is not None),
                       D("0")).quantize(D("0.000001"))) for name in SLIPPAGE}
    return {"status":"OOS_V12_REPLAY_MATCH_PRELIMINARY_COUNTS",
            "cohort_rows":len(cohort),
            "complete_asof_signal_instances":sum(
               valid_price_geometry(r) and bool(r.get("created_at")) and
               as_utc_ms(r["created_at"]) <= (as_utc_ms(r["detected_at_utc"])//HOUR_MS+1)*HOUR_MS
               for r in cohort),
            "independent_symbol_day_candidates":len(candidates),
            "correlated_calendar_episodes":3,
            "regimes":regimes,"outcomes":dict(Counter(c["status"] for c in candidates)),
            "net_resolved_only_by_scenario":sums,"filters":filters,"candidates":candidates,
            "verified_order_fills":0,"profitability_certified":False,
            "universe_certified":False,"real_order_authority":False,"research_only":True}

def certify(archive,signals,out):
    out=Path(out)
    if (not out.is_absolute() or out.parent.resolve()!=BASE or out.exists() or out.is_symlink()
        or out.resolve()==Path(archive).resolve() or out.resolve()==Path(signals).resolve()):
        raise ValueError("new private output sibling required, no overwrite")
    verified,manifest=checked_archive(archive)
    cohort,info=checked_signals(signals)
    result=model(cohort,verified)
    result["signals_sha256"]=info["sha256"]
    result["market_sources_sha256"]={item["name"]:item["sha256"] for item in manifest["raw_sources"]}
    old=os.umask(0o077)
    try:
        out.mkdir(mode=0o700,exist_ok=False)
        with (out/"oos_v12_certificate.json").open("x") as f:
            json.dump(result,f,indent=2)
    finally:
        os.umask(old)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--signals",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    opts=p.parse_args()
    result=certify(opts.archive,opts.signals,opts.out)
    print(json.dumps({k:result[k] for k in ("status","cohort_rows",
       "complete_asof_signal_instances","independent_symbol_day_candidates",
       "outcomes","net_resolved_only_by_scenario","verified_order_fills")},indent=2))
