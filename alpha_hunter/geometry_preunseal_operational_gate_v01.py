"""Pure, pre-unseal geometry holdout *operational metadata* acceptance gate.

Synthetic unit fixtures only; caller must separately verify SQL source.
Never reads sealed outcomes, never invokes exchange/network/database or alters a
frozen scientific spec. Failure-event retries are NOT independent candidates,
and a failed attempt does NOT establish an absent sealed outcome.
"""
from __future__ import annotations

from typing import Mapping,Any

SPEC = "AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01"
END_AT_UTC = "2026-11-19T00:29:06.132018Z"


def review_capture_metadata(summary: Mapping[str,Any]) -> dict[str,Any]:
    """Analyze aggregate, non-outcome metadata without scientific authority."""
    result=dict(
        spec_id=SPEC,
        capture_research_only=True,
        primary_outcome_access_permitted=False,
        original_exclusions_unchanged=True,
        missing_outcomes_imputed=0,
        historical_trade_reclassified=0,
        cohort_spec_change_permitted=False,
        overwrite_existing_outcomes_permitted=False,
        promotion_permitted=False,
        trading_permission=False,
        independent_review_approved=False,
        status="BLOCKED_MISSING_OR_INVALID_METADATA",
        reasons=[],
    )
    numbers=(
        "captured", "eligible", "excluded", "group_quality_mismatch",
        "authority_violation", "source_after_decision",
        "source_hash_metadata_missing",
        "eligible_nonascii_symbols", "nonascii_with_logged_failure",
        "nonascii_without_logged_failure", "distinct_failed_bindings",
        "failed_attempt_events", "same_source_opposing_direction_pairs",
        "unexpected_source_reuse",
    )
    try:
        if summary.get("spec_id")!=SPEC:
            raise ValueError("SPEC_MISMATCH")
        for name in numbers:
            val=summary[name]
            if isinstance(val,bool) or not isinstance(val,int) or val<0:
                raise ValueError("INVALID_COUNTER_"+name)
        if summary.get("primary_results_exposed") is not False:
            raise ValueError("SEALED_PRIMARY_RESULTS_EXPOSED_OR_UNKNOWN")
        if summary.get("scientific_conclusion")!="NONE":
            raise ValueError("UNAUTHORIZED_SCIENTIFIC_CONCLUSION")
        if summary.get("trade_permission") is not False:
            raise ValueError("UNAUTHORIZED_TRADE_PERMISSION")
        if summary.get("production_promotion_permitted") is not False:
            raise ValueError("UNAUTHORIZED_PRODUCTION_PROMOTION")
        if summary["eligible"] + summary["excluded"] != summary["captured"]:
            raise ValueError("CAPTURE_DENOMINATOR_MISMATCH")
        if (summary["eligible_nonascii_symbols"]!=
            summary["nonascii_with_logged_failure"]+
            summary["nonascii_without_logged_failure"]):
            raise ValueError("NONASCII_BINDING_COUNT_MISMATCH")
        if summary["distinct_failed_bindings"]>summary["eligible"]:
            raise ValueError("FAILED_BINDINGS_EXCEED_COHORT")
        if summary["nonascii_with_logged_failure"]>summary["distinct_failed_bindings"]:
            raise ValueError("FAILURES_DONT_RECONCILE")
        if summary["failed_attempt_events"]<summary["distinct_failed_bindings"]:
            raise ValueError("ATTEMPTS_BELOW_DISTINCT_FAILURES")
        if any(summary[x] for x in ("group_quality_mismatch",
              "authority_violation","source_after_decision",
              "source_hash_metadata_missing","unexpected_source_reuse")):
            raise ValueError("OPERATIONAL_CUSTODY_OR_AUTHORITY_BREACH")
        result.update(
            observed_eligible_count=summary["eligible"],
            eligible_nonascii_symbols=summary["eligible_nonascii_symbols"],
            nonascii_with_logged_failure=summary["nonascii_with_logged_failure"],
            nonascii_without_logged_failure=summary["nonascii_without_logged_failure"],
            distinct_failed_bindings=summary["distinct_failed_bindings"],
            failed_attempt_events=summary["failed_attempt_events"],
            same_source_opposing_direction_pairs=summary[
                "same_source_opposing_direction_pairs"],
            missing_outcome_count="UNKNOWN_NOT_RETRIEVED",
        )
        if summary["eligible_nonascii_symbols"]>0:
            result["reasons"].append("SYSTEMATIC_SYMBOL_REJECTION_RISK")
        if summary["failed_attempt_events"]>0:
            result["reasons"].append("EVALUATOR_FAILURE_CENSORING_REVIEW_REQUIRED")
        if summary["same_source_opposing_direction_pairs"]>0:
            result["reasons"].append("PAIRED_DIRECTION_SOURCE_DEPENDENCE")
        if result["reasons"]:
            result["status"]="BLOCKED_FOR_INDEPENDENT_PREUNSEAL_REVIEW"
        else:
            result["status"]="COLLECTING_SEALED_NO_SCIENTIFIC_PROMOTION"
    except (KeyError,TypeError,ValueError) as ex:
        result["reasons"]=[str(ex)]
    return result
