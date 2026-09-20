-- Alpha Hunter geometry feasibility decomposition v0.1
--
-- Purpose:
--   Diagnose why the unchanged 5R requirement fails at decision time without
--   changing production thresholds, stop/target logic, direction logic, or
--   trade permission.
--
-- This is contemporaneous/non-outcome evidence only.
-- It does not read sealed holdout outcomes and cannot promote production logic.

create or replace view public.alpha_hunter_geometry_feasibility_observations_v01
with (security_invoker=true,security_barrier=true)
as
with base as (
  select
    g.diagnostic_id,
    g.run_id,
    g.source_signal_id,
    g.captured_at_utc,
    g.symbol,
    g.candidate_direction,
    g.scanner_direction,
    g.explicit_geometry_complete,
    g.classification,
    g.explicit_entry as entry_price,
    g.research_stop as stop_price,
    g.research_target as target_price,
    g.research_rr as current_rr,
    g.evidence->>'opportunity_timing' as opportunity_timing,
    g.evidence->>'market_phase' as market_phase,
    g.evidence->>'direction_source' as direction_source,
    nullif(g.evidence->>'observed_atr_1h_pct','')::double precision
      as atr_1h_pct,
    nullif(g.evidence->>'observed_atr_15m_pct','')::double precision
      as atr_15m_pct,
    nullif(g.evidence->>'observed_spread_pct','')::double precision
      as spread_pct,
    g.model_version as source_model_version
  from public.alpha_hunter_geometry_diagnostics g
  where g.research_geometry_recoverable=true
    and g.explicit_entry>0
    and g.research_stop>0
    and g.research_target>0
    and g.candidate_direction in ('LONG','SHORT')
),
calc as (
  select
    b.*,
    case
      when b.candidate_direction='LONG'
      then b.stop_price<b.entry_price
        and b.entry_price<b.target_price
      when b.candidate_direction='SHORT'
      then b.target_price<b.entry_price
        and b.entry_price<b.stop_price
      else false
    end as orientation_valid,
    abs(b.entry_price-b.stop_price) as risk_distance,
    abs(b.target_price-b.entry_price) as reward_distance,
    abs(b.target_price-b.stop_price) as structural_span,
    100.0*abs(b.entry_price-b.stop_price)/b.entry_price as risk_pct,
    100.0*abs(b.target_price-b.entry_price)/b.entry_price as reward_pct,
    case
      when abs(b.target_price-b.stop_price)>0
      then abs(b.entry_price-b.stop_price)
        /abs(b.target_price-b.stop_price)
    end as range_fraction_from_stop_side,
    case
      when b.candidate_direction='LONG'
      then (b.target_price+5.0*b.stop_price)/6.0
      when b.candidate_direction='SHORT'
      then (5.0*b.stop_price+b.target_price)/6.0
    end as entry_boundary_for_5r
  from base b
),
decomposed as (
  select
    c.*,
    1.0/6.0 as max_range_fraction_for_5r,
    case
      when c.candidate_direction='LONG'
      then greatest(0.0,c.entry_price-c.entry_boundary_for_5r)
      when c.candidate_direction='SHORT'
      then greatest(0.0,c.entry_boundary_for_5r-c.entry_price)
    end as adverse_entry_gap_to_5r,
    c.reward_distance/5.0 as max_risk_distance_for_5r_current_target,
    5.0*c.risk_distance as required_reward_distance_for_5r_current_stop
  from calc c
)
select
  d.diagnostic_id,
  d.run_id,
  d.source_signal_id,
  d.captured_at_utc,
  d.symbol,
  d.candidate_direction,
  d.scanner_direction,
  (d.scanner_direction=d.candidate_direction)
    as scanner_direction_aligned,
  d.explicit_geometry_complete,
  d.classification,
  d.opportunity_timing,
  d.market_phase,
  d.direction_source,
  d.entry_price,
  d.stop_price,
  d.target_price,
  d.current_rr,
  d.orientation_valid,
  d.risk_distance,
  d.reward_distance,
  d.structural_span,
  d.risk_pct,
  d.reward_pct,
  d.range_fraction_from_stop_side,
  d.max_range_fraction_for_5r,
  d.entry_boundary_for_5r,
  d.adverse_entry_gap_to_5r,
  100.0*d.adverse_entry_gap_to_5r/d.entry_price
    as adverse_entry_gap_to_5r_pct,
  d.max_risk_distance_for_5r_current_target,
  100.0*greatest(
    0.0,
    d.risk_distance-d.max_risk_distance_for_5r_current_target
  )/d.entry_price as stop_tightening_needed_pct,
  d.required_reward_distance_for_5r_current_stop,
  100.0*greatest(
    0.0,
    d.required_reward_distance_for_5r_current_stop-d.reward_distance
  )/d.entry_price as target_extension_needed_pct,
  case
    when d.atr_1h_pct>0
    then (
      100.0*greatest(
        0.0,
        d.risk_distance-d.max_risk_distance_for_5r_current_target
      )/d.entry_price
    )/d.atr_1h_pct
  end as stop_tightening_needed_atr1h,
  case
    when d.atr_1h_pct>0
    then (
      100.0*greatest(
        0.0,
        d.required_reward_distance_for_5r_current_stop-d.reward_distance
      )/d.entry_price
    )/d.atr_1h_pct
  end as target_extension_needed_atr1h,
  d.atr_1h_pct,
  d.atr_15m_pct,
  d.spread_pct,
  case
    when d.orientation_valid is not true
      then 'GEOMETRY_ORIENTATION_INVALID'
    when d.current_rr>=5.0
      then 'CURRENT_GEOMETRY_RR5_FEASIBLE'
    when d.range_fraction_from_stop_side>1.0/6.0
      then 'ENTRY_BEYOND_RR5_RANGE_BOUNDARY'
    else 'RR5_INFEASIBLE_OTHER'
  end as feasibility_class,
  'DECISION_TIME_GEOMETRY_DIAGNOSTIC_ONLY'::text as scientific_role,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  false as outcome_evidence_used,
  false as sealed_holdout_outcome_read,
  true as shadow_only,
  false as trade_permission,
  'geometry-feasibility-decomposition-v0.1'::text as model_version,
  d.source_model_version
