"""Successor-only 24h paper exits. Legacy positions keep their original policy.

Activation and prior observations must be supplied by the database evidence view.
This module neither grants paper admission nor creates an activation.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .paper_exit import (
    _attempt, _exit_event, _modeled_exit_fill, _quote_map,
    reconcile_active_protections,
)
from .paper_lifecycle import PaperState

PROTOCOL = "paper-horizon-24h-v0.1"
HORIZON = timedelta(hours=24)
MAX_LAG = timedelta(minutes=35)


def successor_admission_permitted(snapshot: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    """Admission is closed until one verified successor identity is activated."""
    if len(rows) != 1:
        return False
    activation = rows[0]
    identity = snapshot.get("validation_identity") or {}
    observed = _time(snapshot.get("collected_at_utc"))
    started = _time(activation.get("activated_at_utc"))
    cutoff = _time(activation.get("admission_cutoff_at_utc"))
    return bool(
        activation.get("protocol_version") == PROTOCOL
        and observed is not None and started is not None and cutoff is not None
        and started < observed <= cutoff
        and identity.get("run_source") == "RENDER_CRON"
        and identity.get("runtime_role") == "RENDER_CRON"
        and activation.get("scientific_fingerprint_sha256")
        and identity.get("scientific_fingerprint_sha256")
        == activation["scientific_fingerprint_sha256"]
    )


def _time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def reconcile_successor_protections(
    snapshot: dict[str, Any],
    open_positions: list[dict[str, Any]],
    *,
    attempted_entry_order_ids: set[str] | None = None,
    quote_overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Retain protective precedence; never turn a failed horizon into a later win."""
    attempted = attempted_entry_order_ids or set()
    quotes = _quote_map(snapshot)
    quotes.update({str(k).upper(): dict(v) for k, v in (quote_overrides or {}).items()
                   if isinstance(v, dict)})
    attempts, fills, events = [], [], []
    identity = snapshot.get("validation_identity") or {}
    run_id = str(snapshot.get("run_id") or "")
    scan_at = _time(snapshot.get("collected_at_utc"))
    if not run_id or scan_at is None:
        raise ValueError("Horizon reconciliation requires run identity and aware time")

    for position in open_positions:
        order_id = str(position.get("entry_order_id") or "")
        if not order_id or order_id in attempted:
            continue
        if position.get("horizon_protocol") is None:
            a, f, e = reconcile_active_protections(
                snapshot, [position], quote_overrides=quote_overrides)
            attempts.extend(a); fills.extend(f); events.extend(e)
            continue

        # Discovery/web/GitHub scans are not observations in the sealed Render
        # cohort. They must not manufacture failures or advance its gap clock.
        # A purported canonical run with the wrong role/fingerprint still fails
        # closed below. Legacy protection routing above remains unchanged.
        if identity.get("run_source") != "RENDER_CRON":
            continue

        quote = quotes.get(str(position.get("symbol") or "").upper())
        observed_text = str((quote or {}).get("_captured_at_utc")
                            or snapshot["collected_at_utc"])
        observed = _time(observed_text)
        entry = _time(position.get("entry_completed_at_utc"))
        previous_text = position.get("previous_exit_observed_at_utc")
        previous_observation = _time(previous_text)
        previous = previous_observation if previous_text is not None else entry
        failures = []
        if position.get("horizon_protocol") != PROTOCOL:
            failures.append("HORIZON_PROTOCOL_UNKNOWN")
        if (identity.get("run_source") != "RENDER_CRON"
                or identity.get("runtime_role") != "RENDER_CRON"):
            failures.append("HORIZON_SOURCE_NOT_CANONICAL")
        frozen = position.get("horizon_scientific_fingerprint_sha256")
        if not frozen or identity.get("scientific_fingerprint_sha256") != frozen:
            failures.append("HORIZON_FINGERPRINT_MISMATCH")
        if observed is None or entry is None or previous is None:
            failures.append("HORIZON_CLOCK_EVIDENCE_INVALID")
        elif (
            not failures
            and previous_text is None
            and str(position.get("entry_completed_source_run_id") or "") == run_id
            and scan_at <= entry <= scan_at + MAX_LAG
            and scan_at <= observed <= scan_at + MAX_LAG
        ):
            # This immutable run established the fill, not a later observation.
            # Do not mark it AMBIGUOUS/FAILED or fabricate a NO_TRIGGER baseline.
            # First later monitoring is still timed from the actual entry fill.
            continue
        elif observed < scan_at or observed < entry or observed <= previous:
            failures.append("HORIZON_OBSERVATION_REPLAY_OR_CLOCK_INVALID")

        # Invalid source/clock must not fabricate either a protective or timeout fill.
        if failures:
            a = _attempt(position, quote, source_run_id=run_id,
                         observed_at_utc=snapshot["collected_at_utc"],
                         outcome="HORIZON_FAILED", blockers=failures)
            a["evidence"]["horizon_integrity_failed"] = True
            a["evidence"]["horizon_protocol"] = PROTOCOL
            attempts.append(a)
            continue

        deadline = entry + HORIZON
        due = observed >= deadline
        if observed - previous > MAX_LAG:
            failures.append("HORIZON_MONITORING_GAP_EXCEEDED")
        if position.get("horizon_integrity_failed") is True:
            failures.append("HORIZON_PRIOR_FAILURE")
        if observed > deadline + MAX_LAG:
            failures.append("HORIZON_OBSERVATION_LAG_EXCEEDED")
        if position.get("unresolved_protective_evidence") is True:
            failures.append("HORIZON_EARLIER_PROTECTIVE_TRIGGER_UNRESOLVED")

        a, f, e = reconcile_active_protections(
            snapshot, [position], quote_overrides=quote_overrides)
        attempt = a[0]
        if attempt["outcome"] in {"INPUT_MISSING", "AMBIGUOUS"}:
            failures.append("HORIZON_MONITORING_OBSERVATION_UNUSABLE")
        if due and not f and attempt["outcome"] != "NO_TRIGGER":
            failures.append("HORIZON_FIRST_DUE_OBSERVATION_UNUSABLE")

        # SL/TP always takes precedence. Failures remain attached even if a
        # later protective exit manages the position successfully.
        if due and not f and attempt["outcome"] == "NO_TRIGGER" and not failures:
            fill, blockers = _modeled_exit_fill(
                position, quote, source_run_id=run_id,
                observed_at_utc=observed_text, protection_type="HORIZON_24H")
            if fill is None or blockers:
                failures.extend(blockers or ["HORIZON_FILL_EVIDENCE_MISSING"])
            else:
                attempt["outcome"] = "HORIZON_CLOSED"
                f = [fill]
                e = [_exit_event(position, fill, source_run_id=run_id,
                                 observed_at_utc=observed_text,
                                 state=PaperState.HORIZON_CLOSED)]
        if due and failures and not f:
            attempt["outcome"] = "HORIZON_FAILED"
        attempt["blockers"] = list(dict.fromkeys([*attempt["blockers"], *failures]))
        attempt["evidence"].update({
            "horizon_protocol": PROTOCOL,
            "horizon_integrity_failed": bool(failures),
            "entry_completed_at_utc": entry.isoformat(),
            "horizon_deadline_utc": deadline.isoformat(),
            "actual_holding_seconds": (observed-entry).total_seconds(),
            "horizon_observation_lag_seconds": max(0, (observed-deadline).total_seconds()),
            "maximum_observation_lag_seconds": MAX_LAG.total_seconds(),
        })
        attempts.append(attempt); fills.extend(f); events.extend(e)
    return attempts, fills, events
