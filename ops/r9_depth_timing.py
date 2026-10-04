"""Forward-only R9 diagnostic. Never writes execution or profitability evidence."""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import datetime, timezone

from ops.r8_depth_shadow import _fetch_depth, _rest_get, _rest_insert

FINGERPRINT = "5a869160798c47904023a1fa7f6ef7c79f6452468379185e08abb38feb1f5fed"
SPEC = "SEALED-ARCH-V14R9-EXEC-PAPER-24H-20261004"
CAPTURES = "alpha_hunter_r9_depth_timing_captures_v01"
RUNS = "alpha_hunter_r9_depth_timing_runs_v01"


def utc(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def number(value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError("Non-positive or non-finite book value")
    return result


def classify(order, depth, received):
    """A displayed book is a capacity observation, never proof of execution."""
    ts = int(depth["ts"])
    age = received.timestamp() * 1000 - ts
    if not -5000 <= age <= 30000:
        raise ValueError("Stale or future book")
    sides = {}
    for name, reverse in (("asks", False), ("bids", True)):
        levels = [(number(p), number(q)) for p, q, *_ in depth[name]]
        if not levels or len({p for p, _ in levels}) != len(levels):
            raise ValueError("Empty or duplicate-price book")
        sides[name] = sorted(levels, reverse=reverse)
    if sides["bids"][0][0] >= sides["asks"][0][0]:
        raise ValueError("Crossed or locked book")
    direction = order["direction"]
    if direction not in ("LONG", "SHORT"):
        raise ValueError("Invalid direction")
    limit = number(order["limit_price"])
    required = number(order["quantity"])
    levels = sides["asks" if direction == "LONG" else "bids"]
    best, l1 = levels[0]
    eligible = [(p, q) for p, q in levels
                if (p <= limit if direction == "LONG" else p >= limit)]
    available = sum(q for _, q in eligible)
    if not eligible:
        verdict = "NOT_CROSSED"
    elif l1 >= required:
        verdict = "L1_SUFFICIENT"
    elif available >= required:
        verdict = "RETURNED_DEPTH_SUFFICIENT_L1_INSUFFICIENT"
    else:
        verdict = "RETURNED_DEPTH_INSUFFICIENT"
    remaining, notional = required, 0.0
    for p, q in eligible:
        take = min(q, remaining)
        notional += p * take
        remaining -= take
    return {
        "verdict": verdict, "exchange_timestamp_ms": ts,
        "book_age_ms": age, "best_price": best, "top_quantity": l1,
        "eligible_quantity": available, "required_quantity": required,
        "distance_pct": 100 * (best - limit if direction == "LONG" else limit - best) / best,
        "displayed_book_vwap": notional / required if available >= required else None,
        "asks": sides["asks"], "bids": sides["bids"],
        "precision": depth.get("precision"), "scale": depth.get("scale"),
        "fill_proven": False, "profitability_sample_eligible": False,
    }


def collect(base, key):
    run_id = uuid.uuid4().hex
    started = datetime.now(timezone.utc)
    summary = {"run_id": run_id, "started_at_utc": started.isoformat(),
               "status": "STARTED", "orders_seen": 0, "captures_saved": 0,
               "capture_failures": 0}
    # Persist the start separately so interrupted workers cannot look successful.
    _rest_insert(base, key, RUNS, {**summary, "phase": "START"})
    try:
        activation = _rest_get(base, key, "alpha_hunter_paper_admission_open_v09",
                               {"select": "*", "activation_id": "eq.PAPER_EXECUTION_R9"})
        if len(activation) != 1:
            raise ValueError("R9 admission inactive")
        a = activation[0]
        if (a["spec_id"] != SPEC or a["scientific_fingerprint_sha256"] != FINGERPRINT
                or a["paper_only"] is not True or a["exchange_authority"] is not False
                or a["trade_permission"] is not False or a["order_path"] != "NONE"):
            raise ValueError("R9 activation invariant mismatch")
        runtime = _rest_get(base, key, "alpha_hunter_production_deployment_runtime_status_v03", {"select": "*"})[0]
        scan_age = (started - utc(runtime["latest_canonical_scan_at_utc"])).total_seconds()
        if (runtime["deployment_status"] != "MATCHED"
                or runtime["scientific_fingerprint_sha256"] != FINGERPRINT
                or not 0 <= scan_age <= 2100):
            raise ValueError("Canonical identity or freshness mismatch")
        orders = _rest_get(base, key, "alpha_hunter_r9_depth_timing_open_v01",
                           {"select": "*", "order": "submitted_at_utc.asc,order_id.asc", "limit": "251"})
        if len(orders) > 250:
            raise ValueError("Diagnostic order limit exceeded; no silent truncation")
        summary["orders_seen"] = len(orders)
        for order in orders:
            requested = datetime.now(timezone.utc)
            if not 0 <= (requested - utc(order["submitted_at_utc"])).total_seconds() <= 2100:
                continue
            evidence = {"verdict": "CAPTURE_FAILED", "fill_proven": False,
                        "profitability_sample_eligible": False}
            try:
                depth, _ = _fetch_depth(order["symbol"])
                received = datetime.now(timezone.utc)
                evidence = classify(order, depth, received)
                if (received - utc(order["submitted_at_utc"])).total_seconds() > 2100:
                    evidence["verdict"] = "RECEIVED_AFTER_EXPIRY"
            except Exception as exc:
                received = datetime.now(timezone.utc)
                # Exception class only: never persist response bodies or credentials.
                evidence["error_type"] = type(exc).__name__
                summary["capture_failures"] += 1
            evidence.update({"order_snapshot": order, "scientific_fingerprint": FINGERPRINT,
                             "canonical_run_id": runtime["latest_canonical_run_id"],
                             "request_duration_ms": (received-requested).total_seconds()*1000})
            _rest_insert(base, key, CAPTURES, {
                "capture_id": hashlib.sha256(f"{run_id}|{order['order_id']}".encode()).hexdigest(),
                "run_id": run_id, "order_id": order["order_id"],
                "requested_at_utc": requested.isoformat(), "received_at_utc": received.isoformat(),
                "verdict": evidence["verdict"], "evidence": evidence,
            })
            summary["captures_saved"] += 1
        summary["status"] = "DEGRADED" if summary["capture_failures"] else "COMPLETE"
    except Exception as exc:
        summary["status"] = "FAILED"
        summary["error_type"] = type(exc).__name__
    _rest_insert(base, key, RUNS, {**summary, "phase": "END"})
    return summary


if __name__ == "__main__":
    result = collect(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "COMPLETE" else 1)