from decomposed d;


create or replace view public.alpha_hunter_geometry_feasibility_status_v01
with (security_invoker=true,security_barrier=true)
as
with cohorts as (
  select
    'ALL_SHADOW_GEOMETRY'::text as cohort,
    o.*
  from public.alpha_hunter_geometry_feasibility_observations_v01 o

  union all

  select
    'SCANNER_DIRECTION_ALIGNED'::text as cohort,
    o.*
  from public.alpha_hunter_geometry_feasibility_observations_v01 o
  where o.scanner_direction_aligned=true

  union all

  select
    'EXPLICIT_EXECUTION_GEOMETRY'::text as cohort,
    o.*
  from public.alpha_hunter_geometry_feasibility_observations_v01 o
  where o.explicit_geometry_complete=true
)
select
  cohort,
  count(*)::bigint as observations,
  count(*) filter(
    where feasibility_class='CURRENT_GEOMETRY_RR5_FEASIBLE'
  )::bigint as rr5_feasible_observations,
  case
    when count(*)>0
    then round(
      100.0*count(*) filter(
        where feasibility_class='CURRENT_GEOMETRY_RR5_FEASIBLE'
      )/count(*)::numeric,
      2
    )
  end as rr5_feasible_pct,
  percentile_cont(0.5) within group(order by current_rr)
    as median_current_rr,
  percentile_cont(0.9) within group(order by current_rr)
    as p90_current_rr,
  max(current_rr) as max_current_rr,
  100.0*percentile_cont(0.5) within group(
    order by range_fraction_from_stop_side
  ) as median_range_consumed_pct,
  percentile_cont(0.5) within group(
    order by adverse_entry_gap_to_5r_pct
  ) as median_entry_gap_to_5r_pct,
  percentile_cont(0.5) within group(
    order by risk_pct
  ) as median_risk_pct,
  percentile_cont(0.5) within group(
    order by reward_pct
  ) as median_reward_pct,
  percentile_cont(0.5) within group(
    order by stop_tightening_needed_pct
  ) as median_stop_tightening_needed_pct,
  percentile_cont(0.5) within group(
    order by target_extension_needed_pct
  ) as median_target_extension_needed_pct,
  percentile_cont(0.5) within group(
    order by stop_tightening_needed_atr1h
  ) as median_stop_tightening_needed_atr1h,
  percentile_cont(0.5) within group(
    order by target_extension_needed_atr1h
  ) as median_target_extension_needed_atr1h,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  false as outcome_evidence_used,
  false as sealed_holdout_outcome_read,
  true as shadow_only,
  false as trade_permission
from cohorts
where orientation_valid=true
group by cohort;


revoke all on public.alpha_hunter_geometry_feasibility_observations_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_geometry_feasibility_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_geometry_feasibility_observations_v01
  to service_role;
grant select on public.alpha_hunter_geometry_feasibility_status_v01
  to service_role;
