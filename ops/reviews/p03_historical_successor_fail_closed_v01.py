"""Successor-only immutable history acceptance gate — OFFLINE, no credentials.

Never scans, writes, deploys, repairs histories, grants trading permission, or
calls production. The caller must independently establish that the captured
input covers the required historical interval; assertions alone are not proof
of source authenticity. This is an additional acceptance contract for a
future separately authorised successor, not the existing producer.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import isfinite
from re import fullmatch

SAFE_OUTCOMES = frozenset({
    "NO_TRIGGER", "STOP_TRIGGERED", "TARGET_TRIGGERED", "HORIZON_CLOSED",
})
FROZEN_LIMIT_SECONDS = 35 * 60
REQUIRED_SOURCE = "RENDER_CRON"


def _utc(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("non-time timestamp")
    if result.utcoffset() is None:
        raise ValueError("timezone missing")
    return result.astimezone(timezone.utc)


def _identifier(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _utc_or_fault(value, faults, label):
    try:
        return _utc(value)
    except (ValueError, TypeError, OverflowError):
        faults.add(label)
        return None


def evaluate_history(*, parents, children, receipts, positions,
                     required_run_ids, coverage_attested, origin_attestations,
                     max_gap_minutes=35):
    """Inspect *all supplied* immutable records; return fail-closed decision.

    A required-run manifest and coverage attestation are mandatory inputs; a
    true flag is not independent verification of the manifest or market source.
    Parent expected_symbols must be from a separately preserved scan input.
    A newer receipt cannot cancel a prior gap, ambiguous first observation,
    or incomplete parent. Results never alter or reclassify those records.
    """
    faults = set()
    if (not isinstance(max_gap_minutes, (int, float))
            or isinstance(max_gap_minutes, bool)
            or not isfinite(max_gap_minutes) or max_gap_minutes != 35):
        faults.add("FROZEN_35M_RULE_CHANGED")
    if coverage_attested is not True:
        faults.add("INDEPENDENT_HISTORY_COVERAGE_NOT_ATTESTED")
    if (not isinstance(parents, (list, tuple)) or not parents
            or not isinstance(children, (list, tuple))
            or not isinstance(receipts, (list, tuple))
            or not isinstance(positions, (list, tuple))
            or not isinstance(required_run_ids, (list, tuple))
            or not isinstance(origin_attestations, dict)):
        return _verdict(faults | {"HISTORY_DATASET_MISSING"}, 0, 0)

    parent_by_id, parent_times, child_by_run = {}, {}, defaultdict(list)
    for parent in parents:
        if not isinstance(parent, dict) or not _identifier(parent.get("run_id")):
            faults.add("INVALID_PARENT_ROW")
            continue
        rid = parent["run_id"]
        if rid in parent_by_id:
            faults.add("DUPLICATE_PARENT_RUN_ID")
            continue
        parent_by_id[rid] = parent
        parent_times[rid] = _utc_or_fault(
            parent.get("collected_at_utc"), faults, "INVALID_PARENT_TIMESTAMP")
        if parent.get("run_source") != REQUIRED_SOURCE:
            faults.add("UNTRUSTED_PARENT_SOURCE")
        if parent.get("publication_state") != "VERIFIED":
            faults.add("HISTORICAL_PARENT_UNVERIFIED")
        count = parent.get("symbol_count")
        errors = parent.get("error_count")
        if (not isinstance(count, int) or isinstance(count, bool) or count <= 0
                or not isinstance(errors, int) or isinstance(errors, bool)
                or not 0 <= errors <= count):
            faults.add("INVALID_PARENT_COUNTS")

    if (not required_run_ids or any(not _identifier(x) for x in required_run_ids)
            or len(set(required_run_ids)) != len(required_run_ids)
            or set(required_run_ids) != set(parent_by_id)):
        faults.add("REQUIRED_RUN_MANIFEST_MISMATCH")

    for child in children:
        if not isinstance(child, dict) or not _identifier(child.get("run_id")):
            faults.add("INVALID_CHILD_ROW")
            continue
        child_by_run[child["run_id"]].append(child)
    if set(child_by_run) - set(parent_by_id):
        faults.add("ORPHAN_CHILD_RUN")

    for rid, parent in parent_by_id.items():
        expected = parent.get("expected_symbols")
        rows = child_by_run.get(rid, [])
        if (not isinstance(expected, (list, tuple)) or not expected
                or any(not _identifier(s) for s in expected)
                or len(set(expected)) != len(expected)
                or len(expected) != parent.get("symbol_count")):
            faults.add("EXPECTED_SYMBOL_MANIFEST_INVALID")
            continue
        persisted = []
        for child in rows:
            if (child.get("run_id") != rid
                    or not _identifier(child.get("symbol"))
                    or not isinstance(child.get("payload"), dict)
                    or child["payload"].get("symbol") != child.get("symbol")):
                faults.add("CHILD_PAYLOAD_IDENTITY_MISMATCH")
            persisted.append(child.get("symbol"))
        if (len(rows) != len(expected) or len(set(persisted)) != len(rows)
                or set(persisted) != set(expected)):
            faults.add("HISTORICAL_CHILDREN_INCOMPLETE")

    position_by_id, entry_times = {}, {}
    for position in positions:
        if not isinstance(position, dict) or not _identifier(position.get("entry_order_id")):
            faults.add("INVALID_POSITION_INVENTORY")
            continue
        eid = position["entry_order_id"]
        if eid in position_by_id:
            faults.add("DUPLICATE_POSITION_ID")
            continue
        position_by_id[eid] = position
        if any(not _identifier(position.get(k))
               for k in ("decision_id", "symbol", "direction")):
            faults.add("INVALID_POSITION_IDENTITY")
        entry_times[eid] = _utc_or_fault(
            position.get("entry_completed_at_utc"), faults, "ENTRY_TIME_INVALID")
        attestation = origin_attestations.get(eid)
        if (not isinstance(attestation, dict)
                or attestation.get("accepted") is not True
                or not isinstance(attestation.get("artifact_sha256"), str)
                or not fullmatch(r"[0-9a-f]{64}", attestation["artifact_sha256"])):
            faults.add("FIRST_ENTRY_ORIGIN_NOT_ATTESTED")
    if set(origin_attestations) != set(position_by_id):
        faults.add("ORIGIN_MANIFEST_MISMATCH")

    by_position, seen_pair = defaultdict(list), set()
    for receipt in receipts:
        if not isinstance(receipt, dict):
            faults.add("INVALID_RECEIPT")
            continue
        eid, rid = receipt.get("entry_order_id"), receipt.get("source_run_id")
        if not _identifier(eid) or not _identifier(rid):
            faults.add("INVALID_RECEIPT_IDENTITY")
            continue
        if (eid, rid) in seen_pair:
            faults.add("DUPLICATE_RECEIPT_FOR_RUN")
        seen_pair.add((eid, rid))
        if eid not in position_by_id or rid not in parent_by_id:
            faults.add("ORPHAN_RECEIPT")
            continue
        position = position_by_id[eid]
        if any(receipt.get(k) != position.get(k)
               for k in ("decision_id", "symbol", "direction")):
            faults.add("RECEIPT_POSITION_IDENTITY_MISMATCH")
        if receipt.get("outcome") not in SAFE_OUTCOMES or receipt.get("blockers") != []:
            faults.add("UNUSABLE_HISTORICAL_RECEIPT")
        if (receipt.get("paper_only") is not True
                or receipt.get("exchange_authority") is not False
                or receipt.get("trade_permission") is not False
                or receipt.get("order_path") != "NONE"):
            faults.add("HISTORICAL_AUTHORITY_INVALID")
        observed = _utc_or_fault(
            receipt.get("observed_at_utc"), faults, "RECEIPT_TIME_INVALID")
        scan_time = parent_times.get(rid)
        entry_time = entry_times.get(eid)
        if observed is not None and scan_time is not None:
            if not 0 <= (observed - scan_time).total_seconds() <= FROZEN_LIMIT_SECONDS:
                faults.add("RECEIPT_OUTSIDE_SCAN_WINDOW")
        if observed is not None and entry_time is not None and observed <= entry_time:
            faults.add("AMBIGUOUS_FIRST_ENTRY_ORDERING")
        if observed is not None:
            by_position[eid].append(observed)

    for eid, entry_time in entry_times.items():
        expected_run_ids = {
            rid for rid, scan_time in parent_times.items()
            if scan_time is not None and entry_time is not None and scan_time >= entry_time
        }
        actual_run_ids = {rid for pid, rid in seen_pair if pid == eid}
        if expected_run_ids != actual_run_ids:
            faults.add("HISTORICAL_POSITION_RECEIPT_COVERAGE_FAILED")
        observations = sorted(by_position.get(eid, []))
        if not observations:
            faults.add("HISTORICAL_POSITION_RECEIPTS_MISSING")
            continue
        if entry_time is not None:
            if not 0 < (observations[0] - entry_time).total_seconds() <= FROZEN_LIMIT_SECONDS:
                faults.add("FIRST_ENTRY_BASELINE_GAP_OR_AMBIGUITY")
        for earlier, later in zip(observations, observations[1:]):
            seconds = (later - earlier).total_seconds()
            if not 0 < seconds <= FROZEN_LIMIT_SECONDS:
                faults.add("HISTORICAL_MONITORING_GAP_OVER_35M")
    return _verdict(faults, len(parent_by_id), len(position_by_id))


def _verdict(faults, scan_count, position_count):
    return {
        "successor_historical_evidence_pass": not faults,
        "blockers": tuple(sorted(faults)),
        "scans_checked": scan_count,
        "positions_checked": position_count,
        "original_records_unchanged": True,
        "production_release_authorized": False,
        "trade_permission": False,
        "exchange_authority": False,
        "paper_only": True,
    }
