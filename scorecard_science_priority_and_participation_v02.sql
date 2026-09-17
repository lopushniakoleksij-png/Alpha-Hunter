begin;

-- Keep one scorecard evaluator and the existing 80-row request cap. Only change
-- queue ordering so current clean prospective science is not starved behind
-- legacy backlog. Fail closed if the expected function shape has drifted.
do $patch$
declare
  v_def text;
  v_old text := $old$order by
      case when exists (
        select 1
        from public.alpha_hunter_early_mover_cohort e
        where e.scorecard_id = o.scorecard_id
          and e.capture_contract_version = 'prospective-early-mover-cohort-v0.2'
      ) then 0 else 1 end,
      o.horizon_due_at_utc,
      o.created_at
    limit 80$old$;
  v_new text := $new$order by
      case
        when exists (
          select 1
          from public.alpha_hunter_early_mover_cohort e
          where e.scorecard_id = o.scorecard_id
            and e.capture_contract_version = 'prospective-early-mover-cohort-v0.2'
        ) then 0
        when exists (
          select 1
          from public.alpha_hunter_geometry_diagnostics g
          where g.run_id = c.run_id
            and g.symbol = c.symbol
            and g.candidate_direction = c.direction
            and g.model_version = 'geometry-diagnostics-v0.2.2-money-entry-scope-aligned'
            and g.shadow_only = true
            and g.trade_permission = false
        ) or exists (
          select 1
          from public.alpha_hunter_participation_diagnostics d
          where d.source_bridge_id = c.source_bridge_id
            and d.run_id = c.run_id
            and d.symbol = c.symbol
            and d.candidate_direction = c.direction
            and d.model_version = 'participation-diagnostics-v0.1'
            and d.shadow_only = true
            and d.trade_permission = false
        ) then 1
        else 2
      end,
      o.horizon_due_at_utc,
      o.created_at
    limit 80$new$;
begin
  select pg_get_functiondef(p.oid)
    into v_def
  from pg_proc p
  join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='private'
    and p.proname='alpha_hunter_run_big_mover_money_scorecard'
    and pg_get_function_identity_arguments(p.oid)='';

  if v_def is null then
    raise exception 'expected scorecard evaluator not found';
  end if;
  if position(v_old in v_def)=0 then
    raise exception 'scorecard queue contract drifted; refusing patch';
  end if;

  v_def := replace(v_def,v_old,v_new);
  execute v_def;
end;
$patch$;

create or replace view public.alpha_hunter_participation_forward_observations_v02
with (security_invoker=true) as
with diagnostics as (
  select d.*
  from public.alpha_hunter_participation_diagnostics d
  where d.model_version='participation-diagnostics-v0.1'
    and d.shadow_only=true
    and d.trade_permission=false
), bound as (
  select d.*,
         c.scorecard_id,
         c.candidate_at_utc as scorecard_candidate_at_utc,
         c.model_version as scorecard_model_version
  from diagnostics d
  left join lateral (
    select c.scorecard_id,c.candidate_at_utc,c.model_version
    from public.alpha_hunter_big_mover_money_scorecard_candidates c
    where c.source_bridge_id=d.source_bridge_id
      and c.run_id=d.run_id
      and c.symbol=d.symbol
      and c.direction=d.candidate_direction
      and c.shadow_only=true
      and c.trade_permission=false
    order by c.created_at desc
    limit 1
  ) c on true
)
select
  b.diagnostic_id,b.run_id,b.source_signal_id,b.source_bridge_id,
  b.captured_at_utc,b.symbol,b.candidate_direction,b.classification,
  b.scanner_participation_confirmed,b.scanner_participation_emerging,
  b.volume_state_15m,b.volume_ratio_15m,b.volume_state_1h,b.volume_ratio_1h,
  b.volume_state_4h,b.volume_ratio_4h,b.behaviour_volume_ratio,b.market_phase,
  b.opportunity_timing,b.liquidity_pass,
  b.scorecard_id,(b.scorecard_id is not null) as scorecard_bound,
  b.scorecard_candidate_at_utc,b.scorecard_model_version,
  o.horizon_hours,o.horizon_due_at_utc,o.evaluation_status,o.evaluated_at_utc,
  o.direction_adjusted_close_return_pct,o.mfe_pct,o.mae_pct,o.target_hit,o.stop_hit,
  o.path_resolution,o.candidate_path_outcome,o.realistic_net_r,o.realistic_net_r_status,
  'EXPLORATORY_PROSPECTIVE'::text as scientific_role,
  false as confirmatory_claim_permitted,
  false as threshold_derivation_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission
from bound b
left join public.alpha_hunter_big_mover_money_scorecard_outcomes o
  on o.scorecard_id=b.scorecard_id
 and o.shadow_only=true
 and o.trade_permission=false;

create or replace view public.alpha_hunter_participation_forward_status_v02
with (security_invoker=true) as
with base as (
  select * from public.alpha_hunter_participation_forward_observations_v02
), keys as (
  select classification,
         count(distinct diagnostic_id) as diagnostic_n,
         count(distinct source_signal_id) as source_signal_n,
         count(distinct diagnostic_id) filter(where scorecard_bound) as scorecard_bound_n,
         count(distinct diagnostic_id) filter(where not scorecard_bound) as scorecard_unavailable_n
  from base group by classification
), h as (
  select classification,horizon_hours,
         count(*) as outcome_rows,
         count(*) filter(where evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')) as matured,
         count(*) filter(where evaluation_status in ('PENDING','RETRYABLE_ERROR')) as pending,
         avg(direction_adjusted_close_return_pct) filter(where evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')) as avg_direction_adjusted_close_return_pct,
         avg(mfe_pct) filter(where evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')) as avg_mfe_pct,
         avg(mae_pct) filter(where evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')) as avg_mae_pct,
         count(*) filter(where evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR') and target_hit is true) as target_hits,
         count(*) filter(where evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR') and stop_hit is true) as stop_hits,
         max(evaluated_at_utc) as latest_evaluated_at_utc
  from base
  where horizon_hours in (1,4,12,24)
  group by classification,horizon_hours
)
select h.classification,h.horizon_hours,k.diagnostic_n,k.source_signal_n,
       k.scorecard_bound_n,k.scorecard_unavailable_n,h.outcome_rows,h.matured,h.pending,
       h.avg_direction_adjusted_close_return_pct,h.avg_mfe_pct,h.avg_mae_pct,
       h.target_hits,h.stop_hits,h.latest_evaluated_at_utc,
       'EXPLORATORY_PROSPECTIVE'::text as scientific_state,
       'NO_CONFIRMATORY_CLAIM_THIS_COHORT'::text as scientific_conclusion,
       'Allow current scorecard outcomes to mature; any threshold requires a separately preregistered future holdout excluding this exploratory cohort.'::text as next_gate,
       false as confirmatory_claim_permitted,
       false as threshold_derivation_permitted,
       false as production_promotion_permitted,
       true as shadow_only,
       false as trade_permission
from h join keys k using(classification)
order by h.classification,h.horizon_hours;

revoke all on public.alpha_hunter_participation_forward_observations_v02 from public,anon,authenticated;
revoke all on public.alpha_hunter_participation_forward_status_v02 from public,anon,authenticated;
grant select on public.alpha_hunter_participation_forward_observations_v02 to service_role;
grant select on public.alpha_hunter_participation_forward_status_v02 to service_role;

commit;
