-- Alpha Hunter forward cost-to-risk viability ledger v0.1
--
-- Mission:
--   Measure whether frozen Alpha Hunter decisions survive even the minimum
--   observable fee+spread cost floor when expressed in R units.
--
-- Scientific limits:
--   * observable cost floor is descriptive, NOT a validated execution-cost model;
--   * no slippage, latency, impact, funding, or adverse-selection claim;
--   * floor-adjusted R is diagnostic only and is NOT realistic net R;
--   * no trade, selector, threshold, risk, or production authority.
--
-- Forward boundary:
--   Only execution freezes at/after this spec's registered_at_utc are admitted.
--   No historical backfill.
--
-- Exactness:
--   Only the first SHADOW_CANDIDATE observation in a strategy instance is
--   admitted, matching the existing strategy-forward-outcome contract.

create table if not exists private.alpha_hunter_cost_to_risk_forward_specs_v01 (
  spec_id text primary key,
  registered_at_utc timestamptz not null,
  horizon_hours integer not null check(horizon_hours=24),
  cost_floor_model_version text not null,
  outcome_model_version text not null,
  status text not null check(status in ('COLLECTING','PAUSED','COMPLETE')),
  scientific_role text not null,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

insert into private.alpha_hunter_cost_to_risk_forward_specs_v01(
  spec_id,registered_at_utc,horizon_hours,cost_floor_model_version,
  outcome_model_version,status,scientific_role,
  shadow_only,trade_permission,threshold_change_permitted,
  production_promotion_permitted,realistic_net_r_claim_permitted,order_path
) values (
  'COST-TO-RISK-FORWARD-V01',
  clock_timestamp(),
  24,
  'execution-cost-floor-status-v0.1',
  'strategy-forward-outcome-v0.1',
  'COLLECTING',
  'FORWARD_COST_TO_RISK_VIABILITY_DIAGNOSTIC',
  true,false,false,false,false,'NONE'
)
on conflict(spec_id) do nothing;

create table if not exists private.alpha_hunter_cost_to_risk_forward_candidates_v01 (
  candidate_id text primary key,
  spec_id text not null
    references private.alpha_hunter_cost_to_risk_forward_specs_v01(spec_id),
  execution_event_id text not null unique,
  strategy_instance_id text not null unique,
  decision_observation_id text not null,
  decision_run_id text not null,
  symbol text not null,
  strategy_id text not null,
  direction text not null check(direction in ('LONG','SHORT')),
  action text not null check(action in ('EXECUTE_NOW','PLACE_LIMIT')),
  decision_observed_at_utc timestamptz not null,
  frozen_at_utc timestamptz not null,
  entry_price double precision not null check(entry_price>0),
  stop_price double precision not null check(stop_price>0),
  target_price double precision not null check(target_price>0),
  reward_risk double precision not null check(reward_risk>0),
  stop_distance_bps double precision not null check(stop_distance_bps>0),
  liquidity_state text,
  cost_scope text not null,
  observable_floor_median_bps double precision not null
    check(observable_floor_median_bps>=0),
  observable_floor_p90_bps double precision not null
    check(observable_floor_p90_bps>=0),
  floor_cost_r_median double precision not null check(floor_cost_r_median>=0),
  floor_cost_r_p90 double precision not null check(floor_cost_r_p90>=0),
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'FORWARD_COST_TO_RISK_CANDIDATE',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  captured_at_utc timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_cost_to_risk_candidate_time_v01
  on private.alpha_hunter_cost_to_risk_forward_candidates_v01(
    spec_id,frozen_at_utc
  );

create table if not exists private.alpha_hunter_cost_to_risk_forward_outcomes_v01 (
  outcome_id text primary key,
  candidate_id text not null unique
    references private.alpha_hunter_cost_to_risk_forward_candidates_v01(candidate_id),
  spec_id text not null,
  execution_event_id text not null,
  strategy_instance_id text not null,
  symbol text not null,
  strategy_id text not null,
  direction text not null,
  action text not null,
  evaluated_at_utc timestamptz not null,
  path_outcome_class text not null,
  path_measurement_quality text not null,
  ordering_ambiguous boolean not null,
  direction_adjusted_endpoint_return_pct double precision,
  risk_pct double precision not null check(risk_pct>0),
  reward_risk double precision not null check(reward_risk>0),
  gross_r double precision not null,
  floor_cost_r_median double precision not null,
  floor_cost_r_p90 double precision not null,
  floor_adjusted_r_median double precision not null,
  floor_adjusted_r_p90 double precision not null,
  cost_adjustment_status text not null
    check(cost_adjustment_status='DESCRIPTIVE_OBSERVED_FEE_SPREAD_FLOOR_ONLY'),
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'FORWARD_COST_TO_RISK_OUTCOME',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_cost_to_risk_outcome_strategy_v01
  on private.alpha_hunter_cost_to_risk_forward_outcomes_v01(
    strategy_id,direction,action,evaluated_at_utc
  );

create table if not exists private.alpha_hunter_cost_to_risk_forward_runs_v01 (
  run_id text primary key,
  spec_id text not null,
  checked_at_utc timestamptz not null,
  candidates_inserted integer not null,
  outcomes_inserted integer not null,
  candidate_rows_total integer not null,
  outcome_rows_total integer not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  realistic_net_r_claim_permitted boolean not null default false
    check(realistic_net_r_claim_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create or replace function private.alpha_hunter_run_cost_to_risk_forward_v01()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_spec private.alpha_hunter_cost_to_risk_forward_specs_v01%rowtype;
  v_now timestamptz:=clock_timestamp();
  v_candidates_inserted integer:=0;
  v_outcomes_inserted integer:=0;
  v_candidate_total integer:=0;
  v_outcome_total integer:=0;
  v_run_id text;
begin
  select * into v_spec
  from private.alpha_hunter_cost_to_risk_forward_specs_v01
  where spec_id='COST-TO-RISK-FORWARD-V01'
    and status='COLLECTING';

  if v_spec.spec_id is null then
    return jsonb_build_object(
      'status','NO_ACTIVE_SPEC',
      'shadow_only',true,
      'trade_permission',false,
      'realistic_net_r_claim_permitted',false
    );
  end if;

  with source_rows as (
    select
      f.execution_event_id,
      f.strategy_instance_id,
      f.decision_observation_id,
      f.decision_run_id,
      f.symbol,
      f.strategy_id,
      f.direction,
      f.action,
      f.decision_observed_at_utc,
      f.frozen_at_utc,
      f.planned_entry_price::double precision as entry_price,
      f.stop_price::double precision as stop_price,
      f.target_price::double precision as target_price,
      f.reward_risk::double precision as reward_risk,
      so.observed_at_utc as strategy_observed_at_utc,
      sf.liquidity_state,
      10000.0*abs(f.planned_entry_price-f.stop_price)
        /nullif(f.planned_entry_price,0) as stop_distance_bps
    from public.alpha_hunter_execution_decision_freezes_v01 f
    join public.alpha_hunter_strategy_observations_v01 so
      on so.observation_id=f.decision_observation_id
     and so.strategy_instance_id=f.strategy_instance_id
     and so.status='SHADOW_CANDIDATE'
    left join lateral (
      select x.liquidity_state
      from public.alpha_hunter_signal_features x
      where x.run_id=f.decision_run_id
        and upper(x.symbol)=upper(f.symbol)
      order by abs(
        extract(epoch from(x.captured_at_utc-f.decision_observed_at_utc))
      ) asc
      limit 1
    ) sf on true
    where f.frozen_at_utc>=v_spec.registered_at_utc
      and f.planned_entry_price is not null
      and f.planned_entry_price>0
      and f.stop_price is not null
      and f.stop_price>0
      and f.target_price is not null
      and f.target_price>0
      and f.reward_risk is not null
      and f.reward_risk>0
      and not exists (
        select 1
        from public.alpha_hunter_strategy_observations_v01 earlier
        where earlier.strategy_instance_id=f.strategy_instance_id
          and earlier.status='SHADOW_CANDIDATE'
          and (
            earlier.observed_at_utc<so.observed_at_utc
            or (
              earlier.observed_at_utc=so.observed_at_utc
              and earlier.observation_id<so.observation_id
            )
          )
      )
  ), costed as (
    select s.*,
           coalesce(scope_floor.cost_scope,all_floor.cost_scope) as cost_scope,
           coalesce(
             scope_floor.observable_taker_round_trip_floor_median_bps,
             all_floor.observable_taker_round_trip_floor_median_bps
           ) as floor_median_bps,
           coalesce(
             scope_floor.observable_taker_round_trip_floor_p90_bps,
             all_floor.observable_taker_round_trip_floor_p90_bps
           ) as floor_p90_bps
    from source_rows s
    left join lateral (
      select c.*
      from public.alpha_hunter_execution_cost_floor_status_v01 c
      where c.cost_scope=upper(coalesce(s.liquidity_state,''))
      limit 1
    ) scope_floor on true
    left join lateral (
      select c.*
      from public.alpha_hunter_execution_cost_floor_status_v01 c
      where c.cost_scope='ALL'
      limit 1
    ) all_floor on true
  ), inserted as (
    insert into private.alpha_hunter_cost_to_risk_forward_candidates_v01(
      candidate_id,spec_id,execution_event_id,strategy_instance_id,
      decision_observation_id,decision_run_id,symbol,strategy_id,direction,action,
      decision_observed_at_utc,frozen_at_utc,entry_price,stop_price,target_price,
      reward_risk,stop_distance_bps,liquidity_state,cost_scope,
      observable_floor_median_bps,observable_floor_p90_bps,
      floor_cost_r_median,floor_cost_r_p90,evidence,
      shadow_only,trade_permission,threshold_change_permitted,
      production_promotion_permitted,realistic_net_r_claim_permitted,order_path
    )
    select
      'cost-risk-'||md5(v_spec.spec_id||'|'||c.execution_event_id),
      v_spec.spec_id,
      c.execution_event_id,
      c.strategy_instance_id,
      c.decision_observation_id,
      c.decision_run_id,
      c.symbol,
      c.strategy_id,
      c.direction,
      c.action,
      c.decision_observed_at_utc,
      c.frozen_at_utc,
      c.entry_price,
      c.stop_price,
      c.target_price,
      c.reward_risk,
      c.stop_distance_bps,
      c.liquidity_state,
      c.cost_scope,
      c.floor_median_bps,
      c.floor_p90_bps,
      c.floor_median_bps/c.stop_distance_bps,
      c.floor_p90_bps/c.stop_distance_bps,
      jsonb_build_object(
        'cost_floor_model_version',v_spec.cost_floor_model_version,
        'cost_floor_scope',c.cost_scope,
        'liquidity_state',c.liquidity_state,
        'first_shadow_candidate_only',true,
        'historical_backfill_permitted',false,
        'validated_cost_model',false
      ),
      true,false,false,false,false,'NONE'
    from costed c
    where c.stop_distance_bps>0
      and c.floor_median_bps is not null
      and c.floor_p90_bps is not null
    on conflict(strategy_instance_id) do nothing
    returning 1
  )
  select count(*) into v_candidates_inserted from inserted;

  with exact_outcomes as (
    select
      c.*,
      o.evaluated_at_utc,
      o.path_outcome_class,
      o.path_measurement_quality,
      o.ordering_ambiguous,
      o.direction_adjusted_endpoint_return_pct,
      o.first_candidate_at_utc,
      o.first_candidate_action,
      o.first_candidate_entry_price,
      100.0*abs(c.entry_price-c.stop_price)/c.entry_price as risk_pct
    from private.alpha_hunter_cost_to_risk_forward_candidates_v01 c
    join public.alpha_hunter_strategy_forward_outcomes_v01 o
      on o.episode_id=c.strategy_instance_id
     and o.horizon_hours=24
    where c.spec_id=v_spec.spec_id
      and o.path_measurement_quality='COMPLETE_ENOUGH'
      and o.ordering_ambiguous=false
      and o.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
      and o.first_candidate_at_utc=c.decision_observed_at_utc
      and o.first_candidate_action=c.action
      and abs(
        o.first_candidate_entry_price-c.entry_price
      )<=greatest(1e-12,abs(c.entry_price)*1e-9)
      and not exists (
        select 1
        from private.alpha_hunter_cost_to_risk_forward_outcomes_v01 x
        where x.candidate_id=c.candidate_id
      )
  ), scored as (
    select e.*,
      case
        when e.path_outcome_class='STOP_FIRST' then -1.0
        when e.path_outcome_class='TARGET_FIRST' then e.reward_risk
        when e.path_outcome_class='OPEN_AT_HORIZON'
             and e.direction_adjusted_endpoint_return_pct is not null
             and e.risk_pct>0
          then greatest(
            -1.0,
            least(
              e.reward_risk,
              e.direction_adjusted_endpoint_return_pct/e.risk_pct
            )
          )
        else null
      end as gross_r
    from exact_outcomes e
  ), inserted as (
    insert into private.alpha_hunter_cost_to_risk_forward_outcomes_v01(
      outcome_id,candidate_id,spec_id,execution_event_id,strategy_instance_id,
      symbol,strategy_id,direction,action,evaluated_at_utc,
      path_outcome_class,path_measurement_quality,ordering_ambiguous,
      direction_adjusted_endpoint_return_pct,risk_pct,reward_risk,gross_r,
      floor_cost_r_median,floor_cost_r_p90,
      floor_adjusted_r_median,floor_adjusted_r_p90,
      cost_adjustment_status,evidence,
      shadow_only,trade_permission,threshold_change_permitted,
      production_promotion_permitted,realistic_net_r_claim_permitted,order_path
    )
    select
      'cost-risk-outcome-'||md5(s.candidate_id),
      s.candidate_id,s.spec_id,s.execution_event_id,s.strategy_instance_id,
      s.symbol,s.strategy_id,s.direction,s.action,s.evaluated_at_utc,
      s.path_outcome_class,s.path_measurement_quality,s.ordering_ambiguous,
      s.direction_adjusted_endpoint_return_pct,s.risk_pct,s.reward_risk,s.gross_r,
      s.floor_cost_r_median,s.floor_cost_r_p90,
      s.gross_r-s.floor_cost_r_median,
      s.gross_r-s.floor_cost_r_p90,
      'DESCRIPTIVE_OBSERVED_FEE_SPREAD_FLOOR_ONLY',
      jsonb_build_object(
        'gross_r_source','EXACT_FIRST_CANDIDATE_24H_FORWARD_OUTCOME',
        'cost_floor_is_validated',false,
        'slippage_included',false,
        'latency_included',false,
        'market_impact_included',false,
        'funding_included',false,
        'adverse_selection_included',false,
        'realistic_net_r_claim_permitted',false
      ),
      true,false,false,false,false,'NONE'
    from scored s
    where s.gross_r is not null
    on conflict(candidate_id) do nothing
    returning 1
  )
  select count(*) into v_outcomes_inserted from inserted;

  select count(*) into v_candidate_total
  from private.alpha_hunter_cost_to_risk_forward_candidates_v01
  where spec_id=v_spec.spec_id;

  select count(*) into v_outcome_total
  from private.alpha_hunter_cost_to_risk_forward_outcomes_v01
  where spec_id=v_spec.spec_id;

  v_run_id:='cost-risk-run-'||md5(v_now::text);

  insert into private.alpha_hunter_cost_to_risk_forward_runs_v01(
    run_id,spec_id,checked_at_utc,candidates_inserted,outcomes_inserted,
    candidate_rows_total,outcome_rows_total,evidence,
    shadow_only,trade_permission,production_promotion_permitted,
    realistic_net_r_claim_permitted,order_path
  ) values (
    v_run_id,v_spec.spec_id,v_now,v_candidates_inserted,v_outcomes_inserted,
    v_candidate_total,v_outcome_total,
    jsonb_build_object(
      'cost_floor_model_version',v_spec.cost_floor_model_version,
      'outcome_model_version',v_spec.outcome_model_version,
      'historical_backfill_permitted',false,
      'claim_ceiling','DESCRIPTIVE_COST_FLOOR_ADJUSTED_R_ONLY'
    ),
    true,false,false,false,'NONE'
  );

  return jsonb_build_object(
    'run_id',v_run_id,
    'candidates_inserted',v_candidates_inserted,
    'outcomes_inserted',v_outcomes_inserted,
    'candidate_rows_total',v_candidate_total,
    'outcome_rows_total',v_outcome_total,
    'shadow_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'realistic_net_r_claim_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_run_cost_to_risk_forward_v01()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_run_cost_to_risk_forward_v01()
to postgres;

create or replace view private.alpha_hunter_cost_to_risk_forward_scorecard_v01
with (security_invoker=true,security_barrier=true)
as
select
  strategy_id,
  direction,
  action,
  count(*) as evaluated_trades,
  count(distinct symbol) as symbols,
  avg(reward_risk) as avg_planned_reward_risk,
  avg(floor_cost_r_median) as avg_floor_cost_r_median,
  avg(floor_cost_r_p90) as avg_floor_cost_r_p90,
  avg(gross_r) as avg_gross_r,
  sum(gross_r) as cumulative_gross_r,
  avg(floor_adjusted_r_median) as avg_floor_adjusted_r_median,
  sum(floor_adjusted_r_median) as cumulative_floor_adjusted_r_median,
  avg(floor_adjusted_r_p90) as avg_floor_adjusted_r_p90,
  sum(floor_adjusted_r_p90) as cumulative_floor_adjusted_r_p90,
  100.0*count(*) filter(where gross_r>0)/nullif(count(*),0)
    as gross_positive_pct,
  100.0*count(*) filter(where floor_adjusted_r_median>0)/nullif(count(*),0)
    as median_floor_positive_pct,
  100.0*count(*) filter(where floor_adjusted_r_p90>0)/nullif(count(*),0)
    as p90_floor_positive_pct,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  false as realistic_net_r_claim_permitted,
  'DESCRIPTIVE_COST_FLOOR_ADJUSTED_R_ONLY'::text as claim_ceiling,
  'NONE'::text as order_path
from private.alpha_hunter_cost_to_risk_forward_outcomes_v01
group by strategy_id,direction,action;

revoke all on private.alpha_hunter_cost_to_risk_forward_specs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_cost_to_risk_forward_candidates_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_cost_to_risk_forward_outcomes_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_cost_to_risk_forward_runs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_cost_to_risk_forward_scorecard_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_cost_to_risk_forward_specs_v01 to service_role;
grant select on private.alpha_hunter_cost_to_risk_forward_candidates_v01 to service_role;
grant select on private.alpha_hunter_cost_to_risk_forward_outcomes_v01 to service_role;
grant select on private.alpha_hunter_cost_to_risk_forward_runs_v01 to service_role;
grant select on private.alpha_hunter_cost_to_risk_forward_scorecard_v01 to service_role;

do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-cost-to-risk-forward-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-cost-to-risk-forward-v01',
  '13 * * * *',
  $cmd$
    select private.alpha_hunter_run_cost_to_risk_forward_v01();
  $cmd$
);

-- No execution freeze before registered_at_utc is admitted.
