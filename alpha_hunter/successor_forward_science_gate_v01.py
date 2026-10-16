"""Pure, sealed P2/P3 FORWARD-ONLY science research acceptance contract.

NO service calls, orders, migrations, admission changes or actual approvals.
Historical 2026-10-02..16 paper outcomes must never become holdout wins.
Successor evaluation is not started until independent reviewers preregister a
prospective cohort and approve quote/source/depth and cost custody. Even a
statistically positive research result NEVER authorizes production.
"""
from __future__ import annotations
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from math import sqrt
from statistics import stdev
from collections import defaultdict
from typing import Any,Sequence,Mapping

MIN_CANDIDATES=230
MIN_SYMBOL_CLUSTERS=60
MIN_UTC_DAY_CLUSTERS=20
SEALED_R9_START="2026-10-04T12:37:51.632971Z"
SEALED_R9_END="2026-11-03T12:37:51.632971Z"
MAX_MONITORING_GAP_MINUTES=35
REQUIRED_COHORT="PREREGISTERED_SUCCESSOR_FORWARD_PAPER_SHADOW"
# This fingerprint is a research schema, not a new scientific spec authority.
CONTRACT_ID="P2P3-ISOLATED-SUCCESSOR-COST-HOLDOUT-v01"


def _time(s:Any):
    try:
        x=datetime.fromisoformat(str(s).replace("Z","+00:00"))
        if x.tzinfo is None or x.utcoffset() is None:raise ValueError()
        return x.astimezone(timezone.utc)
    except (TypeError,AttributeError,ValueError):
        raise ValueError("TIMEZONE_AWARE_UTC_REQUIRED")


def _money(s:Any):
    try:
        if isinstance(s,bool):raise ValueError()
        x=Decimal(str(s))
        if not x.is_finite():raise ValueError()
        return x
    except (ValueError,TypeError,InvalidOperation):
        raise ValueError("FINITE_COST_BOUND_NUMBER_REQUIRED")


def _base():
    return dict(
        contract=CONTRACT_ID,scientific_promotion_permitted=False,
        production_promotion_permitted=False,
        trade_permission=False,admission_permission=False,
        profitability_claim_permitted=False,live_order_authority=False,
        r9_start=SEALED_R9_START,r9_cutoff=SEALED_R9_END,
        monitoring_cap_minutes=MAX_MONITORING_GAP_MINUTES,
        historical_reclassifications=0,
        status="BLOCKED_NOT_PREREGISTERED",accepted_forward_events=0,
        symbol_clusters=0,utc_day_clusters=0,
    )


