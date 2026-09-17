-- Alpha Hunter recovered-geometry forward science view v0.2
-- Read-only prospective exploratory evaluation for the v0.2.2 Money Entry scope-aligned geometry cohort.
-- Existing v0.1 view remains immutable/auditable. No execution authority or threshold derivation.

create or replace view public.alpha_hunter_geometry_forward_observations_v02
with (security_invoker=true)
as
with geometry as (
  select
    g.*,
    case when g.explicit_entry is not null and g.explicit_entry>0 and g.research_stop is not null
      then abs(g.explicit_entry-g.research_stop)/g.explicit_entry*100.0 end as research_stop_distance_pct_calc,
    case when g.explicit_entry is not null and g.explicit_entry>0 and g.research_target is not null
      then abs(g.research_target-g.explicit_entry)/g.explicit_entry*100.0 end as research_target_distance_pct_calc
  from public.alpha_hunter_geometry_diagnostics g
  where g.model_version='geometry-diagnostics-v0.2.2-money-entry-scope-aligned'
    and g.shadow_only=true
    and g.trade_permission=false
), bound as (
  select
    g.*,
    c.scorecard_id,
    c.candidate_at_utc as scorecard_candidate_at_utc,
    c.geometry_valid as scanner_geometry_valid,
    c.model_version as scorecard_model_version
  from geometry g
  left join lateral (
    select c.*
    from public.alpha_hunter_big_mover_money_scorecard_candidates c
    where c.run_id=g.run_id
      and c.symbol=g.symbol
      and c.direction=g.candidate_direction
      and c.shadow_only=true
      and c.trade_permission=false
    order by c.created_at desc
    limit 1
  ) c on true
), joined as (
  select
    b.*,
    o.horizon_hours,
    o.horizon_due_at_utc,
    o.evaluation_status,
    o.evaluated_at_utc,
    o.mfe_pct,
    o.mae_pct,
    o.direction_adjusted_close_return_pct,
    o.candidate_path_outcome as scanner_candidate_path_outcome,
    o.realistic_net_r,
    o.realistic_net_r_status
  from bound b
  left join public.alpha_hunter_big_mover_money_scorecard_outcomes o
    on o.scorecard_id=b.scorecard_id
   and o.shadow_only=true
   and o.trade_permission=false
)
select
  j.diagnostic_id,
  j.run_id,
  j.source_signal_id,
  j.captured_at_utc,
  j.symbol,
  j.candidate_direction,
  j.scanner_direction,
  j.classification as geometry_classification,
  j.explicit_entry as research_entry,
  j.research_stop,
  j.research_target,
  j.research_rr,
  j.research_stop_distance_pct_calc as research_stop_distance_pct,
  j.research_target_distance_pct_calc as research_target_distance_pct,
  j.scorecard_id,
  (j.scorecard_id is not null) as scorecard_bound,
  j.scorecard_candidate_at_utc,
  j.scanner_geometry_valid,
  j.scorecard_model_version,
  j.horizon_hours,
  j.horizon_due_at_utc,
  j.evaluation_status,
  j.evaluated_at_utc,
  j.mfe_pct,
  j.mae_pct,
  j.direction_adjusted_close_return_pct,
  j.realistic_net_r,
  j.realistic_net_r_status,
  case
    when j.evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')
      and j.research_geometry_recoverable is true
      and j.mae_pct is not null
      and j.research_stop_distance_pct_calc is not null
    then j.mae_pct >= j.research_stop_distance_pct_calc
  end as research_stop_touched,
  case
    when j.evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')
      and j.research_geometry_recoverable is true
      and j.mfe_pct is not null
      and j.research_target_distance_pct_calc is not null
    then j.mfe_pct >= j.research_target_distance_pct_calc
  end as research_target_touched,
  case
    when j.scorecard_id is null then 'SCORECARD_UNAVAILABLE'
    when j.horizon_hours is null then 'OUTCOME_ROW_UNAVAILABLE'
    when j.evaluation_status in ('PENDING','RETRYABLE_ERROR') then 'OUTCOME_PENDING'
    when j.evaluation_status not in ('EVALUATED','AMBIGUOUS_INTRABAR') then 'OUTCOME_DATA_INSUFFICIENT'
    when j.research_geometry_recoverable is not true then 'GEOMETRY_NOT_RECOVERABLE'
    when j.mae_pct is null or j.mfe_pct is null
      or j.research_stop_distance_pct_calc is null or j.research_target_distance_pct_calc is null
      then 'PATH_DATA_INCOMPLETE'
    when j.mae_pct >= j.research_stop_distance_pct_calc
      and j.mfe_pct >= j.research_target_distance_pct_calc
      then 'BOTH_TOUCHED_PATH_ORDER_UNKNOWN'
    when j.mae_pct >= j.research_stop_distance_pct_calc then 'STOP_TOUCHED_ONLY'
    when j.mfe_pct >= j.research_target_distance_pct_calc then 'TARGET_TOUCHED_ONLY'
    else 'NEITHER_TOUCHED'
  end as research_geometry_path_class,
  'EXPLORATORY_PROSPECTIVE'::text as scientific_role,
  'MFE_MAE_TOUCH_TEST_REUSES_EXISTING_SCORECARD; BOTH_TOUCHED_HAS_UNKNOWN_ORDER'::text as path_method,
  false as exact_research_fill_claim_permitted,
  false as confirmatory_claim_permitted,
  false as threshold_derivation_permitted,
  false as t0_authorized,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission
