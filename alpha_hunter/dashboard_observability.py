"""Pure, read-only dashboard observability when a compact scan lost child writes.

No execution authority, no trading price/SL/TP suggestion and no stale
research value may enter the canonical action gate from this module.
"""
from __future__ import annotations

from typing import Any

REFERENCE_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}
STRATEGY_PRIORITY = {"SHADOW_CANDIDATE":4, "WATCH":3, "DATA_INSUFFICIENT":2, "NO_SETUP":1}

def inspect_child_stage(row: dict[str, Any], payload: dict[str, Any],
                        children: list[dict[str, Any]]) -> dict[str, Any]:
    """Fail closed on count, duplicates, symbol mismatch or malformed content."""
    expected = row.get("symbol_count")
    compact = payload.get("symbols")
    if not isinstance(compact, list):
        return {"status":"INCOMPLETE","reason":"PARENT_SYMBOL_MANIFEST_UNAVAILABLE",
                "expected":expected,"persisted":0,"symbols":[]}
    if isinstance(expected,bool) or not isinstance(expected,int):
        expected=len(compact)
    if expected<=0 or expected!=len(compact):
        return {"status":"INCOMPLETE","reason":"PARENT_SYMBOL_MANIFEST_MISMATCH",
                "expected":expected,"persisted":len(children),"symbols":[]}
    parent_ids=[p.get("symbol") if isinstance(p,dict) else None for p in compact]
    expected_set=set(parent_ids)
    if None in expected_set or "" in expected_set or len(expected_set)!=expected:
        return {"status":"INCOMPLETE","reason":"PARENT_SYMBOL_IDENTITY_INVALID",
                "expected":expected,"persisted":len(children),"symbols":[]}
    detail=[]
    actual_ids=[]
    for child in children:
        if not isinstance(child,dict):
            continue
        symbol=child.get("symbol")
        data=child.get("payload")
        if isinstance(symbol,str) and isinstance(data,dict) and data.get("symbol")==symbol:
            actual_ids.append(symbol)
            detail.append(data)
    if (len(children)!=expected or len(actual_ids)!=expected
            or len(set(actual_ids))!=expected or set(actual_ids)!=expected_set):
        return {"status":"INCOMPLETE","reason":"CHILD_RECORDS_MISSING_OR_MISMATCHED",
                "expected":expected,"persisted":len(actual_ids),"symbols":[]}
    return {"status":"COMPLETE_SYMBOL_ROWS_NOT_MONITORING_PROOF","reason":"EXACT_CHILD_MANIFEST_MATCH",
            "expected":expected,"persisted":len(detail),"symbols":detail}


def format_historical_research(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Label stale evidence explicitly; NEVER call strategy/action execution gates."""
    if not isinstance(snapshot,dict) or snapshot.get("_detail_integrity")!="COMPLETE_SYMBOL_ROWS_NOT_MONITORING_PROOF":
        return None
    rows=snapshot.get("symbols")
    if not isinstance(rows,list) or not rows:
        return None
    discovery=[]
    strategies=[]
    reference=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get("symbol"),str):
            continue
        symbol=row["symbol"]
        if symbol in REFERENCE_SYMBOLS:
            reference.append({"symbol":symbol,"price":row.get("last_price")})
            continue
        discovery.append({
            "symbol":symbol, "state":str(row.get("state") or "UNKNOWN"),
            "phase":str(row.get("market_phase") or "UNKNOWN"),
            "timing":str(row.get("opportunity_timing") or "UNKNOWN"),
            "behaviour":row.get("behaviour_score"),
        })
        engine=row.get("multi_strategy_engine")
        if isinstance(engine,dict):
            for item in engine.get("strategies",[]):
                if not isinstance(item,dict):
                    continue
                strategies.append({
                    "symbol":symbol,
                    "strategy_id":str(item.get("strategy_id") or "?"),
                    "status":str(item.get("status") or "UNKNOWN"),
                    "direction":str(item.get("direction") or "NONE"),
                    "score":item.get("signal_score"),
                    "shadow_only":True,
                })
    strategies.sort(key=lambda item:(
        STRATEGY_PRIORITY.get(item["status"],0),
        _number(item.get("score")),
    ),reverse=True)
    discovery.sort(key=lambda item:_number(item.get("behaviour")),reverse=True)
    return {
        "status":"HISTORICAL_RESEARCH_ONLY_NOT_LIVE_NOT_EXECUTABLE",
        "run_id":snapshot.get("run_id"),
        "collected_at_utc":snapshot.get("collected_at_utc"),
        "persisted_symbols":len(rows),
        "research":discovery[:25],
        "strategies":strategies[:40],
        "references":sorted(reference,key=lambda item:item["symbol"]),
        "trade_permission":False,
        "execution_authority":False,
        "scientific_pass_permitted":False,
    }


def _number(value: Any) -> float:
    try:
        number=float(value)
        return number if number==number and abs(number)<1e20 else 0.0
    except (TypeError,ValueError):
        return 0.0