def assess_forward(
    observations:Sequence[Mapping[str,Any]],
    *,
    preregistered_activation_utc:str|None,
    independent_risk_review_reference:str|None,
    frozen_successor_fingerprint:str|None,
) -> dict[str,Any]:
    """Evaluate ONLY qualified post-activation *paired* prospective observations.

    Required source evidence is declarative here; values still require
    external independent authentication. A verified reviewer/signature and
    robust forward source custody cannot be forged by setting text fields.
    Thus even passing numeric tests yields independent-review REQUIRED.
    """
    result=_base()
    if not (preregistered_activation_utc and independent_risk_review_reference
            and frozen_successor_fingerprint):
        result["reason"]="INDEPENDENT_APPROVAL_OR_ACTIVATION_MISSING"
        return result
    try:
        start=_time(preregistered_activation_utc)
    except ValueError as e:
        result["reason"]=str(e);return result
    if start<=_time(SEALED_R9_END):
        result["reason"]="FORWARD_SUCCESSOR_CANNOT_OVERLAP_SEALED_R9"
        return result
    if not observations:
        result.update(status="BLOCKED_NO_FORWARD_EVIDENCE",
                      reason="NO_QUALIFIED_PROSPECTIVE_COMPLETIONS")
        return result

    observed=set()
    grouped_symbol=defaultdict(list)
    grouped_day=defaultdict(list)
    rejected=defaultdict(int)
    for x in observations:
        try:
            if x.get("cohort")!=REQUIRED_COHORT:raise ValueError("LEGACY_OR_WRONG_COHORT")
            stamp=_time(x.get("entry_at_utc"))
            close=_time(x.get("completed_at_utc"))
            if stamp<start or close<=stamp:raise ValueError("HISTORICAL_OR_BAD_TIMING")
            key=str(x.get("event_id") or "")
            sym=str(x.get("symbol") or "")
            if not key or not sym or key in observed:raise ValueError("REUSED_OR_MISSING_ID")
            day=stamp.strftime("%Y-%m-%d")
            if x.get("entry_utc_day")!=day:raise ValueError("DAY_CLUSTER_MISMATCH")
            if x.get("baseline_execution_version")!="FROZEN_BASELINE":
                raise ValueError("BASELINE_NOT_FROZEN")
            if x.get("successor_fingerprint")!=frozen_successor_fingerprint:
                raise ValueError("SUCCESSOR_FINGERPRINT_DRIFT")
            if x.get("quote_source_custody")!="INDEPENDENTLY_ATTESTED":
                raise ValueError("QUOTE_CUSTODY_UNVERIFIED")
            if x.get("depth_and_exit_liquidity")!="INDEPENDENTLY_VERIFIED":
                raise ValueError("DEPTH_OR_EXIT_LIQUIDITY_UNKNOWN")
            if x.get("structural_stop_geometry")!="VERIFIED_NO_WIDENING":
                raise ValueError("STOP_GEOMETRY_UNVERIFIED")
            if x.get("fee_binding")!="VENUE_EVIDENCE_BOUND":
                raise ValueError("FEE_NOT_BOUND")
            if x.get("funding_binding")!="VENUE_EVIDENCE_BOUND":
                raise ValueError("FUNDING_NOT_BOUND")
            if x.get("protection_evidence")!="BOTH_LEGS_AND_RESIDUAL_CONFIRMED":
                raise ValueError("RESIDUAL_PROTECTION_UNVERIFIED")
            if x.get("first_touch_ordering")!="INDEPENDENTLY_RECONSTRUCTED":
                raise ValueError("FIRST_TOUCH_ORDERING_UNKNOWN")
            gap=_money(x.get("max_monitor_gap_minutes"))
            if gap<0 or gap>MAX_MONITORING_GAP_MINUTES:
                raise ValueError("MONITORING_INTEGRITY_FAIL")
            baseline=_money(x.get("baseline_net_usdt_after_all_costs"))
            successor=_money(x.get("successor_net_usdt_after_all_costs"))
            if x.get("independent_quote_attestation_id") in (None,""):
                raise ValueError("SOURCE_PROVENANCE_IDENTIFIER_MISSING")
            if x.get("provider_receipt_id") in (None,""):
                raise ValueError("PROVIDER_RECEIPT_MISSING")
            if x.get("symbol_group_id")!=sym:
                raise ValueError("SYMBOL_CLUSTER_MISMATCH")
            delta=float(successor-baseline)
            observed.add(key)
            grouped_symbol[sym].append(delta)
            grouped_day[day].append(delta)
        except (ValueError,TypeError,AttributeError,KeyError) as e:
            rejected[str(e)]+=1

    total=sum(map(len,grouped_symbol.values()))
    result.update(
        accepted_forward_events=total,rejected_events=sum(rejected.values()),
        rejection_reasons=dict(sorted(rejected.items())),
        symbol_clusters=len(grouped_symbol),utc_day_clusters=len(grouped_day),
    )
    if (total<MIN_CANDIDATES or len(grouped_symbol)<MIN_SYMBOL_CLUSTERS
            or len(grouped_day)<MIN_UTC_DAY_CLUSTERS):
        result.update(status="BLOCKED_INSUFFICIENT_INDEPENDENT_FORWARD_EVIDENCE",
                      required_candidates=MIN_CANDIDATES,
                      required_symbols=MIN_SYMBOL_CLUSTERS,
                      required_days=MIN_UTC_DAY_CLUSTERS)
        return result
    # Equal-weighted clusters, NOT each correlated trade counted independently.
    def lower_bound(groups):
        means=[sum(samples)/len(samples) for samples in groups.values()]
        mean=sum(means)/len(means)
        stderr=stdev(means)/sqrt(len(means))
        return mean,mean-1.96*stderr
    symbol_mean,symbol_lcb=lower_bound(grouped_symbol)
    day_mean,day_lcb=lower_bound(grouped_day)
    result.update(symbol_equal_mean_delta=symbol_mean,
                  symbol_equal_95_lcb=symbol_lcb,
                  day_equal_mean_delta=day_mean,
                  day_equal_95_lcb=day_lcb)
    if min(symbol_lcb,day_lcb)<=0:
        result.update(status="REJECTED_NONPOSITIVE_INDEPENDENCE_ADJUSTED_LCB")
    else:
        result.update(status="NUMERIC_RESEARCH_GATE_ONLY_INDEPENDENT_APPROVAL_REQUIRED")
    # This function categorically lacks scientific authorization authority.
    return result
