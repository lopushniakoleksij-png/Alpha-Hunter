"""Research-only, side-effect-free successor quote and paper-monitoring receipts.

DO NOT import from production R9/R10 scanner/management. No DB writes or
orders. Recorded best-level quotes do not guarantee a future executable exit.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

VERSION = "successor-quote-receipt-shadow-v0.1"


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo else None


def _positive(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return v if v.is_finite() and v > 0 else None


def _identifier(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _symbol(value: Any) -> str:
    return _identifier(value).upper()


def build_monitoring_receipts(
    parent: dict[str, Any],
    children: list[dict[str, Any]] | None,
    expected_positions: list[dict[str, Any]] | None,
    attempts: list[dict[str, Any]] | None,
    quotes: list[dict[str, Any]] | None,
    *,
    asof_inventory_complete: bool,
    maximum_quote_offset_seconds: Any,
    approved_quote_sources: set[str] | frozenset[str] | None,
) -> dict[str, Any]:
    """Classify one canonical run with an externally attested *as-of-run* inventory.

    Never substitute the current open-position view for a historic inventory.
    Missing or malformed evidence is UNKNOWN, not safe or scientific PASS.
    """
    run_id = _identifier(parent.get("run_id"))
    collected = _utc(parent.get("collected_at_utc"))
    identity = parent.get("validation_identity")
    identity = identity if isinstance(identity, dict) else {}
    fingerprint = _identifier(identity.get("scientific_fingerprint_sha256"))
    blockers: list[str] = []
    if (not run_id or collected is None or identity.get("run_source") != "RENDER_CRON"
            or identity.get("runtime_role") != "RENDER_CRON"
            or len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint)):
        blockers.append("CANONICAL_RUN_IDENTITY_INVALID")

    expected_children = parent.get("symbol_count")
    if type(expected_children) is not int or expected_children < 0:
        blockers.append("EXPECTED_CHILD_COUNT_INVALID")
    if any(type(source) is not list for source in (children, attempts, quotes, expected_positions)):
        blockers.append("INPUT_EVIDENCE_MISSING_OR_MALFORMED")
    if asof_inventory_complete is not True:
        blockers.append("ASOF_POSITION_INVENTORY_UNVERIFIED")
    if not isinstance(approved_quote_sources, (set, frozenset)) or not approved_quote_sources:
        blockers.append("APPROVED_QUOTE_SOURCES_MISSING")
    max_offset = _positive(maximum_quote_offset_seconds)
    if max_offset is None:
        blockers.append("QUOTE_TIMESTAMP_POLICY_INVALID")

    child_rows = children if isinstance(children, list) else []
    child_symbols: set[str] = set()
    for row in child_rows:
        if not isinstance(row, dict) or _identifier(row.get("run_id")) != run_id or not _symbol(row.get("symbol")):
            blockers.append("CHILD_IDENTITY_INVALID")
            continue
        sym = _symbol(row.get("symbol"))
        if sym in child_symbols:
            blockers.append("DUPLICATE_SYMBOL_CHILD")
        child_symbols.add(sym)
    if type(expected_children) is int and len(child_rows) != expected_children:
        blockers.append("SYMBOL_CHILD_COUNT_MISMATCH")

    by_group: dict[tuple[str, str], set[str]] = defaultdict(set)
    all_ids: set[str] = set()
    position_by_id: dict[str, tuple[str, str]] = {}
    for position in expected_positions if isinstance(expected_positions, list) else []:
        if not isinstance(position, dict):
            blockers.append("EXPECTED_POSITION_INVALID")
            continue
        oid = _identifier(position.get("entry_order_id"))
        sym = _symbol(position.get("symbol"))
        direction = _symbol(position.get("direction"))
        if not oid or not sym or direction not in {"LONG", "SHORT"}:
            blockers.append("EXPECTED_POSITION_INVALID")
            continue
        if oid in all_ids:
            blockers.append("DUPLICATE_EXPECTED_POSITION")
        all_ids.add(oid)
        position_by_id[oid] = (sym, direction)
        by_group[(sym, direction)].add(oid)

    attempt_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts if isinstance(attempts, list) else []:
        if not isinstance(attempt, dict) or _identifier(attempt.get("source_run_id")) != run_id:
            blockers.append("ATTEMPT_RUN_IDENTITY_INVALID")
            continue
        oid = _identifier(attempt.get("entry_order_id"))
        if not oid or oid not in all_ids:
            blockers.append("UNEXPECTED_OR_INVALID_ATTEMPT")
            continue
        if (_symbol(attempt.get("symbol")), _symbol(attempt.get("direction"))) != position_by_id[oid]:
            blockers.append("ATTEMPT_POSITION_IDENTITY_MISMATCH")
        attempt_map[oid].append(attempt)

    quote_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    expected_symbols = {symbol for symbol, direction in by_group}
    for quote in quotes if isinstance(quotes, list) else []:
        if not isinstance(quote, dict) or _identifier(quote.get("source_run_id")) != run_id:
            blockers.append("QUOTE_RUN_IDENTITY_INVALID")
            continue
        sym = _symbol(quote.get("symbol"))
        if not sym or sym not in expected_symbols:
            blockers.append("UNEXPECTED_OR_INVALID_QUOTE")
            continue
        quote_map[sym].append(quote)

    receipts: list[dict[str, Any]] = []
    for (sym, direction), order_ids in sorted(by_group.items()):
        failures: list[str] = []
        for oid in sorted(order_ids):
            count = len(attempt_map.get(oid, []))
            if count == 0:
                failures.append("EXIT_ATTEMPT_MISSING")
            elif count != 1:
                failures.append("EXIT_ATTEMPT_DUPLICATE")
            elif _identifier(attempt_map[oid][0].get("outcome")) in {"", "INPUT_MISSING", "AMBIGUOUS"}:
                failures.append("EXIT_ATTEMPT_OUTCOME_UNVERIFIED")

        candidates = quote_map.get(sym, [])
        quote = candidates[0] if len(candidates) == 1 else None
        captured_at = None
        source = None
        exit_book_quantity = None
        if not candidates:
            failures.append("QUOTE_CAPTURE_MISSING")
        elif len(candidates) > 1:
            failures.append("QUOTE_CAPTURE_DUPLICATE_OR_CONFLICT")
        else:
            source = _identifier(quote.get("source"))
            captured_at = _utc(quote.get("captured_at_utc"))
            bid = _positive(quote.get("bid_price"))
            ask = _positive(quote.get("ask_price"))
            bid_size = _positive(quote.get("bid_size"))
            ask_size = _positive(quote.get("ask_size"))
            if not source or source in {"MISSING", "UNKNOWN", "SOURCE_NOT_LABELED_IN_ATTEMPT"}:
                failures.append("QUOTE_SOURCE_UNLABELLED")
            elif not isinstance(approved_quote_sources, (set, frozenset)) or source not in approved_quote_sources:
                failures.append("QUOTE_SOURCE_NOT_APPROVED")
            if (bid is None or ask is None or bid_size is None or ask_size is None
                    or (bid is not None and ask is not None and ask < bid)):
                failures.append("QUOTE_BOOK_INVALID")
            else:
                exit_book_quantity = str(bid_size if direction == "LONG" else ask_size)
            if captured_at is None or collected is None or max_offset is None:
                failures.append("QUOTE_TIME_UNVERIFIED")
            elif abs(Decimal(str((captured_at - collected).total_seconds()))) > max_offset:
                failures.append("QUOTE_OUTSIDE_CAPTURE_WINDOW")
        if sym not in child_symbols:
            failures.append("SYMBOL_CHILD_MISSING")
        receipt_id = sha256(f"{VERSION}|{run_id}|{sym}|{direction}".encode("utf-8")).hexdigest()[:32]
        receipts.append({
            "receipt_id": receipt_id,
            "source_run_id": run_id,
            "symbol": sym,
            "direction": direction,
            "entry_order_ids": sorted(order_ids),
            "expected_position_count": len(order_ids),
            "attempt_count": sum(len(attempt_map.get(i, [])) for i in order_ids),
            "receipt_status": "OBSERVED" if not failures else "MISSING_OR_CONFLICTING_EVIDENCE",
            "blockers": sorted(set(failures)),
            "quote_source": source,
            "quote_captured_at_utc": captured_at.isoformat() if captured_at else None,
            "exit_side": "SELL" if direction == "LONG" else "BUY",
            "observed_exit_top_book_quantity": exit_book_quantity,
            "future_exit_guaranteed": False,
            "scientific_pass_permitted": False,
        })

    if blockers or any(item["blockers"] for item in receipts):
        status = "UNKNOWN_OR_INCOMPLETE"
    elif not by_group:
        status = "NO_POSITIONS_CONFIRMED_ASOF_RUN"
    else:
        status = "RECEIPTS_OBSERVED_NOT_EXECUTION_PROOF"
    return {
        "model_version": VERSION,
        "source_run_id": run_id,
        "run_status": status,
        "run_blockers": sorted(set(blockers)),
        "expected_symbol_children": expected_children,
        "observed_symbol_children": len(child_rows),
        "expected_position_count": len(all_ids),
        "receipt_count": len(receipts),
        "receipts": receipts,
        "shadow_only": True,
        "paper_only": True,
        "paper_authority": False,
        "trade_permission": False,
        "exchange_authority": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }
