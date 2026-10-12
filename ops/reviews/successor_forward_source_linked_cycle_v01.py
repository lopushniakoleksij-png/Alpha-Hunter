"""Research-only bridge: ALL residual fill source rows -> per-position monitor receipts.

Does not claim that caller's source transaction really existed. A real successor
must capture immutable fill/exit watermarks in a trustworthy external writer.
Never replace historic R10 evidence, edit paper ledgers or issue exchange orders.
"""
from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from json import dumps
from pathlib import Path
from typing import Any


def _load(filename: str, modname: str):
    spec=spec_from_file_location(modname,Path(__file__).with_name(filename))
    mod=module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inventory_lib=_load("successor_forward_asof_inventory_v01.py","forward_source_inventory_shadow_v01")
receipt_lib=_load("successor_quote_receipts_v01.py","paper_receipts_shadow_v01")


def evaluate_source_linked_cycle(
    parent: dict[str, Any],
    symbol_children: list[dict[str, Any]] | None,
    orders: list[dict[str, Any]] | None,
    entry_fills: list[dict[str, Any]] | None,
    exit_fills: list[dict[str, Any]] | None,
    consistent_capture_receipts: dict[str, dict[str, Any]] | None,
    exit_attempts: list[dict[str, Any]] | None,
    quotes: list[dict[str, Any]] | None,
    *,
    max_capture_lag_seconds: int,
    maximum_quote_offset_seconds: int,
    approved_quote_sources: set[str],
) -> dict:
    asof=parent.get("collected_at_utc")
    source=inventory_lib.build_forward_asof_inventory(
        orders,entry_fills,exit_fills,consistent_capture_receipts,
        asof_utc=asof,max_source_capture_lag_seconds=max_capture_lag_seconds
    )
    blockers=list(source["blockers"])
    if source["status"]!="SUPPLIED_SOURCE_ROWS_RECONCILED_NOT_INDEPENDENT_ATTESTATION":
        blockers.append("ALL_COHORT_FILL_EXIT_SOURCE_INCOMPLETE")
    if not source["external_snapshot_token"]:
        blockers.append("CONSISTENT_ASOF_SOURCE_CAPTURE_MISSING")
    manifest_sha=source.get("manifest_sha256")
    if manifest_sha:
        canonical=dumps(source["positions"],sort_keys=True,separators=(",",":")).encode()
        if sha256(canonical).hexdigest()!=manifest_sha:
            blockers.append("RESIDUAL_MANIFEST_HASH_CONFLICT")
    else:
        blockers.append("RESIDUAL_MANIFEST_MISSING")

    # Do NOT allow an incomplete source capture to be 'repaired' by passing
    # fewer/currently-managed positions to the generic structural scorer.
    if blockers:
        return {
            "run_status":"SOURCE_RESIDUAL_INVENTORY_UNKNOWN_OR_INCOMPLETE",
            "blockers":sorted(set(blockers)),
            "source_manifest_sha256":manifest_sha,
            "expected_positions":None,
            "shadow_only":True,
            "trade_permission":False,
            "exchange_authority":False,
            "production_promotion_permitted":False,
            "scientific_pass_permitted":False,
            "order_path":"NONE",
        }

    positions=[{"entry_order_id":p["entry_order_id"],
                "symbol":p["symbol"],"direction":p["direction"]}
               for p in source["positions"]]
    report=receipt_lib.build_monitoring_receipts(
        parent,symbol_children,positions,exit_attempts,quotes,
        asof_inventory_complete=True,
        maximum_quote_offset_seconds=maximum_quote_offset_seconds,
        approved_quote_sources=approved_quote_sources
    )
    report["source_manifest_sha256"]=manifest_sha
    report["source_snapshot_token"]=source["external_snapshot_token"]
    report["source_residual_position_count"]=len(positions)
    report["source_caveat"]="SUPPLIED_CONSISTENT_ROWS_ONLY_NOT_INDEPENDENT_SOURCE_AUTHENTICITY"
    report["scientific_pass_permitted"]=False
    report["production_promotion_permitted"]=False
    report["exchange_authority"]=False
    report["trade_permission"]=False
    report["order_path"]="NONE"
    return report
