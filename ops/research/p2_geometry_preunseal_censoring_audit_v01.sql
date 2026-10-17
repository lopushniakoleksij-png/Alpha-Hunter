-- READ-ONLY pre-unseal quality review of P2 geometry capture.
-- A scientific protocol inspection, NEVER a migration or a reclassification.
-- Absolutely DO NOT SELECT from any sealed primary outcome table.
-- Original active evaluator and cohort fingerprints stay unchanged.

-- Pre-registered aggregate: source data, sample gate and outcome seal.
select spec_id,scientific_status,registered_at_utc,collection_ends_at_utc,
       captured,eligible,excluded,symbols,utc_days,long_eligible,short_eligible,
       capture_sample_gate_met,capture_failures,
       scientific_conclusion,trade_permission,production_promotion_permitted
from public.alpha_hunter_geometry_holdout_status_v01;

-- Operational metadata ONLY; no variant-specific path/return outcomes.
select spec_id,sealed_rows,complete_binding_horizon_sets,evaluator_failure_events,
       latest_evaluated_at_utc,primary_results_exposed,evaluator_state,next_gate
from public.alpha_hunter_geometry_holdout_collection_status_v01;

-- Every binding is counted ONCE regardless of repeated evaluator attempts.
-- Failure presence does not prove that a sealed result was never recorded.
with failed_binding as (
  select distinct binding_id
  from public.alpha_hunter_geometry_holdout_evaluator_failures
  where spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
), eligible as (
  select b.binding_id,b.symbol,b.group_name,b.eligibility_reason,
         b.data_quality_ok,b.shadow_only,b.trade_permission,
         b.production_promotion_permitted,
         b.source_evidence_hash,b.source_schema_fingerprint,
         b.source_query_fingerprint,b.decision_available_at_utc,
         b.source_captured_at_utc,
         case when b.symbol ~ '^[A-Z0-9]+USDT$' then true else false end as ascii_symbol
  from public.alpha_hunter_geometry_holdout_bindings b
  where b.spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
)
select count(*) captured,count(*) filter(where group_name='ELIGIBLE') eligible,
       count(*) filter(where group_name='EXCLUDED') excluded,
       count(*) filter(where group_name='ELIGIBLE' and not ascii_symbol)
         eligible_symbols_rejected_by_evaluator,
       count(*) filter(where group_name='ELIGIBLE' and f.binding_id is not null)
         eligible_bindings_with_any_error,
       count(*) filter(where group_name='ELIGIBLE' and not ascii_symbol
                              and f.binding_id is not null)
         eligible_nonascii_with_logged_error,
       count(*) filter(where group_name='ELIGIBLE' and not ascii_symbol
                              and f.binding_id is null)
         eligible_nonascii_with_no_logged_error,
       count(*) filter(where (group_name='ELIGIBLE') is distinct from
                             (data_quality_ok is true)) group_quality_mismatch,
       count(*) filter(where source_evidence_hash is null
                            or source_schema_fingerprint is null
                            or source_query_fingerprint is null)
         source_hash_metadata_missing,
       count(*) filter(where source_captured_at_utc>decision_available_at_utc)
         source_after_decision,
       count(*) filter(where not coalesce(shadow_only,false)
                        or coalesce(trade_permission,false)
                        or coalesce(production_promotion_permitted,false))
         authority_violation
from eligible b left join failed_binding f on f.binding_id=b.binding_id;

-- Log failure attempts separately from the DISTINCT original bindings.
-- Both horizons must stay separate, and no failure is itself a win or loss.
select f.error_class,f.error_message,f.horizon_hours,
       count(*) attempts,count(distinct f.binding_id) distinct_bindings,
       min(f.failed_at_utc) first_failure,max(f.failed_at_utc) latest_failure
from public.alpha_hunter_geometry_holdout_evaluator_failures f
where f.spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
group by f.error_class,f.error_message,f.horizon_hours
order by attempts desc;

-- Censoring exposure by source symbol; count DISTINCT candidates, not retries.
select b.symbol,count(*) total_bindings,
       count(*) filter(where b.group_name='ELIGIBLE') eligible_bindings,
       count(*) filter(where b.group_name='EXCLUDED') excluded_bindings
from public.alpha_hunter_geometry_holdout_bindings b
where b.spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
  and b.symbol !~ '^[A-Z0-9]+USDT$'
group by b.symbol order by eligible_bindings desc;

-- Do not count paired LONG and SHORT from one source as independent evidence.
with grouped as (
 select source_signal_id,count(*) candidates,
        count(distinct symbol) symbols,count(distinct direction) directions
 from public.alpha_hunter_geometry_holdout_bindings
 where spec_id='AH-GEOMETRY-PROSPECTIVE-HOLDOUT-V01'
 group by source_signal_id
)
select count(*) distinct_sources,
       count(*) filter(where candidates=2 and symbols=1 and directions=2)
         paired_opposite_direction_sources,
       count(*) filter(where candidates>2 or symbols>1)
         unexpected_source_reuse
from grouped;
