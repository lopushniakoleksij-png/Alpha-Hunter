"""P0 source custody and first-entry baseline attestations — research-only.

No I/O. Neither a database link nor producer-asserted quote fields qualify as
independently authenticated provider evidence. This module never grants trading
or economic-profit authorization; it does not alter existing R8/R9/R10 records.
"""
from datetime import datetime, timezone
from math import isfinite


def _utc(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("missing UTC timestamp")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("naive timestamp")
    return dt.astimezone(timezone.utc)


def attest_previous_source(*, receipt, parent, children, expected_fingerprint,
                           expected_run_source="RENDER_CRON"):
    """Require exact DB custody. It is NOT independent quote authentication."""
    problems = []
    if not isinstance(receipt, dict) or not isinstance(parent, dict):
        return {"status": "REJECTED", "blockers": ("SOURCE_OR_RECEIPT_MISSING",),
                "independently_authenticated": False, "trade_permission": False}
    source_id = receipt.get("source_run_id")
    if not isinstance(source_id, str) or not source_id or source_id != parent.get("run_id"):
        problems.append("SOURCE_RUN_PARENT_MISMATCH")
    payload = parent.get("payload")
    ident = payload.get("validation_identity") if isinstance(payload, dict) else None
    if not isinstance(ident, dict):
        ident = {}
    if not isinstance(payload, dict) or payload.get("_canonical_publication_state") != "VERIFIED":
        problems.append("SOURCE_PARENT_NOT_VERIFIED")
    if ident.get("run_source") != expected_run_source or ident.get("runtime_role") != "RENDER_CRON":
        problems.append("SOURCE_RUNTIME_IDENTITY_UNVERIFIED")
    if not expected_fingerprint or ident.get("scientific_fingerprint_sha256") != expected_fingerprint:
        problems.append("SOURCE_SCIENTIFIC_FINGERPRINT_MISMATCH")
    sym = receipt.get("symbol")
    if (not isinstance(children, (list,tuple)) or not children
            or not isinstance(parent.get("symbol_count"),int)
            or len(children) != parent["symbol_count"]):
        problems.append("SOURCE_CHILD_CENSUS_INCOMPLETE")
    else:
        symbols = [c.get("symbol") for c in children if isinstance(c,dict)]
        if (len(symbols) != len(children) or len(set(symbols)) != len(symbols)
                or any(c.get("run_id") != source_id
                       or not isinstance(c.get("payload"),dict)
                       or c["payload"].get("symbol") != c["symbol"] for c in children)
                or sym not in symbols):
            problems.append("SOURCE_CHILD_IDENTITY_INVALID")
    if (receipt.get("paper_only") is not True
            or receipt.get("exchange_authority") is not False
            or receipt.get("trade_permission") is not False):
        problems.append("RECEIPT_PERMISSION_INVALID")
    try:
        collected = _utc(parent.get("collected_at_utc"))
        observed = _utc(receipt.get("observed_at_utc"))
        if (observed-collected).total_seconds() < 0 or (observed-collected).total_seconds() > 2100:
            problems.append("SOURCE_OBSERVATION_CLOCK_INVALID")
    except (ValueError, TypeError, OverflowError):
        problems.append("SOURCE_TIMESTAMP_MISSING")
    return {
        "status": "REJECTED" if problems else "DB_CUSTODY_LINKED_NOT_INDEPENDENTLY_AUTHENTICATED",
        "blockers": tuple(sorted(set(problems))),
        "independently_authenticated": False,
        "trade_permission": False,
    }


def assess_first_entry_baseline(*, position, entry_fills, entry_parent,
                                entry_children, first_observation,
                                expected_fingerprint):
    """Assess baseline candidate only; cannot authorize first-monitor skip.

    A historical fill record and two recorded protective legs are not external
    acknowledgement or delivery. Require human/source verification separately.
    """
    faults = []
    if not isinstance(position,dict) or not isinstance(first_observation,dict):
        faults.append("ENTRY_OR_FIRST_OBSERVATION_MISSING")
        return {"status":"REJECTED","blockers":tuple(faults),
                "monitoring_baseline_authorized":False,"trade_permission":False}
    source_id = position.get("entry_completed_source_run_id")
    receipt = {
        "source_run_id": source_id, "symbol": position.get("symbol"),
        "observed_at_utc": position.get("entry_completed_at_utc"),
        "paper_only": position.get("paper_only",True),
        "exchange_authority":False,"trade_permission":False,
    }
    proof = attest_previous_source(
        receipt=receipt, parent=entry_parent, children=entry_children,
        expected_fingerprint=expected_fingerprint)
    if proof["blockers"]:
        faults.extend(proof["blockers"])
    if (position.get("protection_count") != 2
            or not position.get("stop_protective_order_id")
            or not position.get("target_protective_order_id")
            or position.get("unresolved_protective_evidence") is not False
            or position.get("horizon_integrity_failed") is not False):
        faults.append("ENTRY_PROTECTIVE_ACKNOWLEDGEMENT_UNVERIFIED")
    if (not isinstance(entry_fills,(list,tuple)) or not entry_fills
            or any(not isinstance(fill,dict)
                   or fill.get("order_id") != position.get("entry_order_id")
                   or fill.get("source_run_id") != source_id
                   or not isinstance(fill.get("quantity"),(int,float))
                   or isinstance(fill.get("quantity"),bool)
                   or not isfinite(fill["quantity"])
                   or fill["quantity"] <= 0
                   or fill.get("paper_only") is not True
                   or fill.get("exchange_authority") is not False
                   for fill in entry_fills)):
        faults.append("ENTRY_FILL_CUSTODY_UNVERIFIED")
    try:
        entry_at = _utc(position["entry_completed_at_utc"])
        first_at = _utc(first_observation["observed_at_utc"])
        if not 0 <= (first_at - entry_at).total_seconds() <= 2100:
            faults.append("INITIAL_ENTRY_TO_MONITORING_GAP_INVALID")
    except (ValueError, TypeError, KeyError, OverflowError):
        faults.append("INITIAL_CLOCK_EVIDENCE_MISSING")
    if (first_observation.get("entry_order_id") != position.get("entry_order_id")
            or first_observation.get("symbol") != position.get("symbol")
            or first_observation.get("decision_id") != position.get("decision_id")):
        faults.append("FIRST_OBSERVATION_POSITION_IDENTITY_INVALID")
    if (first_observation.get("outcome") not in (
            "NO_TRIGGER", "STOP_TRIGGERED", "TARGET_TRIGGERED", "HORIZON_CLOSED")
            or first_observation.get("blockers") != []):
        faults.append("FIRST_OBSERVATION_AMBIGUOUS_OR_BLOCKED")
    if (first_observation.get("paper_only") is not True
            or first_observation.get("exchange_authority") is not False
            or first_observation.get("trade_permission") is not False
            or first_observation.get("order_path") != "NONE"):
        faults.append("FIRST_OBSERVATION_AUTHORITY_UNVERIFIED")
    if (not isinstance(first_observation.get("source_run_id"), str)
            or not first_observation.get("source_run_id")):
        faults.append("FIRST_OBSERVATION_SOURCE_UNVERIFIED")
    return {
        "status": "REJECTED" if faults else "CANDIDATE_NEEDS_INDEPENDENT_PROVIDER_AND_PROTECTION_ATTESTATION",
        "blockers": tuple(sorted(set(faults))),
        "monitoring_baseline_authorized": False,
        "trade_permission": False,
    }
