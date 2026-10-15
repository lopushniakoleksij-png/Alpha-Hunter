"""P2 offline rolling receipt-chain red team, NOT a live continuity monitor.

Read-only pure verification over supplied signed synthetic envelopes. Never accepts
a string 'seal_verified' or a parent scan as evidence. A locally consistent chain
CANNOT establish real collection, independent journal durability, venue signatures,
actual 72-hour uptime, delivery, R10 scientific PASS, or order authority.
"""
from __future__ import annotations

from successor_p2_source_quote_provenance_contract_v01 import (
    accept, unseal, stamp, EvidenceRejected, FROZEN_MAX_GAP_SECONDS,
)


def audit_local_rolling_chain(cycles, *, source_key, quote_key, custody_key):
    """Fail closed for any omitted/mismatched receipt, changed position or chain break.

    cycles is an iterable of {"source","quotes","previous","current","now_utc"}.
    The earliest predecessor is bootstrap-only: no earlier operational coverage
    can be inferred. This is a research replay contract, not a deployment.
    """
    blockers = []
    prior_current = None
    prior_run = None
    prior_clock = None
    prior_ids = None
    checked = 0
    max_observed_gap = 0
    for idx, cycle in enumerate(cycles):
        checked += 1
        if not isinstance(cycle, dict):
            blockers.append(f"CYCLE_{idx}_NOT_A_RECORD")
            break
        try:
            source = unseal(cycle["source"], source_key, "SOURCE_REPEATABLE_READ")
            run = source["run_id"]
            now = stamp(cycle["now_utc"])
            asof = stamp(source["asof_utc"])
            cur_rows = cycle["current"]
            old_rows = cycle["previous"]
            if not isinstance(cur_rows, list) or not isinstance(old_rows, list):
                raise EvidenceRejected("POSITION_RECEIPTS_MISSING")
            current = {}
            previous = {}
            for rows, dest in ((cur_rows, current), (old_rows, previous)):
                for sealed in rows:
                    event = unseal(sealed, custody_key, "PAPER_POSITION_OBSERVATION")
                    oid = event.get("entry_order_id")
                    if not isinstance(oid, str) or not oid or oid in dest:
                        raise EvidenceRejected("DUPLICATE_OR_MISSING_ORDER_ID")
                    dest[oid] = (sealed, event)
            ids = frozenset(current)
            if not ids or ids != frozenset(previous):
                raise EvidenceRejected("PER_CYCLE_ORDER_COVERAGE_MISMATCH")
            if idx:
                if run == prior_run or asof <= prior_clock or now <= prior_clock:
                    raise EvidenceRejected("REPLAY_OR_NONMONOTONIC_SOURCE_RUN")
                if ids != prior_ids:
                    # A genuine exit/admission needs independently attested
                    # terminal/admission events, which this test does not supply.
                    raise EvidenceRejected("POSITION_MEMBERSHIP_CHANGE_UNPROVEN")
                for oid in ids:
                    if previous[oid][0] != prior_current[oid][0]:
                        raise EvidenceRejected("PREVIOUS_SEAL_NOT_FROM_PRIOR_CYCLE")
            else:
                # Prior observation in the first fixture is NOT independently
                # proven to cover the time before the supplied series.
                if idx != 0:
                    raise EvidenceRejected("BOOTSTRAP_INVALID")
            result = accept(
                cycle["source"], cycle["quotes"], old_rows, cur_rows,
                source_key=source_key, quote_key=quote_key,
                custody_key=custody_key, now_utc=cycle["now_utc"],
            )
            if result["status"] != "LOCAL_SIGNED_EVIDENCE_CANDIDATE_NOT_UPSTREAM_AUTHENTICATED":
                raise EvidenceRejected("LOCAL_CYCLE_REJECTED:" + ",".join(result["blockers"]))
            if result["locally_receipt_qualified"] != len(ids):
                raise EvidenceRejected("PER_POSITION_LOCAL_QUALIFICATION_MISSING")
            for oid in ids:
                prev_at = stamp(previous[oid][1]["observed_at_utc"])
                curr_at = stamp(current[oid][1]["observed_at_utc"])
                gap = (curr_at - prev_at).total_seconds()
                if not 0 < gap <= FROZEN_MAX_GAP_SECONDS:
                    raise EvidenceRejected("FROZEN_35_MINUTE_MONITOR_GAP_BREACH")
                max_observed_gap = max(max_observed_gap, gap)
            prior_current = current
            prior_run = run
            prior_clock = asof
            prior_ids = ids
        except (KeyError, ValueError, TypeError, AttributeError, OverflowError) as exc:
            blockers.append(f"CYCLE_{idx}_" + (
                str(exc) if isinstance(exc, EvidenceRejected) else "MALFORMED_EVIDENCE"
            ))
            break
    if checked < 2 and not blockers:
        blockers.append("INSUFFICIENT_MULTICYCLE_EVIDENCE")
    return {
        "status": (
            "LOCAL_ROLLING_CHAIN_STRUCTURALLY_CONSISTENT_NOT_LIVE_PROOF"
            if not blockers else "FAIL_CLOSED_UNKNOWN_OR_GAP"
        ),
        "blockers": blockers,
        "cycles_checked": checked,
        "max_local_observation_gap_seconds": max_observed_gap if not blockers else None,
        "frozen_monitor_limit_seconds": 2100,
        "bootstrap_prior_history_authenticated": False,
        "source_authenticated_by_independent_live_connection": False,
        "venue_quote_signed_by_bitget": False,
        "operational_independent_custody_proven": False,
        "continuous_prospective_35m_proven": False,
        "actual_alert_delivery_verified": False,
        "scientific_pass_permitted": False,
        "trade_permission": False,
        "exchange_authority": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }
