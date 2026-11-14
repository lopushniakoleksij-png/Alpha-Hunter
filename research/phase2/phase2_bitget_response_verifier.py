"""Offline verifier for saved public Bitget hourly API responses. No network or DB."""
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

@dataclass(frozen=True)
class Verification:
    status: str
    reason: str
    raw_sha256: str
    symbol: str
    expected_hours: int
    observed_hours: int
    first_ms: int | None
    last_ms: int | None
    request_time_ms: int | None

def verify_response(raw: bytes, *, symbol: str, start_ms: int,
                    end_ms: int, product_type: str = "USDT-FUTURES",
                    granularity: str = "1H") -> Verification:
    """Fail closed: no market identity proof can be inferred from API body alone.
    Caller must preserve URL/request metadata alongside this verification.
    """
    digest=hashlib.sha256(raw).hexdigest()
    expected=(end_ms-start_ms)//3600000 if end_ms>start_ms else 0
    def result(status, reason, n=0, first=None, last=None, rt=None):
        return Verification(status,reason,digest,symbol,expected,n,first,last,rt)
    if product_type!="USDT-FUTURES" or granularity!="1H" or not symbol.endswith("USDT"):
        return result("UNKNOWN","REQUEST_MARKET_NOT_ALLOWED")
    if start_ms%3600000 or end_ms%3600000 or end_ms<=start_ms or (end_ms-start_ms)%3600000 or expected>100:
        return result("UNKNOWN","INVALID_REQUEST_WINDOW")
    try:
        p=json.loads(raw)
        if not isinstance(p,dict) or p.get("code")!="00000" or not isinstance(p.get("data"),list):
            return result("UNKNOWN","API_RESPONSE_FAILURE")
        rows=p["data"]
        rt=int(p["requestTime"]) if "requestTime" in p else None
        if len(rows)!=expected:
            return result("UNKNOWN","INCOMPLETE_WINDOW",len(rows),rt=rt)
        stamps=[]
        for i,row in enumerate(rows):
            if not isinstance(row,list) or len(row)<5:
                return result("UNKNOWN","MALFORMED_CANDLE",len(rows),rt=rt)
            ts=int(row[0]); stamps.append(ts)
            if ts!=start_ms+i*3600000:
                return result("UNKNOWN","TIMESTAMP_GAP_OR_ORDER",len(rows),stamps[0],ts,rt)
            op,hi,lo,cl=[Decimal(str(x)) for x in row[1:5]]
            if not all(x.is_finite() for x in (op,hi,lo,cl)) or lo<=0 or lo>min(op,cl) or hi<max(op,cl):
                return result("UNKNOWN","INVALID_OHLC",len(rows),stamps[0],ts,rt)
        return result("PASS","COMPLETE_HOURLY_WINDOW",len(rows),stamps[0],stamps[-1],rt)
    except (ValueError,TypeError,KeyError,InvalidOperation,UnicodeDecodeError):
        return result("UNKNOWN","INVALID_JSON_OR_FIELDS")