from joined j;

revoke all on public.alpha_hunter_geometry_forward_observations_v02 from public,anon,authenticated;
grant select on public.alpha_hunter_geometry_forward_observations_v02 to service_role;

create or replace view public.alpha_hunter_geometry_forward_status_v02
with (security_invoker=true)
as
with base as (
  select * from public.alpha_hunter_geometry_forward_observations_v02
), keys as (
  select
    count(distinct diagnostic_id)::bigint as geometry_observations,
    count(distinct diagnostic_id) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE')::bigint as research_recoverable_observations,
    count(distinct diagnostic_id) filter (where scorecard_bound)::bigint as scorecard_bound_observations,
    count(distinct diagnostic_id) filter (where not scorecard_bound)::bigint as scorecard_unavailable_observations
  from base
), h as (
  select
    horizon_hours,
    count(*) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE')::bigint as outcome_rows,
    count(*) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE' and evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR'))::bigint as matured,
    count(*) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE' and research_geometry_path_class='TARGET_TOUCHED_ONLY')::bigint as target_only,
    count(*) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE' and research_geometry_path_class='STOP_TOUCHED_ONLY')::bigint as stop_only,
    count(*) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE' and research_geometry_path_class='BOTH_TOUCHED_PATH_ORDER_UNKNOWN')::bigint as both_touched_unknown_order,
    count(*) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE' and research_geometry_path_class='NEITHER_TOUCHED')::bigint as neither_touched,
    avg(direction_adjusted_close_return_pct) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE' and evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')) as avg_direction_adjusted_close_return_pct,
    avg(mfe_pct) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE' and evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')) as avg_mfe_pct,
    avg(mae_pct) filter (where geometry_classification='RESEARCH_SR_GEOMETRY_RECOVERABLE' and evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')) as avg_mae_pct,
    max(evaluated_at_utc) as latest_evaluated_at_utc
  from base
  where horizon_hours in (1,4,12,24)
  group by horizon_hours
)
select
  h.horizon_hours,
  k.geometry_observations,
  k.research_recoverable_observations,
  k.scorecard_bound_observations,
  k.scorecard_unavailable_observations,
  h.outcome_rows,
  h.matured,
  h.target_only,
  h.stop_only,
  h.both_touched_unknown_order,
  h.neither_touched,
  h.avg_direction_adjusted_close_return_pct,
  h.avg_mfe_pct,
  h.avg_mae_pct,
  h.latest_evaluated_at_utc,
  'EXPLORATORY_PROSPECTIVE'::text as scientific_state,
  'INSUFFICIENT_FOR_CONFIRMATORY_GEOMETRY_CLAIM'::text as scientific_conclusion,
  'Allow genuinely new 1H/4H/12H/24H outcomes to mature. Do not promote research geometry into T0; if descriptive path survivability is promising, preregister a separate future holdout excluding these observations.'::text as next_gate,
  false as confirmatory_claim_permitted,
  false as threshold_derivation_permitted,
  false as t0_authorized,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission
from h cross join keys k
order by h.horizon_hours;

revoke all on public.alpha_hunter_geometry_forward_status_v02 from public,anon,authenticated;
grant select on public.alpha_hunter_geometry_forward_status_v02 to service_role;
