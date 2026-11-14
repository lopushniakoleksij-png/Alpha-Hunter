"""Phase 2 scientific pilot V1.0 — reproducible OFFLINE 24h adjudication.

Consumes privately obtained signal snapshots and exact raw public Bitget 1H
market-candle responses for 2026-11-08–10 UTC. This file deliberately has
NO network, database, exchange-order, or write capabilities. It cannot
certify historical instrument tradability, fills, or portfolio profitability.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from phase2_bitget_response_verifier import verify_response
from phase2_signal_investigator import Bar, Setup, investigate

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
SOURCE_START_MS = 1794096000000  # 2026-11-08 00:00 UTC
SOURCE_END_MS = 1794268800000    # 2026-11-10 00:00 UTC
COHORT_END_MS = 1794182400000    # 2026-11-09 00:00 UTC
HOUR_MS = 3600000

def as_utc_ms(value):
    d = datetime.fromisoformat(str(value).replace(" ", "T").replace("Z", "+00:00"))
    if d.utcoffset() is None or d.utcoffset().total_seconds() != 0:
        raise ValueError("UTC timestamp required")
    return int(d.timestamp() * 1000)

def checked_source(symbol, raw):
    check = verify_response(raw, symbol=symbol, start_ms=SOURCE_START_MS,
                            end_ms=SOURCE_END_MS)
    if check.status != "PASS" or check.observed_hours != 48:
        raise ValueError(f"{symbol} source evidence rejected: {check.reason}")
    payload = json.loads(raw)
    bars = {
        int(r[0]): Bar(
            timestamp_utc=datetime.fromtimestamp(int(r[0])/1000,timezone.utc).isoformat(),
            high=Decimal(str(r[2])), low=Decimal(str(r[3]))
        ) for r in payload["data"]
    }
    return bars, {"sha256":check.raw_sha256,
                  "api_request_time_ms":check.request_time_ms,
                  "verified_hours":check.observed_hours}

def replay(signals, raw_by_symbol):
    """Fail closed on missing/invalid price evidence; never infer executed trades."""
    if set(raw_by_symbol) != set(SYMBOLS):
        raise ValueError("pilot requires exactly BTC, ETH and SOL source records")
    sources = {s:checked_source(s,raw_by_symbol[s]) for s in SYMBOLS}
    seen = set()
    findings = []
    for s in signals:
        sym = s["symbol"]
        if sym not in SYMBOLS:
            raise ValueError("outside pilot symbol cohort")
        signal_id = s["signal_id"]
        if signal_id in seen:
            raise ValueError("duplicate signal ID")
        seen.add(signal_id)
        detected = as_utc_ms(s["detected_at_utc"])
        if not SOURCE_START_MS <= detected < COHORT_END_MS:
            raise ValueError("outside frozen 8 Nov signal cohort")
        if s.get("trade_permission") is not False:
            raise ValueError("pilot requires research-only signals, no permitted trades")
        start = ((detected // HOUR_MS) + 1)*HOUR_MS
        raw_created = s.get("created_at")
        if raw_created is None:
            status,reason = "UNKNOWN","CREATED_AT_NOT_RECORDED"
        elif as_utc_ms(raw_created) > start:
            status,reason = "UNKNOWN","NOT_KNOWN_BEFORE_FIRST_EVALUATION_HOUR"
        else:
            by_time = sources[sym][0]
            window = [by_time.get(start+i*HOUR_MS) for i in range(24)]
            if any(b is None for b in window):
                raise ValueError("incomplete 24-hour as-of candle window")
            def d(name):
                value=s.get(name)
                return None if value is None else Decimal(str(value))
            outcome=investigate(
                Setup(signal_id=signal_id, direction=s.get("direction") or "",
                      entry=d("entry_price"),stop=d("stop_loss"),
                      target=d("take_profit"),disposition="BLOCKED"),
                window)
            status,reason=outcome.status,outcome.reason
        findings.append({"signal_id":signal_id,"symbol":sym,
                         "status":status,"reason":reason,
                         "trade_permission":False})
    total_by_symbol = {}
    for symbol in SYMBOLS:
        ss = [f for f in findings if f["symbol"]==symbol]
        total_by_symbol[symbol]={"records":len(ss),
                                  "outcomes":dict(sorted(Counter(f["status"] for f in ss).items()))}
    return {"source_evidence":{s:sources[s][1] for s in SYMBOLS},
            "cohort_size":len(findings),
            "by_symbol":total_by_symbol,
            "outcomes":dict(sorted(Counter(f["status"] for f in findings).items())),
            "research_only":True,
            "historical_universe_certified":False,
            "verified_executable_fills":0,
            "findings":findings}
