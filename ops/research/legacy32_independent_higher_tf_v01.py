"""Independent, EX POST, public-data P1 directional context for frozen 32 exits.

This cannot establish what Alpha Hunter *used* at entry. Never backfill
12H/1D/1W as original strategy input. Every candle must have closed BEFORE
the historical entry. No model fitting, original outcome labels not consulted.
"""
import argparse,hashlib,json,time,urllib.parse,urllib.request
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path

MANIFEST=Path("ops/research/legacy32_canonical_manifest_readonly_20261017.json")
V3="https://api.bitget.com/api/v3/market/history-candles"
V2="https://api.bitget.com/api/v2/mix/market/history-candles"
DAY=86_400_000
TIMEFRAMES={"12H":(12*3600_000,20,50),"1D":(DAY,20,50),
            "1Wutc":(7*DAY,3,10)}


def iso(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()


def get_series(symbol,gran,entry_ms,folder,tag):
    span,fast,slow=TIMEFRAMES[gran]
    weekly=gran=="1Wutc"
    # 12H 37d, 1D 75d, weekly <90d; no later candle can be used.
    size=11 if weekly else 62  # <= 84 days under V2 maximum 90-day range
    a=entry_ms-(size+1)*span
    b=entry_ms
    params=(dict(symbol=symbol,productType="USDT-FUTURES",
                 granularity=gran,startTime=a,endTime=b,limit=100)
            if weekly else
            dict(category="USDT-FUTURES",symbol=symbol,interval=gran,type="market",
                 startTime=a,endTime=b,limit=100))
    endpoint=V2 if weekly else V3
    url=endpoint+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={
        "User-Agent":"AH-P1-ReadOnly-EXPOST-20261017","Accept":"application/json"})
    result=dict(symbol=symbol,timeframe=gran,
        endpoint="/api/v2/mix/market/history-candles" if weekly
                 else "/api/v3/market/history-candles",
        asof_utc=iso(entry_ms),lookahead_prohibited=True,
        source_authentication="TLS_ONLY_NOT_INDEPENDENTLY_ATTESTED",
        contemporaneous_strategy_signal_proof=False,
        status="DATA_INSUFFICIENT")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=20) as r:raw=r.read(180000)
            body=json.loads(raw)
            if body.get("code")!="00000" or not isinstance(body.get("data"),list):
                raise ValueError("API_"+str(body.get("code"))+
                                 "_"+str(body.get("msg"))[:70])
            folder.mkdir(parents=True,exist_ok=True)
            (folder/(tag+"_"+gran+".json")).write_bytes(raw)
            result["raw_response_sha256"]=hashlib.sha256(raw).hexdigest()
            bars={}
            for row in body["data"]:
                if not isinstance(row,list) or len(row)<5:raise ValueError("INVALID_BAR_SCHEMA")
                stamp=int(row[0])
                if stamp+span>entry_ms:continue  # reject lookahead/incomplete bar
                price=Decimal(str(row[4]))
                if not price.is_finite() or price<=0:raise ValueError("BAD_PRICE")
                if stamp in bars and bars[stamp]!=price:
                    raise ValueError("CONFLICTING_HISTORY")
                bars[stamp]=price
            ordered=sorted(bars.items())
            result["closed_bars"]=len(ordered)
            result["max_closed_bar_at_utc"]=iso(ordered[-1][0]+span) if ordered else None
            if len(ordered)<slow:
                result["reason"]="INSUFFICIENT_FULLY_CLOSED_BARS"
            elif any(ordered[i][0]-ordered[i-1][0]!=span
                     for i in range(len(ordered)-slow+1,len(ordered))):
                result["reason"]="NONCONTIGUOUS_LAST_SLOW_WINDOW"
            else:
                closes=[x[1] for x in ordered[-slow:]]
                fast_ma=sum(closes[-fast:])/fast
                slow_ma=sum(closes)/slow
                last=closes[-1]
                # Pre-registered deterministic research descriptor, NOT original signal.
                trend=("BULLISH" if last>slow_ma and fast_ma>slow_ma
                       else "BEARISH" if last<slow_ma and fast_ma<slow_ma
                       else "MIXED")
                result.update(status="RETROSPECTIVE_CLOSED_BAR_CONTEXT",
                    trend=trend,last_close=str(last),fast_mean=str(fast_ma),
                    slow_mean=str(slow_ma),fast_bars=fast,slow_bars=slow,
                    last_closed_bar_start_utc=iso(ordered[-1][0]))
            return result
        except Exception as exc:
            result["reason"]=str(exc)[:160]
            if attempt<2:time.sleep(.5*(attempt+1))
    return result


