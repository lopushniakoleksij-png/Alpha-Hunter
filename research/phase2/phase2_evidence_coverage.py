"""Phase 2 historical hourly-candle evidence coverage gate. No I/O."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

@dataclass(frozen=True)
class CandleEvidence:
    symbol: str
    open_utc: str
    known_at_utc: str
    captured_at_utc: str
    source_exchange: str
    product_type: str
    granularity: str
    fully_closed: bool
    high: float
    low: float
    source_id: str

@dataclass(frozen=True)
class Coverage:
    status: str
    reason: str
    observed: int
    expected: int

def _utc(v: str):
    t=datetime.fromisoformat(v.replace("Z","+00:00"))
    if t.tzinfo is None or t.utcoffset() != timedelta(0):
        raise ValueError("UTC offset required")
    return t

def validate_hourly_window(symbol: str, start_utc: str, end_utc: str,
                           as_of_utc: str, candles: Sequence[CandleEvidence]) -> Coverage:
    """[start,end) hourly coverage; only fully closed known-at-time candles.
    Never promote episode-specific shadow coverage to whole-universe proof.
    """
    start,end,cutoff=map(_utc,(start_utc,end_utc,as_of_utc))
    duration=end-start
    if duration <= timedelta(0) or duration.total_seconds()%3600 or start.minute or start.second or start.microsecond:
        return Coverage("UNKNOWN","INVALID_WINDOW",0,0)
    expected=int(duration.total_seconds()//3600)
    if cutoff < end:
        return Coverage("UNKNOWN","WINDOW_NOT_YET_KNOWN",0,expected)
    matched=[c for c in candles if c.symbol==symbol and start<=_utc(c.open_utc)<end]
    if len({c.open_utc for c in matched})!=len(matched):
        return Coverage("UNKNOWN","DUPLICATE_HOURLY_CANDLE",len(matched),expected)
    if any(not c.source_id or c.source_exchange.upper()!="BITGET" or
           c.product_type.upper() not in {"USDT-M","USDT-FUTURES","USDT_PERPETUAL"} or
           c.granularity.upper() not in {"1H","1HOUR"} or not c.fully_closed or
           c.low>c.high or c.low<=0 or
           _utc(c.known_at_utc)>cutoff or _utc(c.captured_at_utc)>cutoff
           for c in matched):
        return Coverage("UNKNOWN","INVALID_OR_FUTURE_EVIDENCE",len(matched),expected)
    timestamps={_utc(c.open_utc) for c in matched}
    required={start+timedelta(hours=i) for i in range(expected)}
    if timestamps!=required:
        return Coverage("UNKNOWN","INCOMPLETE_HOURLY_WINDOW",len(matched),expected)
    return Coverage("COMPLETE","HOURLY_CANDLES_PRESENT",len(matched),expected)
