-- Alpha Hunter participation forward science view v0.1
-- Read-only prospective exploratory reporting over participation diagnostics + signal outcomes.
-- This is NOT a confirmatory holdout, NOT a threshold-derivation surface, and NOT production authority.

create or replace view public.alpha_hunter_participation_forward_observations_v01
with (security_invoker=true)
as
select
  d.diagnostic_id,
  d.run_id,
  d.source_signal_id,
  d.source_bridge_id,
  d.captured_at_utc,
  d.symbol,
  d.candidate_direction,
  d.classification,
  d.scanner_participation_confirmed,
  d.scanner_participation_emerging,
  d.volume_state_15m,
  d.volume_ratio_15m,
  d.volume_state_1h,
  d.volume_ratio_1h,
  d.volume_state_4h,
  d.volume_ratio_4h,
  d.behaviour_volume_ratio,
  d.market_phase,
  d.opportunity_timing,
  d.liquidity_pass,
  o.horizon_hours,
  o.evaluated_at_utc,
  o.direction_adjusted_return_pct,
  o.target_hit,
  o.stop_hit,
  o.outcome_class,
  'EXPLORATORY_PROSPECTIVE'::text as scientific_role,
  false as confirmatory_claim_permitted,
  false as threshold_derivation_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission
from public.alpha_hunter_participation_diagnostics d
left join public.alpha_hunter_signal_outcomes o
  on o.signal_id=d.source_signal_id
where d.model_version='participation-diagnostics-v0.1'
  and d.shadow_only=true
  and d.trade_permission=false;

revoke all on public.alpha_hunter_participation_forward_observations_v01 from public,anon,authenticated;
grant select on public.alpha_hunter_participation_forward_observations_v01 to service_role;

create or replace view public.alpha_hunter_participation_forward_status_v01
with (security_invoker=true)
as
with base as (
  select *
  from public.alpha_hunter_participation_forward_observations_v01
), diagnostics as (
  select
    classification,
    count(distinct diagnostic_id)::bigint as diagnostic_n,
    count(distinct source_signal_id)::bigint as source_signal_n
  from base
  group by classification
), matured as (
  select
    classification,
    count(*) filter (where horizon_hours=1)::bigint as matured_1h,
    count(*) filter (where horizon_hours=4)::bigint as matured_4h,
    count(*) filter (where horizon_hours=12)::bigint as matured_12h,
    count(*) filter (where horizon_hours=24)::bigint as matured_24h,
    avg(direction_adjusted_return_pct) filter (where horizon_hours=1) as avg_dir_adj_return_1h,
    avg(direction_adjusted_return_pct) filter (where horizon_hours=4) as avg_dir_adj_return_4h,
    avg(direction_adjusted_return_pct) filter (where horizon_hours=12) as avg_dir_adj_return_12h,
    avg(direction_adjusted_return_pct) filter (where horizon_hours=24) as avg_dir_adj_return_24h,
    count(*) filter (where horizon_hours=1 and target_hit is true)::bigint as target_hits_1h,
    count(*) filter (where horizon_hours=1 and stop_hit is true)::bigint as stop_hits_1h,
    count(*) filter (where horizon_hours=4 and target_hit is true)::bigint as target_hits_4h,
    count(*) filter (where horizon_hours=4 and stop_hit is true)::bigint as stop_hits_4h,
    count(*) filter (where horizon_hours=12 and target_hit is true)::bigint as target_hits_12h,
    count(*) filter (where horizon_hours=12 and stop_hit is true)::bigint as stop_hits_12h,
    count(*) filter (where horizon_hours=24 and target_hit is true)::bigint as target_hits_24h,
    count(*) filter (where horizon_hours=24 and stop_hit is true)::bigint as stop_hits_24h,
    max(evaluated_at_utc) as latest_evaluated_at_utc
  from base
  where horizon_hours in (1,4,12,24)
  group by classification
)
select
  d.classification,
  d.diagnostic_n,
  d.source_signal_n,
  coalesce(m.matured_1h,0) as matured_1h,
  coalesce(m.matured_4h,0) as matured_4h,
  coalesce(m.matured_12h,0) as matured_12h,
  coalesce(m.matured_24h,0) as matured_24h,
  m.avg_dir_adj_return_1h,
  m.avg_dir_adj_return_4h,
  m.avg_dir_adj_return_12h,
  m.avg_dir_adj_return_24h,
  coalesce(m.target_hits_1h,0) as target_hits_1h,
  coalesce(m.stop_hits_1h,0) as stop_hits_1h,
  coalesce(m.target_hits_4h,0) as target_hits_4h,
  coalesce(m.stop_hits_4h,0) as stop_hits_4h,
  coalesce(m.target_hits_12h,0) as target_hits_12h,
  coalesce(m.stop_hits_12h,0) as stop_hits_12h,
  coalesce(m.target_hits_24h,0) as target_hits_24h,
  coalesce(m.stop_hits_24h,0) as stop_hits_24h,
  m.latest_evaluated_at_utc,
  'EXPLORATORY_PROSPECTIVE'::text as scientific_state,
  'NO_CONFIRMATORY_CLAIM_THIS_COHORT'::text as scientific_conclusion,
  'Use this cohort for feasibility/measurement only. Any participation threshold or causal/confirmatory claim requires a separately preregistered future holdout that excludes these observations.'::text as next_gate,
  false as confirmatory_claim_permitted,
  false as threshold_derivation_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission
from diagnostics d
left join matured m using(classification)
order by d.classification;

revoke all on public.alpha_hunter_participation_forward_status_v01 from public,anon,authenticated;
grant select on public.alpha_hunter_participation_forward_status_v01 to service_role;
