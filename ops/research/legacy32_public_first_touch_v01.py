"""Read-only historical first-touch bar replay for frozen 32 legacy paper exits.

Only public Bitget USDT-FUTURES market OHLC. This does NOT authenticate
historical best bid/ask, depth, fill quantity, OCO state or execution price.
No future sealed cohort, no data writes, no trading decisions.
"""
import argparse, hashlib, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

SOURCE="BITGET_PUBLIC_V3_MARKET_1M_BAR"
ENDPOINT="https://api.bitget.com/api/v3/market/history-candles"
MINUTE=60000
MAX_PAGES_PER_TRADE=350
MANIFEST=Path("ops/research/legacy32_canonical_manifest_readonly_20261017.json")


def ms(value):
    return int(datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()*1000)


def fetch(symbol, a, b, shard_dir, page):
    params=dict(category="USDT-FUTURES",symbol=symbol,interval="1m",
                type="market",startTime=a-MINUTE,endTime=b+MINUTE,limit=100)
    url=ENDPOINT+"?"+urllib.parse.urlencode(params)
    request=urllib.request.Request(url,headers={
        "User-Agent":"AlphaHunter-Immutable-Legacy-Bar-Evidence/1.0",
        "Accept":"application/json"})
    last_error=None
    for retry in range(4):
        try:
            with urllib.request.urlopen(request,timeout=22) as response:
                if response.status!=200:
                    raise ValueError("HTTP_STATUS_"+str(response.status))
                raw=response.read(180000)
            obj=json.loads(raw)
            if obj.get("code")!="00000" or not isinstance(obj.get("data"),list):
                raise ValueError("BITGET_API_"+str(obj.get("code"))+
                                 "_"+str(obj.get("msg"))[:70])
            target=shard_dir/("raw_"+str(page).zfill(3)+".json")
            target.write_bytes(raw)
            digest=hashlib.sha256(raw).hexdigest()
            return obj["data"],{"page":page,"window_start":a,"window_end":b,
                                  "raw_sha256":digest,"count":len(obj["data"]),
                                  "exchange_request_ms":obj.get("requestTime")}
        except Exception as ex:
            last_error=str(ex)
            if retry<3: time.sleep(.45*(retry+1))
    raise ValueError("PUBLIC_FETCH_FAILED_"+str(last_error)[:90])


