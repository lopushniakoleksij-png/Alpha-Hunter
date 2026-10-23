"""Successor-only forward AS-OF paper-residual inventory. PURE, NO DB WRITES.

Inputs must be captured from authoritative orders / entry-fills / exit-fills
within ONE independent repeatable-read, read-only transaction. This scorer
cannot independently attest data completeness or cryptographic authenticity:
the caller-supplied source capture receipts are assumptions, NOT proven here.
Never reconstruct historical monitoring eligibility using today's active view.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from json import dumps
from typing import Any

VERSION = "successor-forward-asof-inventory-shadow-v0.1"
TABLES = ("alpha_hunter_paper_orders_v02", "alpha_hunter_paper_fills_v02",
          "alpha_hunter_paper_exit_fills_v04")
EPSILON = Decimal("0.000000000001")


def dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except ValueError:
        return None


def decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        v = Decimal(str(value))
        return v if v.is_finite() and v > 0 else None
    except (TypeError, ValueError, InvalidOperation):
        return None


def identifier(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _permission_safe(r: dict) -> bool:
    return (r.get("paper_only") is True and r.get("exchange_authority") is False
            and r.get("trade_permission") is False and r.get("order_path") == "NONE")


def _attestation(captures: Any, *, observed: datetime, max_lag: int) -> list[str]:
    b: list[str] = []
    if not isinstance(captures, dict) or set(captures) != set(TABLES):
        return ["SOURCE_CAPTURE_SET_MISSING"]
    txid = set()
    for table in TABLES:
        item = captures[table]
        if not isinstance(item, dict):
            b.append("SOURCE_CAPTURE_INVALID")
            continue
        if item.get("source_table") != table or item.get("complete") is not True:
            b.append("SOURCE_CAPTURE_INCOMPLETE")
        key = identifier(item.get("consistent_snapshot_id"))
        if not key:
            b.append("CONSISTENT_SOURCE_SNAPSHOT_NOT_ATTESTED")
        txid.add(key)
        stamp = dt(item.get("captured_at_utc"))
        if stamp is None or not (observed <= stamp <= observed +
                                 __import__("datetime").timedelta(seconds=max_lag)):
            b.append("SOURCE_CAPTURE_TIME_NOT_PROSPECTIVE")
    if len(txid) != 1:
        b.append("SOURCE_TABLES_NOT_ONE_CONSISTENT_READ")
    return b


def build_forward_asof_inventory(
    orders: list[dict[str, Any]] | None,
    entry_fills: list[dict[str, Any]] | None,
    exit_fills: list[dict[str, Any]] | None,
    capture_receipts: dict[str, dict[str, Any]] | None,
    *,
    asof_utc: str,
    max_source_capture_lag_seconds: int,
) -> dict[str, Any]:
    """Forward-only, ALL cohorts, with explicit external source capture contracts.

    Result never authorizes an order/scientific result. A complete result only
    demonstrates local consistency of the SUPPLIED records and receipt metadata.
    An independent source-level watermark/ledger snapshot still must be audited.
    """
    blockers: list[str] = []
    asof = dt(asof_utc)
    if asof is None:
        blockers.append("ASOF_UTC_INVALID")
    if type(max_source_capture_lag_seconds) is not int or max_source_capture_lag_seconds <= 0:
        blockers.append("SOURCE_CAPTURE_POLICY_INVALID")
    source_lists = (orders, entry_fills, exit_fills)
    if any(not isinstance(v, list) for v in source_lists):
        blockers.append("SOURCE_LEDGER_RECORDS_MISSING")
    if asof is not None and type(max_source_capture_lag_seconds) is int and max_source_capture_lag_seconds > 0:
        blockers += _attestation(capture_receipts, observed=asof,
                                max_lag=max_source_capture_lag_seconds)
    if blockers:
        return _result(asof_utc, [], blockers, None)

    original_orders: dict[str, dict] = {}
    for row in orders:
        if not isinstance(row, dict):
            blockers.append("ORDER_RECORD_MALFORMED")
            continue
        oid = identifier(row.get("order_id"))
        created = dt(row.get("created_at"))
        submitted = dt(row.get("submitted_at_utc"))
        if (not oid or not created or not submitted or created > asof or submitted > asof
                or not _permission_safe(row)
                or identifier(row.get("symbol")) != identifier(row.get("symbol")).upper()
                or identifier(row.get("direction")) not in {"LONG", "SHORT"}):
            blockers.append("ORDER_ID_TIME_AUTHORITY_INVALID")
            continue
        if oid in original_orders:
            blockers.append("DUPLICATE_ORDER_ID")
        original_orders[oid] = row

    def accumulate(rows: list[dict], *, exit_side: bool):
        quantities: dict[str, Decimal] = {}
        ids: dict[str, list[str]] = {}
        seen_ids: set[str] = set()
        latest_entry: dict[str, datetime] = {}
        for row in rows:
            if not isinstance(row, dict):
                blockers.append("FILL_RECORD_MALFORMED")
                continue
            record_id = identifier(row.get("exit_fill_id" if exit_side else "fill_id"))
            oid = identifier(row.get("entry_order_id" if exit_side else "order_id"))
            stamp = dt(row.get("filled_at_utc"))
            created = dt(row.get("created_at"))
            q = decimal(row.get("quantity"))
            if not stamp or not created or not record_id or not oid or not q:
                blockers.append("FILL_ID_QUANTITY_TIME_INVALID")
                continue
            if stamp > asof:
                # Future fills are irrelevant AS OF the exact decision time.
                continue
            if created > asof or created < stamp or not _permission_safe(row):
                blockers.append("LATE_OR_UNSAFE_FILL_EVIDENCE")
                continue
            if not identifier(row.get("source_run_id")):
                blockers.append("FILL_SOURCE_RUN_ID_MISSING")
            if record_id in seen_ids:
                blockers.append("DUPLICATE_FILL_ID")
            seen_ids.add(record_id)
            parent = original_orders.get(oid)
            if parent is None:
                blockers.append("ORPHAN_FILL_ORDER")
                continue
            if stamp < dt(parent.get("submitted_at_utc")):
                blockers.append("FILL_BEFORE_ORDER")
            if exit_side:
                if (identifier(row.get("symbol")) != identifier(parent.get("symbol"))
                    or identifier(row.get("direction")) != identifier(parent.get("direction"))):
                    blockers.append("EXIT_POSITION_IDENTITY_MISMATCH")
            quantities[oid] = quantities.get(oid, Decimal(0)) + q
            ids.setdefault(oid, []).append(record_id)
            if not exit_side:
                latest_entry[oid] = max(latest_entry.get(oid, stamp), stamp)
        return quantities, ids, latest_entry

    in_qty, entry_ids, most_recent_fill = accumulate(entry_fills, exit_side=False)
    out_qty, exit_ids, _ = accumulate(exit_fills, exit_side=True)
    for oid in out_qty:
        if out_qty[oid] > in_qty.get(oid, Decimal(0)) + EPSILON:
            blockers.append("OVER_EXIT_OR_ORPHAN_RESIDUAL")
    result: list[dict[str, Any]] = []
    for oid in sorted(in_qty):
        remain = in_qty[oid] - out_qty.get(oid, Decimal(0))
        if remain <= EPSILON:
            continue
        order = original_orders.get(oid)
        if not order:
            blockers.append("FILL_ORDER_INVENTORY_INCOMPLETE")
            continue
        # Last actual fill is only the initial monitoring reference, not a
        # substitute for evidence of continuity after the position was opened.
        result.append({
            "entry_order_id": oid,
            "symbol": identifier(order.get("symbol")),
            "direction": identifier(order.get("direction")),
            "filled_qty": str(in_qty[oid]),
            "exited_qty": str(out_qty.get(oid, Decimal(0))),
            "residual_qty": str(remain),
            "entry_fill_ids": sorted(entry_ids.get(oid, [])),
            "exit_fill_ids": sorted(exit_ids.get(oid, [])),
            "latest_entry_fill_at_utc": most_recent_fill[oid].isoformat(),
            "paper_only": True, "exchange_authority": False, "trade_permission": False,
        })
    digest = sha256(dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    snapshot_token = capture_receipts[TABLES[0]]["consistent_snapshot_id"]
    return _result(asof_utc, result, sorted(set(blockers)), digest, snapshot_token)


def _result(asof_utc, positions, blockers, digest, snapshot_token=None):
    return {
        "version": VERSION,
        "asof_utc": asof_utc,
        "status": "SOURCE_EVIDENCE_UNKNOWN_OR_INVALID" if blockers else
                  "SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION",
        "blockers": sorted(set(blockers)),
        "positions": positions,
        "expected_position_count": len(positions),
        "manifest_sha256": digest,
        "external_snapshot_token": snapshot_token,
        "caveat": "NO INDEPENDENT SOURCE COMPLETENESS OR AUTHENTICITY PROOF",
        "shadow_only": True,
        "production_promotion_permitted": False,
        "trade_permission": False, "exchange_authority": False, "order_path": "NONE",
        "scientific_pass_permitted": False,
    }
