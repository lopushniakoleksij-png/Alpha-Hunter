"""No-I/O P2 geometry evaluator throughput acceptance, never scientific verdict.

Operates only on aggregate, read-only operational metadata. In particular,
DO NOT read alpha_hunter_geometry_holdout_outcomes_sealed. This module does not
change cron, invoke evaluator, modify cohort or expose sealed results.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import Any, Mapping

SPEC="AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01"
FROZEN_END="2026-11-19T00:29:06.132018Z"
EXPECTED_SCHEDULE="38 */6 * * *"
EXPECTED_MAX_PER_RUN=40
HORIZONS=(12,24)


def audit_capacity(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Conservative lower bound on due but unfinished *binding/horizon* sets.

    Important: reported sealed complete sets are aggregate metadata; this
    does not determine WHICH bindings have results. The subtraction is thus
    a cohort-level lower bound, not a row-specific reconciliation or proof
    that a given sealed result is present/absent.
    """
    report=dict(
        spec_id=SPEC,
        status="METADATA_INSUFFICIENT",
        original_cohort_immutable=True,
        private_outcomes_queried=False,
        primary_results_exposed=False,
        independent_scientific_approval=False,
        independent_risk_approval=False,
        allowed_to_change_cron=False,
        allowed_to_run_evaluator=False,
        allowed_to_unseal=False,
        scientific_promotion_permitted=False,
        trade_permission=False,
        production_promotion_permitted=False,
        reasons=[],
    )
    try:
        if metadata.get("spec_id")!=SPEC:
            raise ValueError("FROZEN_SPEC_ID_MISMATCH")
        if metadata.get("collection_ends_at_utc")!=FROZEN_END:
            raise ValueError("COLLECTION_ENDPOINT_CHANGED")
        for k,expected in (
            ("primary_results_exposed",False),
            ("trade_permission",False),
            ("production_promotion_permitted",False),
            ("cron_active",True),
            ("max_40_in_sql",True),
        ):
            if metadata.get(k) is not expected:
                raise ValueError("SAFETY_OR_SCHEDULER_STATE_INVALID:"+k)
        if metadata.get("scientific_conclusion")!="NONE":
            raise ValueError("PREMATURE_SCIENTIFIC_CONCLUSION")
        if metadata.get("cron_schedule")!=EXPECTED_SCHEDULE:
            raise ValueError("CRON_SCHEDULE_DRIFT")
        if metadata.get("max_batch_per_run")!=EXPECTED_MAX_PER_RUN:
            raise ValueError("BATCH_LIMIT_DRIFT")
        if metadata.get("horizons_hours")!=list(HORIZONS):
            raise ValueError("HORIZON_OR_ENDPOINT_DRIFT")
        fields=(
            "eligible", "due_12h", "due_24h", "complete_horizon_sets",
            "sealed_rows", "eligible_added_last_7d", "evaluator_failure_events",
        )
        for k in fields:
            n=metadata[k]
            if isinstance(n,bool) or not isinstance(n,int) or n<0:
                raise ValueError("INVALID_COUNTER:"+k)
        elig=metadata["eligible"]
        due=metadata["due_12h"]+metadata["due_24h"]
        complete=metadata["complete_horizon_sets"]
        if metadata["due_12h"]>elig or metadata["due_24h"]>elig:
            raise ValueError("DUE_GREATER_THAN_ELIGIBLE")
        if complete>2*elig or complete>due:
            raise ValueError("SEALED_SET_COUNTER_INCONSISTENT")
        if metadata["sealed_rows"]!=4*complete:
            raise ValueError("INCOMPLETE_FOUR_VARIANT_HORIZON_SETS")
        if metadata["eligible_added_last_7d"]>elig:
            raise ValueError("RECENT_ELIGIBLE_EXCEEDS_COHORT")

        theoretical_runs_per_day=4  # parsed from frozen EXPECTED_SCHEDULE
        max_daily_sets=theoretical_runs_per_day*EXPECTED_MAX_PER_RUN
        new_sets_per_day=(
            Decimal(metadata["eligible_added_last_7d"])*Decimal(len(HORIZONS))
            /Decimal(7)
        )
        backlog_lower_bound=due-complete
        min_days_no_new_work=int(
            (Decimal(backlog_lower_bound)/Decimal(max_daily_sets))
            .to_integral_value(rounding=ROUND_CEILING)
        ) if backlog_lower_bound else 0
        report.update(
            due_binding_horizon_sets=due,
            complete_binding_horizon_sets=complete,
            apparent_overdue_set_deficit=backlog_lower_bound,
            lower_bound_note="AGGREGATE_ONLY_NOT_BINDING_LEVEL_OUTCOME_CHECK",
            theoretical_scheduled_daily_capacity=max_daily_sets,
            recent_7d_average_new_sets_per_day=str(new_sets_per_day),
            intake_minus_scheduled_capacity_per_day=str(
                new_sets_per_day-Decimal(max_daily_sets)),
            minimum_days_to_clear_existing_deficit_if_zero_new_arrivals=(
                min_days_no_new_work
            ),
            failed_attempt_events=metadata["evaluator_failure_events"],
            operational_approval_required=True,
        )
        if backlog_lower_bound:
            report["reasons"].append("DUE_SETS_EXCEED_AGGREGATE_COMPLETIONS")
        if new_sets_per_day>max_daily_sets:
            report["reasons"].append("RECENT_INTAKE_ABOVE_SCHEDULED_CAPACITY")
        if metadata["evaluator_failure_events"]>0:
            report["reasons"].append("EVALUATOR_FAILURES_REQUIRE_SEPARATE_REVIEW")
        report["status"]=(
            "BLOCKED_PREUNSEAL_CAPACITY_RISK"
            if report["reasons"]
            else "OBSERVATION_COUNTS_ONLY_NO_AUTHORITY_TO_UNSEAL"
        )
    except (KeyError,TypeError,ValueError) as exc:
        report["reasons"]=[str(exc)]
    return report
