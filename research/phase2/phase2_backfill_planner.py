"""Read-only Bitget historical backfill request planner. Does not make requests."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence
from urllib.parse import urlencode

BASE_URL = "https://api.bitget.com/api/v2/mix/market/history-candles"
MAX_LIMIT = 100
ALLOWED_SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"})

@dataclass(frozen=True)
class RequestSpec:
    symbol: str
    start_ms: int
    end_ms: int
    expected_hours: int
    url: str

def _utc(value: str) -> datetime:
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset()!=timedelta(0):
        raise ValueError("UTC offset required")
    return dt

def plan(symbols: Sequence[str], start_utc: str, end_utc: str,
         *, max_hours: int = 84) -> tuple[RequestSpec, ...]:
    """Plan bounded requests only; strict allowlist and max 7-day horizon."""
    if not symbols or len(set(symbols))!=len(symbols) or any(s not in ALLOWED_SYMBOLS for s in symbols):
        raise ValueError("symbols not allowed or duplicated")
    if not 1 <= max_hours <= MAX_LIMIT:
        raise ValueError("invalid request bound")
    start,end=_utc(start_utc),_utc(end_utc)
    if start.minute or start.second or start.microsecond or end.minute or end.second or end.microsecond:
        raise ValueError("hour-aligned timestamps required")
    hours=(end-start).total_seconds()/3600
    if hours<=0 or hours>168 or not hours.is_integer():
        raise ValueError("window must be 1-168 whole hours")
    out=[]
    for symbol in sorted(symbols):
        current=start
        while current<end:
            nxt=min(current+timedelta(hours=max_hours),end)
            a=int(current.timestamp()*1000); b=int(nxt.timestamp()*1000)
            expected=int((nxt-current).total_seconds()/3600)
            params=urlencode({"symbol":symbol,"productType":"USDT-FUTURES",
                              "granularity":"1H","startTime":a,
                              "endTime":b,"limit":expected})
            out.append(RequestSpec(symbol,a,b,expected,BASE_URL+"?"+params))
            current=nxt
    return tuple(out)
