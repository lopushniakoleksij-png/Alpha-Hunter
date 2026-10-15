"""P3 isolated execution-cost evidence QUALITY CONTRACT. No valuation or authority.

Strictly SYNTHETIC test fixtures only. Descriptive public market benchmark rows
are never a substitute for verified frozen decision -> exact venue fill IDs.
Even complete test fixtures cannot yield validated costs, realized net R,
scientific promotion, live trade permission, or a real sample count.
No I/O, network, production import, order, database or configuration writes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

FROZEN_SCIENTIFIC_SPEC = "SEALED-ARCH-V14R10-EXEC-PAPER-24H-20261005"
SAMPLE_FLOORS = {"total": 30, "TAKER": 20, "MAKER": 10, "LONG": 5, "SHORT": 5}
COMPONENTS = (
    "realized_entry_fee_usdt",
    "realized_exit_fee_usdt",
    "observed_entry_spread_usdt",
    "signed_entry_slippage_usdt",
    "signed_exit_slippage_usdt",
    "observed_market_impact_usdt",
    "signed_post_fill_markout_usdt",
    "realized_funding_usdt",
)
SIGNED_COMPONENTS = frozenset((
    "signed_entry_slippage_usdt", "signed_exit_slippage_usdt",
    "signed_post_fill_markout_usdt", "realized_funding_usdt",
))
NEEDED_DECISION = (
    "decision_id", "source_run_id", "symbol", "direction",
    "spec_id", "frozen_at_utc", "intended_order_id",
    "arrival_quote_id", "entry_price", "stop_price",
)
NEEDED_FILL = (
    "decision_id", "intended_order_id", "symbol", "direction",
    "exchange_order_id", "venue_trade_id", "filled_at_utc",
    "filled_quantity", "fill_price", "liquidity_role",
)
NEEDED_EXIT = (
    "entry_venue_trade_id", "exit_venue_trade_id", "exit_at_utc",
    "exited_quantity", "exit_price", "exit_quote_id",
)


def clock(value):
    if not isinstance(value, str):
        return None
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return at.astimezone(timezone.utc) if at.tzinfo is not None else None


def number(value, *, allow_negative=False, strictly_positive=False):
    if isinstance(value, bool) or value is None:
        return None
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not n.is_finite() or (n < 0 and not allow_negative) or (strictly_positive and n <= 0):
        return None
    return n


def _missing(record, names):
    return any(not isinstance(record, dict) or record.get(name) in (None, "") for name in names)


def review_fixture(rows, *, now_utc, descriptive_benchmark_count=0):
    """Review test-fixture identity and input completeness; NEVER estimate PnL."""
    blockers = set()
    accepted = []
    seen_decisions = set()
    seen_fills = set()
    now = clock(now_utc)
    if now is None:
        blockers.add("REVIEW_CLOCK_INVALID")
    if not isinstance(descriptive_benchmark_count, int) or isinstance(descriptive_benchmark_count, bool) or descriptive_benchmark_count < 0:
        blockers.add("HISTORICAL_BENCHMARK_COUNT_INVALID")
    if not isinstance(rows, list):
        blockers.add("SAMPLE_NOT_A_LIST")
        rows = []

    for idx, item in enumerate(rows):
        reasons = []
        if not isinstance(item, dict):
            reasons.append("ROW_INVALID")
            blockers.add("ROW_INVALID")
            continue
        d, f, e, costs = (item.get(name) for name in
                          ("decision", "entry_fill", "exit_fill", "components"))
        if _missing(d, NEEDED_DECISION) or _missing(f, NEEDED_FILL):
            reasons.append("FROZEN_DECISION_OR_EXACT_ENTRY_FILL_MISSING")
        if _missing(e, NEEDED_EXIT):
            reasons.append("EXIT_FILL_OR_FULL_POSITION_CLOSE_MISSING")
        if not isinstance(d, dict) or not isinstance(f, dict) or not isinstance(e, dict):
            blockers.update(reasons)
            continue

        did, vid = d.get("decision_id"), f.get("venue_trade_id")
        if did in seen_decisions or vid in seen_fills:
            reasons.append("DUPLICATE_DECISION_OR_FILL")
        seen_decisions.add(did)
        seen_fills.add(vid)
        if not all(
            str(x).startswith("synthetic-") for x in
            (did, vid, d.get("source_run_id"), d.get("intended_order_id"),
             f.get("exchange_order_id"), e.get("exit_venue_trade_id"))
        ):
            reasons.append("NON_SYNTHETIC_SOURCE_NOT_AUTHORIZED_FOR_OFFLINE_FIXTURE")
        if (d.get("spec_id") != FROZEN_SCIENTIFIC_SPEC
                or d.get("direction") not in ("LONG", "SHORT")
                or f.get("liquidity_role") not in ("MAKER", "TAKER")
                or f.get("direction") != d.get("direction")
                or f.get("symbol") != d.get("symbol")
                or f.get("decision_id") != did
                or f.get("intended_order_id") != d.get("intended_order_id")
                or e.get("entry_venue_trade_id") != vid
                or e.get("exit_venue_trade_id") == vid):
            reasons.append("DECISION_FILL_EXIT_IDENTITY_MISMATCH")

        a,b,c = clock(d.get("frozen_at_utc")),clock(f.get("filled_at_utc")),clock(e.get("exit_at_utc"))
        if not a or not b or not c or not now or not (a <= b <= c <= now):
            reasons.append("FROZEN_DECISION_FILL_EXIT_CLOCK_INVALID")
        q = number(f.get("filled_quantity"), strictly_positive=True)
        x = number(e.get("exited_quantity"), strictly_positive=True)
        if q is None or x != q:
            reasons.append("PARTIAL_OR_UNVERIFIED_FULL_EXIT_QUANTITY")
        entry = number(d.get("entry_price"), strictly_positive=True)
        stop = number(d.get("stop_price"), strictly_positive=True)
        fill = number(f.get("fill_price"), strictly_positive=True)
        exit_price = number(e.get("exit_price"), strictly_positive=True)
        if (entry is None or stop is None or fill is None or exit_price is None
                or entry == stop or
                (d.get("direction") == "LONG" and stop >= entry) or
                (d.get("direction") == "SHORT" and stop <= entry)):
            reasons.append("UNVALIDATED_STRUCTURAL_RISK_GEOMETRY")
        if not isinstance(costs, dict) or set(costs) != set(COMPONENTS):
            reasons.append("REALISTIC_COST_COMPONENT_SET_INCOMPLETE")
        else:
            seen_ref = set()
            for key in COMPONENTS:
                cst = costs[key]
                if not isinstance(cst, dict):
                    reasons.append("COMPONENT_RECORD_INVALID:" + key)
                    continue
                receipt = cst.get("receipt_id")
                if (cst.get("evidence_class") != "SYNTHETIC_TEST_ONLY"
                        or not isinstance(receipt, str) or
                        not receipt.startswith("synthetic-") or receipt in seen_ref
                        or cst.get("currency") != "USDT"):
                    reasons.append("COMPONENT_SOURCE_OR_CURRENCY_UNVERIFIED:" + key)
                seen_ref.add(receipt)
                if number(cst.get("amount"), allow_negative=key in SIGNED_COMPONENTS) is None:
                    reasons.append("COMPONENT_NUMERIC_INVALID_OR_MISSING:" + key)
        if not isinstance(d.get("arrival_quote_id"), str) or not d["arrival_quote_id"].startswith("synthetic-"):
            reasons.append("ARRIVAL_QUOTE_SOURCE_UNVERIFIED")
        if not isinstance(e.get("exit_quote_id"), str) or not e["exit_quote_id"].startswith("synthetic-"):
            reasons.append("EXIT_QUOTE_SOURCE_UNVERIFIED")
        if reasons:
            blockers.update(reasons)
        else:
            accepted.append((did, f["liquidity_role"], d["direction"]))

    total = len(accepted)
    counts = {
        "total": total,
        "TAKER": sum(role == "TAKER" for _, role, _ in accepted),
        "MAKER": sum(role == "MAKER" for _, role, _ in accepted),
        "LONG": sum(side == "LONG" for _, _, side in accepted),
        "SHORT": sum(side == "SHORT" for _, _, side in accepted),
    }
    if not all(counts[k] >= floor for k, floor in SAMPLE_FLOORS.items()):
        blockers.add("OFFLINE_ENTRY_CALIBRATION_SAMPLE_FLOORS_NOT_MET")
    if not rows:
        blockers.add("NO_EXACT_LINKED_EXECUTION_FIXTURES")

    return {
        "status": ("OFFLINE_SYNTHETIC_STRUCTURAL_CANDIDATE_NOT_REAL_VALIDATION"
                   if not blockers else "OFFLINE_DATA_INSUFFICIENT_OR_INVALID"),
        "blockers": sorted(blockers),
        "synthetic_structurally_complete_rows": total,
        "synthetic_segment_counts": counts,
        "synthetic_segment_floors_met": all(counts[k] >= v for k,v in SAMPLE_FLOORS.items()),
        "descriptive_benchmark_count_separate_not_verified_executions":
            descriptive_benchmark_count if isinstance(descriptive_benchmark_count, int)
            and not isinstance(descriptive_benchmark_count, bool)
            and descriptive_benchmark_count >= 0 else None,
        "verified_real_execution_rows": 0,
        "verified_real_exit_slippage_rows": 0,
        "verified_real_post_fill_markout_rows": 0,
        "validated_model": False,
        "realistic_net_r": None,
        "realistic_net_pnl": None,
        "live_cost_validation_proven": False,
        "p2_live_receipt_custody_proven": False,
        "scientific_pass_permitted": False,
        "trade_permission": False,
        "exchange_authority": False,
        "production_promotion_permitted": False,
        "order_path": "NONE",
    }
