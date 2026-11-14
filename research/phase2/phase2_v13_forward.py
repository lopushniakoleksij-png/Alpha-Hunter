"""Alpha Hunter V1.3 prospective frozen 30-day research evaluator.

Pure offline functions only. NO DB, HTTP, orders, scheduler, GitHub, or file
writes. All as-of gates and cost scenarios are fixed before 2026-11-15 UTC.
The existing scanner remains the only producer. Historical member and real
fill certification are never inferred from current market OHLC evidence.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from phase2_signal_investigator import Bar, Setup, investigate
from phase2_scientific_v11 import model_return, TAKER_FEE, SLIPPAGE

D=Decimal
SYMBOLS=("BTCUSDT","ETHUSDT","SOLUSDT")
START=datetime(2026,11,15,tzinfo=timezone.utc)
END=datetime(2026,12,15,tzinfo=timezone.utc)
FINAL_HORIZON=datetime(2026,12,16,tzinfo=timezone.utc)
HOUR=timedelta(hours=1)
COOLDOWN=timedelta(hours=24)
DAYS=30
GATE_KEYS=("rr_minimum_met","participation_confirmed","momentum_confirmed",
           "direction_aligned","structure_valid","funding_not_extreme",
           "data_integrity_min_88")
RESOLVED=("TP_FIRST","SL_FIRST")

def utc(value):
    if isinstance(value,datetime):d=value
    else:d=datetime.fromisoformat(str(value).replace(" ","T").replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset()!=timedelta(0):
        raise ValueError("strict UTC timestamp required")
    return d.astimezone(timezone.utc)

def day_key(t):
    return utc(t).date().isoformat()

def geometry(row):
    if row.get("direction") not in ("LONG","SHORT"):
        return False
    try:
        ep,sl,tp=(D(str(row[k])) for k in ("entry_price","stop_loss","take_profit"))
        if not all(x.is_finite() and x>0 for x in (ep,sl,tp)):return False
    except (InvalidOperation,TypeError,ValueError,KeyError):return False
    return (sl<ep<tp) if row["direction"]=="LONG" else (tp<ep<sl)

def first_full_hour(detection):
    t=utc(detection)
    return t.replace(minute=0,second=0,microsecond=0)+HOUR

def gates(row):
    checks=row.get("execution_checks")
    if checks is None:checks={}
    if not isinstance(checks,dict):raise ValueError("invalid original execution-checks snapshot")
    result={}
    for key in GATE_KEYS:
        v=checks.get(key)
        result[key]="PASS" if v is True else "FAIL" if v is False else "MISSING"
    result["all_required_execution_checks"]=(
        "PASS" if all(result[k]=="PASS" for k in GATE_KEYS) else
        "MISSING" if any(result[k]=="MISSING" for k in GATE_KEYS) else "FAIL")
    return result

def regime(previous_close,prior_close):
    p=D(str(previous_close));b=D(str(prior_close))
    if not (p.is_finite() and b.is_finite() and p>0 and b>0):
        raise ValueError("invalid completed BTC daily closes")
    pct=(p/b-D("1"))*100
    return {"regime":"RISING" if pct>D("1") else "FALLING" if pct<D("-1") else "SIDEWAYS",
            "prior_completed_day_return_pct":str(pct.quantize(D("0.000001")))}

def select_from_existing_scanner(records):
    """30-day cohort, earliest as-of complete signal / symbol / UTC day;
    cross-day cooldown intentionally suppresses a whole next day if the prior
    candidate is less than 24 hours old at its 00:00 start. Never replace.
    No outcome, future OHLC, ranking, filter or trade-permission selection.
    """
    rows=list(records)
    seen=set();sorted_rows=[]
    for r in rows:
        if r.get("signal_id") in seen or not r.get("signal_id"):
            raise ValueError("duplicate or blank signal id")
        seen.add(r["signal_id"])
        sym=r.get("symbol");timestamp=utc(r["detected_at_utc"])
        if sym not in SYMBOLS or not START<=timestamp<END:
            raise ValueError("not part of preregistered cohort")
        sorted_rows.append((timestamp,str(r["signal_id"]),r))
    sorted_rows.sort(key=lambda x:(x[0],x[1]))
    by_day=defaultdict(list)
    for ts,sid,r in sorted_rows:by_day[(ts.date().isoformat(),r["symbol"])].append((ts,sid,r))
    selected=[];log=[];last_for_symbol={}
    for offset in range(DAYS):
        date=(START+timedelta(days=offset)).date().isoformat()
        midnight=START+timedelta(days=offset)
        for sym in SYMBOLS:
            group=by_day.get((date,sym),[])
            prior=last_for_symbol.get(sym)
            if prior is not None and midnight<prior+COOLDOWN:
                log.append({"day":date,"symbol":sym,"status":"COOLDOWN_SUPPRESSED",
                            "observed_records":len(group)})
                continue
            eligible=[]
            for ts,sid,r in group:
                if not geometry(r):continue
                if not r.get("created_at"):continue
                created=utc(r["created_at"])
                if not ts<=created<=first_full_hour(ts):continue
                eligible.append((ts,sid,r))
            if not eligible:
                # Not a confirmed empty universe without parent-child audit.
                log.append({"day":date,"symbol":sym,"status":"NO_ASOF_COMPLETE_SIGNAL",
                            "observed_records":len(group)})
                continue
            ts,sid,r=eligible[0]
            # original blocked/trade permission is only informational
            decision={"day":date,"symbol":sym,"signal_id":sid,
                      "detected_at_utc":ts.isoformat(),
                      "created_at":utc(r["created_at"]).isoformat(),
                      "direction":r["direction"],
                      "entry_price":str(r["entry_price"]),
                      "stop_loss":str(r["stop_loss"]),
                      "take_profit":str(r["take_profit"]),
                      "trade_permission":r.get("trade_permission"),
                      "trade_permission_reason":r.get("trade_permission_reason"),
                      "blocking_gate":r.get("blocking_gate"),
                      "gate_states":gates(r),
                      "nominal_stop_risk_usdt":str((D("1000")*
                        abs(D(str(r["stop_loss"]))-D(str(r["entry_price"])))/
                        D(str(r["entry_price"]))).quantize(D("0.000001")))}
            selected.append(decision);last_for_symbol[sym]=ts
            log.append({"day":date,"symbol":sym,"status":"SELECTED",
                        "observed_records":len(group),"signal_id":sid})
    return {"selected":selected,"day_symbol_log":log,"observed_signal_rows":len(rows),
            "selected_count":len(selected),
            "real_order_authority":False,
            "historical_universe_certified":False,
            "scientific_profitability_certified":False}

def evaluate_closed_hourly(candidate,source,as_of_utc,
                           *,evidence_valid=False,instrument_eligible=False):
    """Only a verified hourly source with a fully matured horizon can be used.
    source: 24 OHLC dictionaries with UTC candle-open timestamp + high/low.
    This does not assert executable fills or historical venue eligibility.
    """
    start=first_full_hour(candidate["detected_at_utc"])
    asof=utc(as_of_utc)
    if asof<start+24*HOUR:
        return {"status":"PENDING","hypothetical_costs":None}
    if not evidence_valid:
        return {"status":"UNKNOWN","reason":"CANDLE_EVIDENCE_NOT_CERTIFIED","hypothetical_costs":None}
    if not instrument_eligible:
        # The research probe may still show counterfactual touches, but without
        # historical venue eligibility it must not certify trading evidence.
        eligibility="UNKNOWN"
    else:eligibility="VERIFIED"
    if not isinstance(source,(list,tuple)) or len(source)!=24:
        return {"status":"UNKNOWN","reason":"MISSING_CONSECUTIVE_BARS","hypothetical_costs":None}
    bars=[]
    for index,row in enumerate(source):
        try:
            t=utc(row["t"])
            h=D(str(row["high"]));l=D(str(row["low"]))
        except (ValueError,KeyError,TypeError,InvalidOperation):
            return {"status":"UNKNOWN","reason":"INVALID_BAR","hypothetical_costs":None}
        if (t!=start+HOUR*index or not all(v.is_finite() and v>0 for v in (h,l))
                or l>h):
            return {"status":"UNKNOWN","reason":"OHLC_TIME_OR_GEOMETRY","hypothetical_costs":None}
        bars.append(Bar(timestamp_utc=t.isoformat(),high=h,low=l))
    setup=Setup(signal_id=candidate["signal_id"],direction=candidate["direction"],
                entry=D(candidate["entry_price"]),stop=D(candidate["stop_loss"]),
                target=D(candidate["take_profit"]),disposition="BLOCKED")
    finding=investigate(setup,bars)
    costs={name:model_return(candidate["entry_price"],candidate["stop_loss"],
           candidate["take_profit"],candidate["direction"],finding.status,
           TAKER_FEE,slip) for name,slip in SLIPPAGE.items()}
    return {"status":finding.status,"reason":finding.reason,
            "entry_at":finding.entry_at,"exit_at":finding.exit_at,
            "historical_instrument_eligibility":eligibility,
            "hypothetical_costs":costs,
            "executed_fills":0}

def compare_original_checks(selected_with_outcomes,gate):
    if gate not in GATE_KEYS and gate!="all_required_execution_checks":
        raise ValueError("gate not frozen in preregistration")
    outcome={}
    for name in ("PASS","FAIL","MISSING"):
        group=[x for x in selected_with_outcomes
               if x["gate_states"][gate]==name]
        resolved=[x for x in group if x.get("outcome",{}).get("status") in RESOLVED and
                  x.get("outcome",{}).get("hypothetical_costs",{}).get("baseline") is not None]
        unknown=[x for x in group if x.get("outcome",{}).get("status") in
                 ("UNKNOWN","AMBIGUOUS","OPEN_AT_HORIZON","PENDING")]
        total=sum((D(x["outcome"]["hypothetical_costs"]["baseline"]["net_ex_funding_usdt"])
                   for x in resolved),D("0"))
        outcome[name]={"candidates":len(group),"resolved":len(resolved),
                       "unresolved":len(unknown),
                       "no_entry":sum(x.get("outcome",{}).get("status")=="NO_ENTRY" for x in group),
                       "resolved_only_hypothetical_net_usdt":
                       str(total.quantize(D("0.000001"))) if resolved else None}
    outcome["comparison_status"]=("DESCRIPTIVE_ONLY_NOT_CAUSAL"
        if outcome["PASS"]["resolved"] and outcome["FAIL"]["resolved"]
        else "NOT_COMPARABLE")
    return outcome