def one(trade,base):
    stamp=int(datetime.fromisoformat(
        trade["entry_at_utc"].replace("Z","+00:00")).timestamp()*1000)
    out=dict(exit_fill_id=trade["exit_fill_id"],symbol=trade["symbol"],
             direction=trade["direction"],entry_at_utc=trade["entry_at_utc"],
             original_12h_1d_1w_stored_at_decision=False,
             retrospective_not_admission_evidence=True,
             profitability_claim_permitted=False,trade_permission=False)
    assets=[trade["symbol"],"BTCUSDT","ETHUSDT"]
    out["sources"]={}
    for sym in assets:
        sources={}
        for gran in TIMEFRAMES:
            row=get_series(sym,gran,stamp,base, sym)
            sources[gran]=row
            time.sleep(.08)
        out["sources"][sym]=sources
    # Only retrospective descriptors, not approval of a new strategy.
    directions={sym:{"12H":out["sources"][sym]["12H"].get("trend"),
                     "1D":out["sources"][sym]["1D"].get("trend"),
                     "1Wutc":out["sources"][sym]["1Wutc"].get("trend")}
                for sym in assets}
    out["trends"]=directions
    good=all(directions[sym][k] in ("BULLISH","BEARISH","MIXED")
             for sym in assets for k in ("12H","1D","1Wutc"))
    out["full_higher_tf_coverage"]=good
    if good:
        side="BULLISH" if trade["direction"]=="LONG" else "BEARISH"
        out["asset_12h_1d_aligned_to_trade"]=all(
            directions[trade["symbol"]][k]==side for k in ("12H","1D"))
        out["btc_eth_12h_1d_regime_favors_trade"]=all(
            directions[sym][k]==side for sym in ("BTCUSDT","ETHUSDT")
            for k in ("12H","1D"))
        out["weekly_asset_context"]=directions[trade["symbol"]]["1Wutc"]
        out["status"]="RECONSTRUCTED_EX_POST_ONLY"
    else:
        out["status"]="INCOMPLETE_PUBLIC_CONTEXT"
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--shard",type=int,required=True)
    parser.add_argument("--shards",type=int,default=4)
    parser.add_argument("--out",default="p1-public-regime")
    args=parser.parse_args()
    manifest=json.loads(MANIFEST.read_text())
    assert len(manifest["trades"])==32
    base=Path(args.out)/("shard_"+str(args.shard))
    base.mkdir(parents=True,exist_ok=True)
    results=[]
    for i,t in enumerate(manifest["trades"]):
        if i%args.shards!=args.shard:continue
        row=one(t,base/t["exit_fill_id"])
        results.append(row)
        debug={k:v for k,v in row.items() if k!="sources"}
        debug["missing"]= [
            {"asset":sym,"timeframe":tf,"reason":source.get("reason"),
             "closed_bars":source.get("closed_bars")}
            for sym,panels in row["sources"].items()
            for tf,source in panels.items()
            if source["status"]!="RETROSPECTIVE_CLOSED_BAR_CONTEXT"
        ]
        print("P1_CONTEXT",json.dumps(debug,sort_keys=True),flush=True)
    (base/"p1_summary.json").write_text(json.dumps(
       {"shard":args.shard,"results":results,
        "context_only_not_proof_of_original_signal":True},indent=2,sort_keys=True))
    print("P1_SHARD_SUMMARY",json.dumps({"shard":args.shard,"total":len(results),
         "complete":sum(x["full_higher_tf_coverage"] for x in results),
         "incomplete":sum(not x["full_higher_tf_coverage"] for x in results)}),flush=True)
    assert results

if __name__=="__main__":
    main()
