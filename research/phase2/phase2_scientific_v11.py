"""Alpha Hunter Phase 2 Scientific Validation V1.1 — offline research only.

Apply an explicit, pre-specified-for-replay symbol-level deduplication rule:
- First complete, valid as-of SHORT/LONG signal per symbol in the frozen UTC day.
- One 24-hour opportunity maximum per symbol; suppress ALL later observations
  in the same symbol regardless of their outcome.
- This is a retrospectively chosen research design, NOT prospective validation.
- BTC, ETH, SOL remain one correlated crypto-market regime, NOT three
  statistically independent market events.

Inputs are the EXISTING PRIVATE evidence archive and read-only export.
The original certificate, raw candles and CSV are checked and NEVER modified.
The only output is a NEW, opt-in, private directory. No network or DB access.
"""
import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from phase2_pilot_offline_certify import (OUTCOME_EXPECTED, validate_signals,
                                         validate_sources)
from phase2_scientific_pilot_replay import (SYMBOLS, HOUR_MS, as_utc_ms,
                                           checked_source, replay)
from phase2_signal_investigator import Setup, investigate

D = Decimal
NOTIONAL = D("1000")   # independently modeled 1,000 USDT per candidate
TAKER_FEE = D("0.0006") # 0.06% per side; public standard Bitget fee (2026)
SLIPPAGE = {"fees_only": D("0"), "baseline": D("0.0005"),
            "stress": D("0.001")} # adverse EACH side (0/5/10 bps)
WINDOW_HOURS = 24

def valid_price_geometry(row):
    if row.get("direction") not in {"SHORT","LONG"}:
        return False
    try:
        ep=D(str(row["entry_price"])); sl=D(str(row["stop_loss"])); tp=D(str(row["take_profit"]))
    except (TypeError,ValueError):
        return False
    if not all(x.is_finite() and x>0 for x in (ep,sl,tp)):
        return False
    return (tp<ep<sl) if row["direction"]=="SHORT" else (sl<ep<tp)

