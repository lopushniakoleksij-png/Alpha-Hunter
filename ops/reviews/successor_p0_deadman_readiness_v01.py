"""Offline successor-only deadman/position-coverage readiness gate.

Inputs are caller-supplied read-only diagnostic rows, not independently
authenticated source/custody evidence. No network, DB connection, timers,
background worker, dispatch, trading operations or scientific promotion.
The frozen 35-minute deadline is never extended by another successful scan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256

FROZEN_MAX_SECONDS = Decimal("2100")


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        time = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return time.astimezone(timezone.utc) if time.utcoffset() is not None else None


def _nonnegative(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    return number if number.is_finite() and number >= 0 else None


def _count(value):
    number = _nonnegative(value)
    return int(number) if number is not None and number == number.to_integral_value() else None


def evaluate_deadman_readiness(*, ledger, position_rows, checked_at_utc):
    """Return redacted alert CANDIDATES, never evidence of delivered alerts.

    Identity is deliberately limited to symbol/direction/ordinal; this cannot
    bind an authenticated source order without a separate signed as-of manifest.
    A supplied 'all clear' or missing inventory is never treated as proof.
    """
    blockers = set()
    incidents = []
    now = _utc(checked_at_utc)
    if now is None:
        blockers.add("CHECK_CLOCK_UNKNOWN")
    if not isinstance(ledger, dict) or not isinstance(position_rows, list):
        blockers.add("SOURCE_COUNTS_OR_POSITIONS_UNAVAILABLE")
        ledger = ledger if isinstance(ledger, dict) else {}
        position_rows = position_rows if isinstance(position_rows, list) else []

    total = _count(ledger.get("all_cohort_residual_count"))
    managed = _count(ledger.get("managed_from_fill_ledger"))
    quarantined = _count(ledger.get("quarantined_outside_managed"))
    unprotected = _count(ledger.get("unexplained_unmanaged"))
    legs_missing = _count(ledger.get("missing_recorded_stop_or_target"))
    if None in (total, managed, quarantined, unprotected, legs_missing):
        blockers.add("ALL_COHORT_LEDGER_COUNTS_UNKNOWN")
    elif (total != managed + quarantined + unprotected or
          len(position_rows) != managed):
        blockers.add("LEDGER_MANAGED_RECEIPT_SET_MISMATCH")

    if not position_rows:
        blockers.add("EMPTY_MANAGED_VIEW_NOT_INDEPENDENT_EMPTY_PROOF")
    if quarantined is not None and quarantined:
        blockers.add("QUARANTINED_POSITIVE_RESIDUALS_NOT_CLOSED")
    if unprotected is not None and unprotected:
        blockers.add("UNPROTECTED_PARTIAL_OR_RESIDUAL_INCIDENT")
    if legs_missing is not None and legs_missing:
        blockers.add("MISSING_RECORDED_PROTECTION_LEG")

    seen = set()
    for row in position_rows:
        if not isinstance(row, dict):
            blockers.add("MALFORMED_POSITION_ROW")
            continue
        sym = row.get("symbol")
        side = row.get("direction")
        slot = _count(row.get("position_slot"))
        if not isinstance(sym, str) or not sym.strip() or side not in ("LONG", "SHORT") or slot is None or slot < 1:
            blockers.add("INVALID_POSITION_IDENTITY")
            continue
        ident = (sym, side, slot)
        if ident in seen:
            blockers.add("DUPLICATE_POSITION_ROW")
        seen.add(ident)

        reasons = []
        receipts = _count(row.get("receipts_24h"))
        invalid = _count(row.get("structurally_invalid_receipts"))
        missing_quote = _count(row.get("missing_independent_quote_receipt_link"))
        missing_anchor = _count(row.get("absent_prior_anchor_rows"))
        breaches = _count(row.get("observed_gaps_over_35m"))
        longest = _nonnegative(row.get("longest_observed_gap_seconds"))
        latest = _utc(row.get("latest_24h_receipt"))
        if receipts is None or receipts == 0 or latest is None:
            reasons.append("POSITION_OBSERVATIONS_MISSING")
        if missing_anchor is None or missing_anchor:
            reasons.append("PRIOR_MONITORING_CHAIN_UNKNOWN")
        if breaches is None or breaches:
            reasons.append("FROZEN_35M_HISTORICAL_GAP")
        if longest is None or longest > FROZEN_MAX_SECONDS:
            reasons.append("FROZEN_35M_OBSERVATION_GAP_OR_UNKNOWN")
        if invalid is None or invalid:
            reasons.append("UNUSABLE_RECORDED_POSITION_ATTEMPTS")
        if missing_quote is None or missing_quote:
            reasons.append("INDEPENDENT_QUOTE_CUSTODY_MISSING")
        if now is not None and latest is not None:
            delta = Decimal(str((now - latest).total_seconds()))
            if delta < 0:
                reasons.append("OBSERVATION_CLOCK_FROM_FUTURE")
            elif delta > FROZEN_MAX_SECONDS:
                reasons.append("FROZEN_35M_CURRENT_POSITION_STALE")
        # A valid structural scan cannot cancel a historical breach.
        if reasons:
            identifier = sha256((
                "offline-only|" + sym + "|" + side + "|" + str(slot) + "|" +
                (checked_at_utc if isinstance(checked_at_utc, str) else "invalid-clock")
            ).encode()).hexdigest()[:24]
            incidents.append({
                "offline_case_id": identifier,
                "symbol": sym,
                "direction": side,
                "position_slot": slot,
                "severity": "CRITICAL",
                "reasons": sorted(set(reasons)),
                "delivery_state": "NOT_SENT_SYNTHETIC_DIAGNOSTIC",
            })

    if blockers:
        incidents.append({
            "offline_case_id": "global-inventory-unknown",
            "severity": "CRITICAL",
            "reasons": sorted(blockers),
            "delivery_state": "NOT_SENT_SYNTHETIC_DIAGNOSTIC",
        })
    return {
        "status": "OFFLINE_FAIL_CLOSED_ALERT_CANDIDATES" if incidents else
                  "OFFLINE_STRUCTURAL_RECORDS_ONLY_NOT_AUTHENTICATED",
        "position_rows": len(position_rows),
        "redacted_incident_candidates": incidents,
        "run_blockers": sorted(blockers),
        "frozen_maximum_monitor_gap_seconds": 2100,
        "independent_asof_inventory_authenticated": False,
        "independent_quote_custody_authenticated": False,
        "actual_alert_dispatched": False,
        "actual_provider_acceptance_verified": False,
        "actual_inbox_delivery_verified": False,
        "operational_72h_pilot_qualified": False,
        "scientific_pass_permitted": False,
        "production_deployment_permitted": False,
        "paper_admission_permitted": False,
        "exchange_authority": False,
        "trade_permission": False,
        "order_path": "NONE",
        "new_spend_usd": 0,
    }
