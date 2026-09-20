-- Alpha Hunter readiness score compatibility audit v0.1
--
-- Purpose:
--   Audit whether the current production EXECUTION_SCORE and EARLY_TIMING gates
--   can coexist in observed data, and distinguish missing open-interest history
--   from genuinely weak open-interest behaviour.
--
-- This is observational/audit-only. It does not change any threshold, score
-- weight, candidate classification, trade permission, or execution path.

create or replace view public.alpha_hunter_readiness_score_compatibility_v01
with (security_invoker=true,security_barrier=true)
as
with observations as (
  select
    s.collected_at_utc,
    item->>'symbol' as symbol,
    nullif(item->>'behaviour_score','')::double precision as behaviour_score,
    upper(coalesce(item->>'opportunity_timing','UNAVAILABLE')) as opportunity_timing,
    upper(coalesce(item->>'market_phase','UNAVAILABLE')) as market_phase,
    nullif(item->>'previous_behaviour_score','')::double precision as previous_behaviour_score,
    nullif(item->>'open_interest_change_pct','')::double precision as open_interest_change_pct,
    nullif(
      item->'behaviour'->'components'->>'open_interest',
      ''
    )::double precision as open_interest_component,
    nullif(
      item->'execution_setup'->>'rr',
      ''
    )::double precision as execution_rr,
    nullif(
      item->'execution_setup'->>'direction',
      ''
    ) as execution_direction,
    coalesce((item->>'trade_permission')::boolean,false) as trade_permission
  from public.alpha_hunter_snapshots s
  cross join lateral jsonb_array_elements(
    coalesce(s.payload->'symbols','[]'::jsonb)
  ) item
  where s.collected_at_utc >= now()-interval '7 days'
    and item ? 'symbol'
    and not (item ? 'error')
),
timing_rollup as (
  select
    opportunity_timing,
    count(*)::bigint as observations,
    count(*) filter(
      where previous_behaviour_score is null
    )::bigint as no_previous_selected_observation,
    count(*) filter(
      where open_interest_change_pct is null
    )::bigint as oi_change_missing,
    count(*) filter(
      where coalesce(open_interest_component,0)=0
    )::bigint as oi_component_zero,
    min(behaviour_score) as min_score,
    percentile_cont(0.5) within group(order by behaviour_score) as median_score,
    percentile_cont(0.9) within group(order by behaviour_score) as p90_score,
    max(behaviour_score) as max_score,
    count(*) filter(
      where behaviour_score>=7.5
    )::bigint as score_ge_7_5,
    count(*) filter(
      where behaviour_score>=7.5
        and opportunity_timing='EARLY'
    )::bigint as joint_score_and_early,
    count(*) filter(
      where behaviour_score>=7.5
        and opportunity_timing='EARLY'
        and market_phase in ('RECOVERY','IGNITION')
    )::bigint as joint_score_early_eligible_phase,
    count(*) filter(
      where behaviour_score>=7.5
        and opportunity_timing='EARLY'
        and market_phase in ('RECOVERY','IGNITION')
        and execution_direction is not null
    )::bigint as joint_score_early_phase_direction,
    count(*) filter(where trade_permission)::bigint
      as trade_permission_observations
  from observations
  where behaviour_score is not null
  group by opportunity_timing
)
select
  opportunity_timing,
  observations,
  no_previous_selected_observation,
  oi_change_missing,
  oi_component_zero,
  min_score,
  median_score,
  p90_score,
  max_score,
  score_ge_7_5,
  joint_score_and_early,
  joint_score_early_eligible_phase,
  joint_score_early_phase_direction,
  trade_permission_observations,
  7.5::double precision as reference_execution_score,
  'EARLY'::text as reference_required_timing,
  case
    when opportunity_timing='EARLY' and score_ge_7_5=0
      then 'JOINT_GATE_UNREACHED_IN_OBSERVED_7D_COHORT'
    else 'OBSERVED_OR_NOT_APPLICABLE'
  end as compatibility_status,
  false as threshold_changed,
  false as trade_permission_granted_by_audit,
  'OBSERVATIONAL_AUDIT_ONLY'::text as scientific_role,
  true as shadow_only,
  false as trade_permission
from timing_rollup
order by
  case opportunity_timing
    when 'EARLY' then 1
    when 'FAIR' then 2
    when 'LATE' then 3
    else 4
  end,
  opportunity_timing;


create or replace view public.alpha_hunter_oi_score_coverage_v01
with (security_invoker=true,security_barrier=true)
as
with observations as (
  select
    s.collected_at_utc,
    item->>'symbol' as symbol,
    nullif(item->>'behaviour_score','')::double precision as behaviour_score,
    upper(coalesce(item->>'opportunity_timing','UNAVAILABLE')) as opportunity_timing,
    nullif(item->>'previous_behaviour_score','')::double precision as previous_behaviour_score,
    nullif(item->>'open_interest_change_pct','')::double precision as open_interest_change_pct,
    nullif(
      item->'behaviour'->'components'->>'open_interest',
      ''
    )::double precision as open_interest_component
  from public.alpha_hunter_snapshots s
  cross join lateral jsonb_array_elements(
    coalesce(s.payload->'symbols','[]'::jsonb)
  ) item
  where s.collected_at_utc >= now()-interval '7 days'
    and item ? 'symbol'
    and not (item ? 'error')
)
select
  case
    when previous_behaviour_score is null
      then 'NO_PREVIOUS_SELECTED_OBSERVATION'
    else 'HAS_PREVIOUS_SELECTED_OBSERVATION'
  end as previous_observation_status,
  count(*)::bigint as observations,
  count(*) filter(
    where open_interest_change_pct is null
  )::bigint as oi_change_missing,
  count(*) filter(
    where coalesce(open_interest_component,0)=0
  )::bigint as oi_component_zero,
  avg(open_interest_component) as mean_oi_component,
  percentile_cont(0.5) within group(order by open_interest_component)
    as median_oi_component,
  percentile_cont(0.9) within group(order by open_interest_component)
    as p90_oi_component,
  avg(behaviour_score) as mean_behaviour_score,
  percentile_cont(0.5) within group(order by behaviour_score)
    as median_behaviour_score,
  percentile_cont(0.9) within group(order by behaviour_score)
    as p90_behaviour_score,
  count(*) filter(where behaviour_score>=7.5)::bigint
    as score_ge_7_5,
  false as score_weight_changed,
  false as threshold_changed,
  'MISSING_OI_IS_CURRENTLY_SCORED_AS_ZERO_IN_PRODUCTION'::text
    as production_semantics,
  'AUDIT_ONLY_DO_NOT_REWEIGHT_FROM_THIS_VIEW'::text
    as claim_ceiling,
  true as shadow_only,
  false as trade_permission
from observations
where behaviour_score is not null
group by 1
order by 1;


revoke all on public.alpha_hunter_readiness_score_compatibility_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_oi_score_coverage_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_readiness_score_compatibility_v01
  to service_role;
grant select on public.alpha_hunter_oi_score_coverage_v01
  to service_role;
