"""Isolated forward-only custody verifier for a NEW successor research cohort.

A signed future schedule and a separately signed ordered observation chain
MUST originate from separately held keys. Self-signed fixtures only prove the
test contract; signatures alone do NOT prove quote-provider authenticity.
No producer, database, scanner, networking, file modification or order imports.
Never rehabilitate or rewrite the frozen R8/R9/R10 historical archive.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from re import fullmatch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

LEGACY_FROZEN_CENSUS_HEAD = "5b3a6f424e88ff65fa4d0ca235d91e5e25921acb"
LEGACY_ACCEPTANCE = "EVIDENCE_NO_GO"
CUTOFF = datetime.fromisoformat("2026-11-03T10:39:08.112514+00:00")
MAX_SECONDS = 35 * 60
ID = r"[A-Za-z0-9_-]{1,100}"


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      allow_nan=False, separators=(",", ":")).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def utc(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be str")
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.utcoffset() is None:
        raise ValueError("timezone required")
    return date.astimezone(timezone.utc)


def verify_detached(public_hex, signature_b64, object_value):
    try:
        public = bytes.fromhex(public_hex)
        signed = base64.b64decode(signature_b64, validate=True)
        if len(public) != 32 or len(signed) != 64:
            return False
        Ed25519PublicKey.from_public_bytes(public).verify(
            signed, canonical(object_value))
        return True
    except (ValueError, TypeError, InvalidSignature, OverflowError):
        return False


def verdict(faults, count):
    faults = tuple(sorted(set(faults)))
    return {
        "status": "ISOLATED_PROSPECTIVE_CONTRACT_PASS_ONLY"
                  if not faults else "PROSPECTIVE_EVIDENCE_NO_GO",
        "prospective_chain_shape_valid": not faults,
        "blockers": faults,
        "future_runs_checked": count,
        "historical_legacy_reclassified": False,
        "legacy_evidence_acceptance": LEGACY_ACCEPTANCE,
        "provider_quotes_independently_authenticated": False,
        "independent_human_approval": False,
        "paper_only": True,
        "trade_permission": False,
        "exchange_authority": False,
        "production_release_authorized": False,
    }


def validate_forward_history(*, schedule, schedule_signature_b64,
                             trusted_schedule_public_hex,
                             event_envelopes, trusted_event_public_hex):
    """Reject missing or altered independent run schedules and observations.

    Schedule and event signatures must use DIFFERENT pinned public keys.
    A valid synthetic path is contract-only, not provider or production proof.
    """
    faults = []
    if (not isinstance(schedule, dict)
            or not isinstance(event_envelopes, (list, tuple))
            or not isinstance(trusted_schedule_public_hex, str)
            or not isinstance(trusted_event_public_hex, str)
            or trusted_schedule_public_hex == trusted_event_public_hex):
        return verdict(["INDEPENDENT_WITNESS_KEYS_OR_DATA_MISSING"], 0)
    if not verify_detached(trusted_schedule_public_hex,
                           schedule_signature_b64, schedule):
        faults.append("SCHEDULE_SIGNATURE_INVALID")
    if schedule.get("legacy_census_head") != LEGACY_FROZEN_CENSUS_HEAD:
        faults.append("LEGACY_CENSUS_PIN_MISMATCH")
    if schedule.get("legacy_acceptance") != LEGACY_ACCEPTANCE:
        faults.append("LEGACY_HISTORICAL_OUTCOME_REWRITE_ATTEMPT")
    cohort_id = schedule.get("cohort_id")
    if (not isinstance(cohort_id, str)
            or not fullmatch(r"R11-[A-Za-z0-9_-]{1,60}", cohort_id)):
        faults.append("NEW_SUCCESSOR_COHORT_ID_MISSING")
    try:
        genesis_at = utc(schedule.get("genesis_utc"))
        if genesis_at <= CUTOFF:
            faults.append("GENESIS_NOT_AFTER_FROZEN_ARCHIVE")
    except (ValueError, TypeError):
        genesis_at = None
        faults.append("GENESIS_TIMESTAMP_INVALID")
    expected = schedule.get("expected_runs")
    if (not isinstance(expected, list) or not expected or len(expected) > 250
            or len(event_envelopes) > 250):
        return verdict(faults + ["PROSPECTIVE_SCHEDULE_INCOMPLETE"], 0)
    expected_ids, expected_times, expected_sym = [], {}, {}
    for run in expected:
        if not isinstance(run, dict):
            faults.append("SCHEDULE_RUN_INVALID")
            continue
        rid, symbols = run.get("run_id"), run.get("expected_symbols")
        if not isinstance(rid, str) or not fullmatch(ID, rid):
            faults.append("SCHEDULE_RUN_ID_INVALID")
            continue
        expected_ids.append(rid)
        try:
            at = utc(run.get("scheduled_utc"))
            expected_times[rid] = at
            if genesis_at is None or at < genesis_at:
                faults.append("SCHEDULE_RUN_PRE_GENESIS")
        except (ValueError, TypeError):
            faults.append("SCHEDULE_TIME_INVALID")
        if (not isinstance(symbols, list) or not symbols
                or any(not isinstance(s, str) or not s for s in symbols)
                or len(set(symbols)) != len(symbols)):
            faults.append("SCHEDULE_EXPECTED_SYMBOLS_INVALID")
        else:
            expected_sym[rid] = set(symbols)
    if len(set(expected_ids)) != len(expected_ids):
        faults.append("SCHEDULE_DUPLICATE_RUN")
    if len(expected_ids) != len(expected):
        faults.append("SCHEDULE_ENTRY_INVALID")
    # No gaps in the independent signed plan itself.
    scheduled_times = sorted(expected_times.values())
    for previous, current in zip(scheduled_times, scheduled_times[1:]):
        if not 0 < (current - previous).total_seconds() <= MAX_SECONDS:
            faults.append("SCHEDULE_CADENCE_GAP_OVER_35M")
    if len(expected) != len(event_envelopes):
        faults.append("OBSERVATION_RUN_COUNT_MISMATCH")
    incoming_ids = []
    earlier_chain = "GENESIS"
    receipt_history = {}
    for index, envelope in enumerate(event_envelopes):
        if not isinstance(envelope, dict):
            faults.append("OBSERVATION_ENVELOPE_INVALID")
            continue
        event, sig = envelope.get("event"), envelope.get("signature_b64")
        if not isinstance(event, dict):
            faults.append("OBSERVATION_EVENT_INVALID")
            continue
        if not verify_detached(trusted_event_public_hex, sig, event):
            faults.append("OBSERVATION_SIGNATURE_INVALID")
        rid = event.get("run_id")
        incoming_ids.append(rid)
        if event.get("cohort_id") != cohort_id:
            faults.append("COHORT_CONTAMINATION_OR_REPLAY")
        if event.get("previous_event_sha256") != earlier_chain:
            faults.append("OBSERVATION_CHAIN_BROKEN")
        earlier_chain = digest(event)
        if index < len(expected_ids) and rid != expected_ids[index]:
            faults.append("SIGNED_SCHEDULE_ORDER_MISMATCH")
        if rid not in expected_times or rid not in expected_sym:
            faults.append("UNSCHEDULED_OR_UNVERIFIED_RUN")
            continue
        try:
            observed_at = utc(event.get("observed_at_utc"))
            scan_at = expected_times[rid]
            if not 0 <= (observed_at - scan_at).total_seconds() <= MAX_SECONDS:
                faults.append("OBSERVATION_OUTSIDE_SCHEDULE_WINDOW")
        except (TypeError, ValueError):
            faults.append("OBSERVATION_TIMESTAMP_INVALID")
        children = event.get("persisted_children")
        if (not isinstance(children, list)
                or len(children) != len(expected_sym[rid])
                or any(not isinstance(c, dict) or
                       c.get("run_id") != rid or
                       c.get("symbol") not in expected_sym[rid] or
                       not isinstance(c.get("payload"), dict) or
                       c["payload"].get("symbol") != c.get("symbol")
                       for c in children)
                or {c["symbol"] for c in children if isinstance(c, dict)}
                        != expected_sym[rid]):
            faults.append("PROSPECTIVE_CHILD_CENSUS_INCOMPLETE")
        receipts = event.get("position_receipts")
        if not isinstance(receipts, list):
            faults.append("PROSPECTIVE_RECEIPTS_MISSING")
            continue
        seen = set()
        for receipt in receipts:
            if not isinstance(receipt, dict):
                faults.append("PROSPECTIVE_RECEIPT_INVALID")
                continue
            pid = receipt.get("entry_order_id")
            if not isinstance(pid, str) or not pid or pid in seen:
                faults.append("PROSPECTIVE_RECEIPT_DUPLICATE_OR_MISSING")
                continue
            seen.add(pid)
            if (receipt.get("source_run_id") != rid
                    or receipt.get("outcome") not in {
                        "NO_TRIGGER", "STOP_TRIGGERED",
                        "TARGET_TRIGGERED", "HORIZON_CLOSED",
                    }
                    or receipt.get("blockers") != []
                    or receipt.get("paper_only") is not True
                    or receipt.get("trade_permission") is not False
                    or receipt.get("exchange_authority") is not False
                    or receipt.get("order_path") != "NONE"):
                faults.append("PROSPECTIVE_RECEIPT_UNUSABLE")
            try:
                t = utc(receipt.get("observed_at_utc"))
                if not 0 <= (t - expected_times[rid]).total_seconds() <= MAX_SECONDS:
                    faults.append("PROSPECTIVE_RECEIPT_OUTSIDE_WINDOW")
                if pid in receipt_history:
                    gap = (t - receipt_history[pid]).total_seconds()
                    if not 0 < gap <= MAX_SECONDS:
                        faults.append("PROSPECTIVE_POSITION_GAP_OVER_35M")
                receipt_history[pid] = t
            except (ValueError, TypeError):
                faults.append("PROSPECTIVE_RECEIPT_TIME_INVALID")
    if incoming_ids != expected_ids:
        faults.append("SIGNED_SCHEDULE_RUNS_NOT_FULLY_OBSERVED")
    return verdict(faults, len(incoming_ids))