def frozen_candidates(cohort):
    """Only as-of recorded input fields are used in candidate selection."""
    seen_ids=set()
    ordered=sorted(cohort,key=lambda x:(as_utc_ms(x["detected_at_utc"]),x["signal_id"]))
    selected={}
    for row in ordered:
        if row["signal_id"] in seen_ids:
            raise ValueError("duplicate signal ID")
        seen_ids.add(row["signal_id"])
        if row.get("trade_permission") is not False:
            raise ValueError("never evaluate signals with trading permission in blocked-only pilot")
        if not valid_price_geometry(row):
            continue
        detection=as_utc_ms(row["detected_at_utc"])
        eval_start=(detection//HOUR_MS+1)*HOUR_MS
        if not row.get("created_at") or as_utc_ms(row["created_at"])>eval_start:
            continue
        selected.setdefault(row["symbol"],row)
    if set(selected)!=set(SYMBOLS):
        raise ValueError("no complete as-of candidate for one or more required pilot symbols")
    return selected

def model_return(entry,stop,target,direction,exit_status,fee,slip):
    """Per 1,000 reference-USDT notional, no leverage and no assumed funding."""
    if exit_status not in {"TP_FIRST","SL_FIRST"}:
        return None
    ep,sl,tp=map(lambda v:D(str(v)),(entry,stop,target))
    if not (ep>0 and sl>0 and tp>0):
        raise ValueError("invalid prices")
    close=tp if exit_status=="TP_FIRST" else sl
    size=NOTIONAL/ep
    if direction=="SHORT":
        traded_entry=ep*(1-slip)
        traded_exit=close*(1+slip)
        gross=size*(ep-close)
        net=size*((traded_entry-traded_exit)-fee*(traded_entry+traded_exit))
        risk=size*(sl-ep)
    elif direction=="LONG":
        traded_entry=ep*(1+slip)
        traded_exit=close*(1-slip)
        gross=size*(close-ep)
        net=size*((traded_exit-traded_entry)-fee*(traded_entry+traded_exit))
        risk=size*(ep-sl)
    else:
        raise ValueError("unrecognized direction")
    if risk<=0:
        raise ValueError("wrong stop geometry")
    return {"gross_usdt":str(gross.quantize(D("0.000001"))),
            "net_ex_funding_usdt":str(net.quantize(D("0.000001"))),
            "net_ex_funding_pct_notional":str((net/NOTIONAL*100).quantize(D("0.000001"))),
            "nominal_stop_risk_usdt":str(risk.quantize(D("0.000001"))),
            "net_r_multiple":str((net/risk).quantize(D("0.000001")))}

def inspect_independent_opportunities(cohort,raw):
    original=replay(cohort,raw)
    if original["outcomes"] != OUTCOME_EXPECTED:
        raise ValueError("frozen 175-row replay does not match certified preliminary count")
    selected=frozen_candidates(cohort)
    bars={s:checked_source(s,raw[s])[0] for s in SYMBOLS}
    result=[]
    for symbol in SYMBOLS:
        row=selected[symbol]
        detected=as_utc_ms(row["detected_at_utc"])
        first=(detected//HOUR_MS+1)*HOUR_MS
        window=[bars[symbol].get(first+i*HOUR_MS) for i in range(WINDOW_HOURS)]
        if any(x is None for x in window):
            raise ValueError("missing 24-hour closed price bars")
        outcome=investigate(
            Setup(signal_id=row["signal_id"],direction=row["direction"],
                  entry=D(str(row["entry_price"])),stop=D(str(row["stop_loss"])),
                  target=D(str(row["take_profit"])),disposition="BLOCKED"),
            window)
        cost={k:model_return(row["entry_price"],row["stop_loss"],row["take_profit"],
                             row["direction"],outcome.status,TAKER_FEE,v)
              for k,v in SLIPPAGE.items()}
        result.append({"symbol":symbol,"signal_id":row["signal_id"],
                       "detected_at_utc":row["detected_at_utc"],
                       "direction":row["direction"],
                       "hypothetical_outcome":outcome.status,
                       "entry_hour_utc":outcome.entry_at,
                       "exit_hour_utc":outcome.exit_at,
                       "entry":str(row["entry_price"]),
                       "stop":str(row["stop_loss"]),
                       "target":str(row["take_profit"]),
                       "fee_slippage_scenarios":cost,
                       "trade_permission":False})
    complete=sum(valid_price_geometry(r) for r in cohort)
    if complete!=43:
        raise ValueError("unexpected number of complete frozen signal instances")
    return {"source_signal_instances":len(cohort),"directional_signal_instances":
            sum(x.get("direction") in {"LONG","SHORT"} for x in cohort),
            "complete_signal_instances":complete,
            "distinct_symbol_candidates":len(result),
            "suppressed_complete_instances":complete-len(result),
            "market_regime_independent_observations":1,
            "selection_rule":"FIRST_ASOF_COMPLETE_PER_SYMBOL_PER_24H_DAY",
            "hypothetical_outcomes":dict(Counter(x["hypothetical_outcome"] for x in result)),
            "candidates":result,
            "scenario_net_totals":{
                k:str(sum(D(x["fee_slippage_scenarios"][k]["net_ex_funding_usdt"])
                          for x in result if x["fee_slippage_scenarios"][k] is not None))
                for k in SLIPPAGE
                if all(x["fee_slippage_scenarios"][k] is not None for x in result)
            },
            "cost_model":{"notional_usdt_per_candidate":str(NOTIONAL),
                          "taker_fee_per_side":str(TAKER_FEE),
                          "adverse_slippage_per_side":{k:str(v) for k,v in SLIPPAGE.items()},
                          "funding_excluded_from_main_net":"UNKNOWN_UNTIL_SEPARATE_VALIDATION"},
            "verified_fills":0,"historical_universe_certified":False,
            "profitability_certified":False,"research_only":True}

def run(archive,signals,certificate,out):
    # READ existing private evidence only. No modifying original files/hashes.
    out=Path(out).absolute()
    if not out.is_absolute() or out.exists():
        raise ValueError("new absolute directory required; no overwrite")
    raw,manifest=validate_sources(archive)
    cohort,snapshot_sha=validate_signals(signals)
    cert_path=Path(certificate)
    if cert_path.is_symlink() or not cert_path.is_file():
        raise ValueError("original certification is absent or symlinked")
    cert_bytes=cert_path.read_bytes()
    cert=json.loads(cert_bytes)
    if (cert.get("status")!="REPLAY_MATCH_PRELIMINARY_COUNTS"
            or cert.get("signals")!=175
            or cert.get("signals_sha256")!=snapshot_sha
            or cert.get("source_sha256")!={e["symbol"]:e["sha256"] for e in manifest["sources"]}
            or cert.get("outcomes")!=OUTCOME_EXPECTED
            or cert.get("zero_verified_fills") is not True):
        raise ValueError("existing private certificate or hashes do not match source evidence")
    result=inspect_independent_opportunities(cohort,raw)
    result["original_private_certificate_sha256"]=hashlib.sha256(cert_bytes).hexdigest()
    result["original_signals_sha256"]=snapshot_sha
    result["source_sha256"]={e["symbol"]:e["sha256"] for e in manifest["sources"]}
    result["account_profit"]=None
    result["realized_trades"]=0
    # Only now create a distinct private output directory, with no source writes.
    old=os.umask(0o077)
    try:
        out.mkdir(parents=True,mode=0o700,exist_ok=False)
        with (out/"v11_independent_research.json").open("x",encoding="utf-8") as f:
            json.dump(result,f,indent=2,ensure_ascii=False)
    finally:
        os.umask(old)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--archive",type=Path,required=True)
    p.add_argument("--signals",type=Path,required=True)
    p.add_argument("--certificate",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    result=run(args.archive,args.signals,args.certificate,args.out)
    print(json.dumps({k:result[k] for k in
        ("source_signal_instances","complete_signal_instances",
         "distinct_symbol_candidates","hypothetical_outcomes",
         "scenario_net_totals","verified_fills","research_only")},indent=2))