def one(trade, folder):
    folder.mkdir(parents=True,exist_ok=True)
    begin,finish=ms(trade["entry_at_utc"]),ms(trade["recorded_exit_at_utc"])
    first=(begin//MINUTE)*MINUTE
    last=(finish//MINUTE)*MINUTE
    expected=(last-first)//MINUTE+1
    report=dict(exit_fill_id=trade["exit_fill_id"],entry_order_id=trade["entry_order_id"],
                symbol=trade["symbol"],direction=trade["direction"],
                recorded_exit_reason=trade["exit_reason"],observed_exit_at=trade["recorded_exit_at_utc"],
                source=SOURCE,expected_candles=expected,observed_candles=0,
                pages=0,full_bar_coverage=False,first_touch=None,
                stop_vs_target_ordering_verified=False,
                source_authentication="TLS_ONLY_NOT_INDEPENDENTLY_ATTESTED",
                quote_depth_authenticated=False,executable_fill_verified=False,
                counterfactual_only=True,profitability_claim_permitted=False,
                sealed_R9_trade=False,trade_permission=False,
                status="DATA_INSUFFICIENT")
    if expected<1 or expected>MAX_PAGES_PER_TRADE*90:
        report["reason"]="WINDOW_TOO_LARGE_OR_INVALID";return report
    book={};proof=[]
    try:
        for idx,j in enumerate(range(0,expected,90)):
            a=first+j*MINUTE;b=first+min(expected-1,j+89)*MINUTE
            rows,digest=fetch(trade["symbol"],a,b,folder,idx)
            proof.append(digest)
            for raw in rows:
                if not isinstance(raw,list) or len(raw)<5:
                    raise ValueError("MALFORMED_BAR")
                timestamp=int(raw[0])
                if not a<=timestamp<=b:continue
                if timestamp%MINUTE:raise ValueError("MISALIGNED_BAR")
                o,h,l,c=(Decimal(str(x)) for x in raw[1:5])
                if not (all(v.is_finite() and v>0 for v in (o,h,l,c))
                        and l<=min(o,c) and h>=max(o,c) and h>=l):
                    raise ValueError("INVALID_OHLC")
                values=[str(x) for x in (o,h,l,c)]
                if timestamp in book and book[timestamp]!=values:
                    raise ValueError("CONFLICTING_BAR")
                book[timestamp]=values
            time.sleep(.23)
        report["pages"]=len(proof)
        report["page_custody"]=proof
        report["observed_candles"]=len(book)
        missing=[first+k*MINUTE for k in range(expected) if first+k*MINUTE not in book]
        report["missing_minutes"]=len(missing)
        if missing:
            report["reason"]="MISSING_1M_HISTORY"
            report["first_missing_ms"]=missing[0]
            return report
        report["full_bar_coverage"]=True
        normalized=[[t,*book[t]] for t in sorted(book)]
        raw=json.dumps(normalized,separators=(",",":")).encode()
        report["normalized_path_sha256"]=hashlib.sha256(raw).hexdigest()
        (folder/"normalized_candles.json").write_bytes(raw)
        stop=Decimal(str(trade["stop_price"]))
        target=Decimal(str(trade["target_price"]))
        if not ((stop<target) if trade["direction"]=="LONG" else (target<stop)):
            raise ValueError("INVALID_STOP_TARGET_GEOMETRY")
        for stamp,o,h,l,c in normalized:
            hi,lo=Decimal(h),Decimal(l)
            stop_hit=lo<=stop if trade["direction"]=="LONG" else hi>=stop
            target_hit=hi>=target if trade["direction"]=="LONG" else lo<=target
            if not stop_hit and not target_hit:continue
            if stamp==first:touch="ENTRY_MINUTE_ORDER_AMBIGUOUS"
            elif stop_hit and target_hit:touch="STOP_AND_TARGET_SAME_MINUTE_AMBIGUOUS"
            elif stop_hit:touch="STOP_LOSS"
            else:touch="TAKE_PROFIT"
            report["first_touch"]=touch
            report["first_touch_minute_utc"]=datetime.fromtimestamp(
                stamp/1000,timezone.utc).isoformat()
            report["delay_first_touch_to_recorded_exit_minutes"]=round(
                (finish-stamp)/MINUTE,3)
            report["recorded_exit_reason_matches"]=(touch==trade["exit_reason"]
                if touch in ("STOP_LOSS","TAKE_PROFIT") else None)
            report["stop_vs_target_ordering_verified"]=(touch in ("STOP_LOSS","TAKE_PROFIT"))
            report["status"]="BAR_LEVEL_TOUCH_ONLY" if report["stop_vs_target_ordering_verified"] else "BAR_ORDERING_AMBIGUOUS"
            break
        if not report["first_touch"]:
            report["status"]="NO_TOUCH_IN_COMPLETE_1M_BAR_WINDOW"
    except Exception as exc:
        report["status"]="DATA_INSUFFICIENT"
        report["reason"]=str(exc)[:180]
        report["observed_candles"]=len(book)
        report["pages"]=len(proof)
        report["page_custody"]=proof
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--shard",type=int,required=True)
    parser.add_argument("--shards",type=int,default=4)
    parser.add_argument("--out",default="p0-public-research")
    args=parser.parse_args()
    manifest=MANIFEST.read_bytes()
    j=json.loads(manifest)
    assert j["historical_only"] and len(j["trades"])==32
    assert len(set(x["exit_fill_id"] for x in j["trades"]))==32
    folder=Path(args.out)/("shard_"+str(args.shard))
    folder.mkdir(parents=True,exist_ok=True)
    results=[]
    for idx,t in enumerate(j["trades"]):
        if idx%args.shards!=args.shard:continue
        result=one(t,folder/t["exit_fill_id"])
        results.append(result)
        print("P0_EXIT",json.dumps({k:v for k,v in result.items()
            if k not in ("page_custody",)},sort_keys=True),flush=True)
    payload={"manifest_sha256":hashlib.sha256(manifest).hexdigest(),
             "shard":args.shard,"shards":args.shards,
             "immutable_source_only":True,"results":results}
    (folder/"p0_summary.json").write_text(json.dumps(payload,indent=2,sort_keys=True))
    print("P0_SHARD_SUMMARY",json.dumps({
        "shard":args.shard,"trades":len(results),
        "complete_bar_windows":sum(x["full_bar_coverage"] for x in results),
        "source_insufficient":sum(x["status"]=="DATA_INSUFFICIENT" for x in results),
        "first_touch_disagreements":sum(x.get("recorded_exit_reason_matches") is False
                                        for x in results)}),flush=True)
    assert len(results)>0

if __name__=="__main__":
    main()
