"""Research ONLY: bounded successor symbol-child persistence with exact readback.

Never imported by the production scanner. Does not modify production data,
the configured 12s/15s timeouts, R10 admission or 35m paper-monitoring rule.
One verified child stage is NOT a complete paper monitoring cycle or trade.
"""
from __future__ import annotations
import hashlib
import json
from typing import Any, Callable

class SuccessorChildStageIncomplete(RuntimeError):
    pass

def _canonical(data: Any) -> str:
    return json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)

def child_manifest_sha256(rows: list[dict[str,Any]]) -> str:
    ordered=sorted((r["symbol"],r["payload"]) for r in rows)
    return hashlib.sha256(_canonical(ordered).encode("utf-8")).hexdigest()

def validated_child_batches(
    rows: list[dict[str,Any]],batch_size: int=12
) -> list[list[dict[str,Any]]]:
    """Strictly reject missing/duplicate symbols, mixed runs and malformed data."""
    if type(batch_size) is not int or not 1<=batch_size<=32:
        raise ValueError("INVALID_REVIEW_ONLY_BATCH_SIZE")
    if not isinstance(rows,list) or len(rows)==0:
        raise ValueError("EXPECTED_SYMBOL_MANIFEST_MISSING")
    seen=set()
    run=None
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("SYMBOL_CHILD_INVALID")
        symbol=row.get("symbol")
        rid=row.get("run_id")
        payload=row.get("payload")
        if (not isinstance(symbol,str) or not symbol or symbol!=symbol.upper()
                or not isinstance(rid,str) or not rid
                or not isinstance(payload,dict)
                or payload.get("symbol")!=symbol):
            raise ValueError("SOURCE_SYMBOL_IDENTITY_INVALID")
        if run is None:
            run=rid
        if rid!=run or symbol in seen:
            raise ValueError("MIXED_RUN_OR_DUPLICATE_SYMBOL")
        seen.add(symbol)
    # Verify digest can be produced BEFORE the first write. Never send a
    # partially malformed batch or NaN/Infinity through the PostgREST path.
    child_manifest_sha256(rows)
    return [rows[i:i+batch_size] for i in range(0,len(rows),batch_size)]

def persist_and_verify_bounded_children(
    rows: list[dict[str,Any]],
    *,
    write_batch: Callable[[list[dict[str,Any]]],None],
    read_back: Callable[[str],list[dict[str,Any]]],
    batch_size: int=12,
) -> dict[str,Any]:
    """PostgreSQL commit/readback must be independently done by supplied adapter.

    Partial batches are possible if a later request fails; the transaction
    spanning an HTTP request is NOT global to all batches. Do not issue or
    return a success receipt on exception, timeout, missing or different data.
    """
    batches=validated_child_batches(rows,batch_size=batch_size)
    run_id=rows[0]["run_id"]
    expected={r["symbol"]:r["payload"] for r in rows}
    expected_sha=child_manifest_sha256(rows)
    try:
        for batch in batches:
            write_batch(batch)
    except Exception as exc:
        raise SuccessorChildStageIncomplete(
            "UNKNOWN_OR_INCOMPLETE_CHILD_WRITE_FAILED; source persists may be partial"
        ) from exc
    try:
        observed=read_back(run_id)
    except Exception as exc:
        raise SuccessorChildStageIncomplete(
            "UNKNOWN_OR_INCOMPLETE_CHILD_READBACK_FAILED"
        ) from exc
    if not isinstance(observed,list) or len(observed)!=len(rows):
        raise SuccessorChildStageIncomplete(
            f"UNKNOWN_OR_INCOMPLETE_CHILD_CARDINALITY {len(observed) if isinstance(observed,list) else 'unavailable'}/{len(rows)}"
        )
    actual={}
    for row in observed:
        if not isinstance(row,dict):
            raise SuccessorChildStageIncomplete("UNKNOWN_OR_INCOMPLETE_CHILD_MALFORMED")
        symbol=row.get("symbol")
        data=row.get("payload")
        if symbol in actual or symbol not in expected or not isinstance(data,dict):
            raise SuccessorChildStageIncomplete("UNKNOWN_OR_INCOMPLETE_CHILD_IDENTITY")
        actual[symbol]=data
    if actual!=expected or child_manifest_sha256(observed)!=expected_sha:
        raise SuccessorChildStageIncomplete("UNKNOWN_OR_INCOMPLETE_CHILD_PAYLOAD_MISMATCH")
    return {
        "status":"PERSISTED_SOURCE_CHILD_MANIFEST_VERIFIED_NOT_PAPER_MONITORING",
        "run_id":run_id,"expected_symbol_count":len(rows),
        "persisted_symbol_count":len(observed),
        "child_manifest_sha256":expected_sha,
        "batch_count":len(batches),
        "paper_authority":False,"trade_permission":False,
        "exchange_authority":False,"scientific_pass_permitted":False,
        "production_promotion_permitted":False,"order_path":"NONE",
    }
