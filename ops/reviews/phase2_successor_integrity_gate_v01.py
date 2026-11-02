"""Pure, fail-closed successor evidence gate. OFFLINE RESEARCH ONLY.

Does not connect to a database, import a scanner, generate fills, or grant
trading authority. Original R8/R9/R10 records are never modified.
"""
from datetime import datetime, timezone
from math import isfinite

SAFE_OUTCOMES = frozenset({'NO_TRIGGER', 'STOP_TRIGGERED', 'TARGET_TRIGGERED', 'HORIZON_CLOSED'})


def _utc(value):
    if isinstance(value, datetime):
        d = value
    elif isinstance(value, str):
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    else:
        raise ValueError('timestamp must be ISO-8601 with a timezone')
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError('timestamp without timezone is not evidence')
    return d.astimezone(timezone.utc)


def evaluate_scan(*, run_id, collected_at_utc, expected_symbols,
                  persisted_symbols, positions, receipts,
                  expected_fingerprint, observed_fingerprint,
                  expected_source, observed_source,
                  monitoring_limit_minutes, prior_cohort_failure=False):
    """Return independent operational/scientific verdicts, never trade permission.

    positions is an independently captured pre-reconciliation inventory.
    Each position must include its last independently persisted observation UTC.
    Every position requires exactly one current-run receipt. Without a previous
    receipt (e.g. newly admitted position), fail until a separately reviewed
    entry baseline proves the timing origin; never invent an observation.
    """
    faults = []
    try:
        now = _utc(collected_at_utc)
    except (ValueError, TypeError):
        now = None
        faults.append('SCAN_TIMESTAMP_INVALID')
    if not isinstance(run_id, str) or not run_id.strip():
        faults.append('RUN_ID_MISSING')
    if observed_source != expected_source or not expected_source:
        faults.append('RUN_SOURCE_MISMATCH')
    if observed_fingerprint != expected_fingerprint or not expected_fingerprint:
        faults.append('SCIENTIFIC_FINGERPRINT_MISMATCH')
    if (not isinstance(monitoring_limit_minutes, (int, float))
            or isinstance(monitoring_limit_minutes, bool)
            or not isfinite(monitoring_limit_minutes)
            or monitoring_limit_minutes <= 0):
        faults.append('MONITORING_LIMIT_INVALID')
        limit = None
    else:
        limit = float(monitoring_limit_minutes) * 60

    if (not isinstance(expected_symbols, (list, tuple)) or not expected_symbols
            or any(not isinstance(s, str) or not s for s in expected_symbols)
            or len(set(expected_symbols)) != len(expected_symbols)):
        faults.append('EXPECTED_SYMBOL_INVENTORY_INVALID')
    if (not isinstance(persisted_symbols, (list, tuple))
            or any(not isinstance(s, str) or not s for s in persisted_symbols)
            or len(set(persisted_symbols)) != len(persisted_symbols)):
        faults.append('PERSISTED_SYMBOL_INVENTORY_INVALID')
    if ('EXPECTED_SYMBOL_INVENTORY_INVALID' not in faults
            and 'PERSISTED_SYMBOL_INVENTORY_INVALID' not in faults
            and set(expected_symbols) != set(persisted_symbols)):
        faults.append('CANONICAL_CHILD_IDENTITY_INCOMPLETE')

    if not isinstance(positions, (list, tuple)) or not isinstance(receipts, (list, tuple)):
        faults.append('MONITORING_INVENTORY_UNAVAILABLE')
        positions, receipts = [], []
    ids = [p.get('entry_order_id') for p in positions if isinstance(p, dict)]
    if (len(ids) != len(positions)
            or any(not isinstance(k, str) or not k for k in ids)
            or len(set(ids)) != len(ids)):
        faults.append('POSITION_INVENTORY_INVALID')
    seen_receipts = set()
    by_id = {}
    for receipt in receipts:
        if not isinstance(receipt, dict):
            faults.append('RECEIPT_INVALID')
            continue
        key = receipt.get('entry_order_id')
        if not isinstance(key, str) or not key or key in seen_receipts:
            faults.append('DUPLICATE_OR_MISSING_RECEIPT_ID')
            continue
        seen_receipts.add(key)
        by_id[key] = receipt
    if set(by_id) != set(ids):
        faults.append('MONITORING_RECEIPT_COVERAGE_FAILED')

    for position in positions:
        if not isinstance(position, dict):
            continue
        key = position.get('entry_order_id')
        receipt = by_id.get(key)
        if not receipt:
            continue
        if (any(receipt.get(k) != position.get(k)
                for k in ('decision_id', 'symbol', 'direction'))
                or receipt.get('source_run_id') != run_id):
            faults.append('RECEIPT_IDENTITY_MISMATCH')
        if receipt.get('outcome') not in SAFE_OUTCOMES or receipt.get('blockers') != []:
            faults.append('RECEIPT_UNUSABLE')
        if (receipt.get('paper_only') is not True
                or receipt.get('exchange_authority') is not False
                or receipt.get('trade_permission') is not False
                or receipt.get('order_path') != 'NONE'):
            faults.append('RECEIPT_AUTHORITY_INVALID')
        try:
            observed = _utc(receipt.get('observed_at_utc'))
            previous = _utc(position.get('prior_observed_at_utc'))
            if now is None or limit is None or not (previous < observed <= now):
                faults.append('MONITORING_OBSERVATION_ORDER_INVALID')
            else:
                if (observed - previous).total_seconds() > limit:
                    faults.append('MONITORING_GAP_OVER_FROZEN_LIMIT')
                if (now - observed).total_seconds() > limit:
                    faults.append('MONITORING_RECEIPT_STALE')
        except (ValueError, TypeError):
            faults.append('MONITORING_TIME_EVIDENCE_MISSING')
    blockers = tuple(sorted(set(faults)))
    return {
        'operational_evidence_complete': not blockers,
        'scientific_eligible': not blockers and prior_cohort_failure is False,
        'historical_failure_preserved': bool(prior_cohort_failure),
        'blockers': blockers,
        'paper_only': True,
        'trade_permission': False,
        'exchange_authority': False,
        'production_promotion_permitted': False,
    }


def check_exit_capacity(*, direction, quantity, best_bid, best_ask,
                        bid_size, ask_size, prior_stop_unresolved=False):
    """Diagnostic eligibility only; never manufactures an executable fill."""
    if prior_stop_unresolved:
        return 'UNRESOLVED_PRIOR_STOP_PRECEDENCE'
    if direction not in ('LONG', 'SHORT'):
        return 'DIRECTION_INVALID'
    values = (quantity, best_bid, best_ask, bid_size, ask_size)
    if any(not isinstance(v, (int, float)) or isinstance(v, bool)
           or not isfinite(v) or v <= 0 for v in values):
        return 'EXECUTABLE_QUOTE_OR_QUANTITY_MISSING'
    if best_ask < best_bid:
        return 'CROSSED_QUOTE_UNVERIFIED'
    if (bid_size if direction == 'LONG' else ask_size) < quantity:
        return 'INSUFFICIENT_CLOSE_SIDE_TOP_OF_BOOK'
    return 'CAPACITY_OBSERVED_NOT_EXECUTION_PROVEN'
