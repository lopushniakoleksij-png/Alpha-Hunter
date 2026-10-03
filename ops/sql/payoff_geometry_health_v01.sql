-- Alpha Hunter prospective payoff-geometry health monitor v0.1
--
-- Purpose:
--   Score every NEW immutable execution decision against only evidence that was
--   available at decision time:
--     * stop distance vs historical MAE,
--     * target distance vs historical MFE,
--     * descriptive observed cost floor vs stop distance.
--
-- This is a research/diagnostic monitor only. It cannot veto, authorize,
-- resize, or submit an order.
--
-- Scientific boundary:
--   * no historical decision backfill;
--   * historical outcome rows used for a decision must have evaluated_at_utc
--     <= the decision frozen_at_utc;
--   * observed cost floor is descriptive and explicitly unvalidated;
--   * no production promotion without a separate prospective review.

create table if not exists private.alpha_hunter_payoff_geometry_health_specs_v01 (
  spec_id text primary key,
  registered_at_utc timestamptz not null default clock_timestamp(),
  status text not null default 'COLLECTING'
    check(status in ('COLLECTING','PAUSED','RETIRED')),
  minimum_history_n integer not null,
  cost_fragile_threshold_r double precision not null,
  stop_reference text not null,
  target_reference text not null,
  minimum_forward_observations integer not null,
  minimum_forward_symbols integer not null,
  minimum_forward_days integer not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check(minimum_history_n>=1),
  check(cost_fragile_threshold_r>0),
  check(minimum_forward_observations>=1),
  check(minimum_forward_symbols>=1),
  check(minimum_forward_days>=1)
);

insert into private.alpha_hunter_payoff_geometry_health_specs_v01(
  spec_id,status,minimum_history_n,cost_fragile_threshold_r,
  stop_reference,target_reference,
  minimum_forward_observations,minimum_forward_symbols,minimum_forward_days,
  evidence,shadow_only,trade_permission,threshold_change_permitted,
  production_promotion_permitted,order_path
) values (
  'PAYOFF-GEOMETRY-HEALTH-V01',
  'COLLECTING',
  10,
  0.25,
  'HISTORICAL_MEDIAN_MAE_24H_TRIGGERED_COMPLETE_NONAMBIG',
  'HISTORICAL_P90_MFE_24H_TRIGGERED_COMPLETE_NONAMBIG',
  50,
  15,
  5,
  jsonb_build_object(
    'decision_source','IMMUTABLE_EXECUTION_DECISION_FREEZE',
    'history_cutoff_rule','OUTCOME_EVALUATED_AT_OR_BEFORE_DECISION_FREEZE',
    'cost_floor_source','DESCRIPTIVE_OBSERVED_MEDIAN_TAKER_ROUND_TRIP_FLOOR',
    'cost_model_validated',false,
    'realistic_net_r_claim_permitted',false,
    'monitor_is_trade_gate',false
  ),
  true,false,false,false,'NONE'
)
on conflict(spec_id) do nothing;

create table if not exists private.alpha_hunter_payoff_geometry_health_observations_v01 (
  geometry_health_id text primary key,
  spec_id text not null references private.alpha_hunter_payoff_geometry_health_specs_v01(spec_id),
  execution_event_id text not null unique,
  decision_observation_id text not null,
  strategy_instance_id text not null,
  run_id text not null,
  symbol text not null,
  strategy_id text not null,
  direction text not null check(direction in ('LONG','SHORT')),
  action text not null,
  decision_observed_at_utc timestamptz not null,
  frozen_at_utc timestamptz not null,
  planned_entry_price double precision not null,
  stop_price double precision not null,
  target_price double precision not null,
  reward_risk double precision,
  stop_distance_pct double precision not null,
  target_distance_pct double precision not null,
  descriptive_cost_floor_bps double precision,
  descriptive_cost_r double precision,
  history_n integer not null,
  historical_median_mae_pct double precision,
  historical_p75_mae_pct double precision,
  historical_median_mfe_pct double precision,
  historical_p90_mfe_pct double precision,
  stop_inside_median_mae boolean,
  target_beyond_p90_mfe boolean,
  cost_fragile boolean,
  geometry_health text not null,
  reasons jsonb not null default '{}'::jsonb,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check(planned_entry_price>0),
  check(stop_price>0),
  check(target_price>0),
  check(stop_distance_pct>0),
  check(target_distance_pct>0),
  check(history_n>=0)
);

create index if not exists idx_ah_payoff_geometry_health_strategy_v01
  on private.alpha_hunter_payoff_geometry_health_observations_v01(
    strategy_id,direction,frozen_at_utc desc
  );

create index if not exists idx_ah_payoff_geometry_health_class_v01
  on private.alpha_hunter_payoff_geometry_health_observations_v01(
    geometry_health,frozen_at_utc desc
  );

create or replace function private.alpha_hunter_capture_payoff_geometry_health_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $function$
declare
  v_spec private.alpha_hunter_payoff_geometry_health_specs_v01%rowtype;
  v_cost_floor_bps double precision;
  v_stop_pct double precision;
  v_target_pct double precision;
  v_cost_r double precision;
  v_history_n integer:=0;
  v_median_mae double precision;
  v_p75_mae double precision;
  v_median_mfe double precision;
  v_p90_mfe double precision;
  v_stop_inside boolean;
  v_target_beyond boolean;
  v_cost_fragile boolean;
  v_health text;
begin
  select * into v_spec
  from private.alpha_hunter_payoff_geometry_health_specs_v01
  where spec_id='PAYOFF-GEOMETRY-HEALTH-V01'
    and status='COLLECTING';

  if not found then
    return new;
  end if;

  if new.frozen_at_utc<v_spec.registered_at_utc then
    return new;
  end if;

  if new.planned_entry_price is null
     or new.planned_entry_price<=0
     or new.stop_price is null
     or new.stop_price<=0
     or new.target_price is null
     or new.target_price<=0
     or new.strategy_instance_id is null
     or new.decision_observation_id is null
  then
    return new;
  end if;

  v_stop_pct :=
    100.0*abs(new.planned_entry_price-new.stop_price)/new.planned_entry_price;
  v_target_pct :=
    100.0*abs(new.target_price-new.planned_entry_price)/new.planned_entry_price;

  if v_stop_pct<=0 or v_target_pct<=0 then
    return new;
  end if;

  select observable_taker_round_trip_floor_median_bps
    into v_cost_floor_bps
  from public.alpha_hunter_execution_cost_floor_status_v01
  where cost_scope='ALL'
  limit 1;

  if v_cost_floor_bps is not null then
    v_cost_r := (v_cost_floor_bps/100.0)/v_stop_pct;
  end if;

  select
    count(*)::integer,
    percentile_cont(0.5) within group(order by o.max_adverse_excursion_pct),
    percentile_cont(0.75) within group(order by o.max_adverse_excursion_pct),
    percentile_cont(0.5) within group(order by o.max_favorable_excursion_pct),
    percentile_cont(0.90) within group(order by o.max_favorable_excursion_pct)
  into
    v_history_n,
    v_median_mae,
    v_p75_mae,
    v_median_mfe,
    v_p90_mfe
  from public.alpha_hunter_strategy_forward_outcomes_v01 o
  where o.horizon_hours=24
    and o.strategy_id=new.strategy_id
    and o.direction=new.direction
    and o.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
    and o.path_measurement_quality='COMPLETE_ENOUGH'
    and o.ordering_ambiguous=false
    and o.evaluated_at_utc<=new.frozen_at_utc
    and o.max_adverse_excursion_pct is not null
    and o.max_favorable_excursion_pct is not null;

  v_stop_inside :=
    case
      when v_history_n>=v_spec.minimum_history_n and v_median_mae is not null
        then v_stop_pct<v_median_mae
      else null
    end;

  v_target_beyond :=
    case
      when v_history_n>=v_spec.minimum_history_n and v_p90_mfe is not null
        then v_target_pct>v_p90_mfe
      else null
    end;

  v_cost_fragile :=
    case
      when v_cost_r is not null
        then v_cost_r>v_spec.cost_fragile_threshold_r
      else null
    end;

  v_health :=
    case
      when v_history_n<v_spec.minimum_history_n
        then 'INSUFFICIENT_HISTORY'
      when v_stop_inside is true and v_target_beyond is true and v_cost_fragile is true
        then 'STOP_TARGET_AND_COST_FRAGILE'
      when v_stop_inside is true and v_target_beyond is true
        then 'STOP_TIGHT_TARGET_BEYOND_P90'
      when v_stop_inside is true and v_cost_fragile is true
        then 'STOP_AND_COST_FRAGILE'
      when v_target_beyond is true and v_cost_fragile is true
        then 'TARGET_AND_COST_FRAGILE'
      when v_stop_inside is true
        then 'STOP_INSIDE_MEDIAN_MAE'
      when v_target_beyond is true
        then 'TARGET_BEYOND_P90_MFE'
      when v_cost_fragile is true
        then 'COST_FRAGILE'
      else 'GEOMETRY_PLAUSIBLE_SHADOW'
    end;

  insert into private.alpha_hunter_payoff_geometry_health_observations_v01(
    geometry_health_id,spec_id,execution_event_id,decision_observation_id,
    strategy_instance_id,run_id,symbol,strategy_id,direction,action,
    decision_observed_at_utc,frozen_at_utc,
    planned_entry_price,stop_price,target_price,reward_risk,
    stop_distance_pct,target_distance_pct,
    descriptive_cost_floor_bps,descriptive_cost_r,
    history_n,historical_median_mae_pct,historical_p75_mae_pct,
    historical_median_mfe_pct,historical_p90_mfe_pct,
    stop_inside_median_mae,target_beyond_p90_mfe,cost_fragile,
    geometry_health,reasons,evidence,
    shadow_only,trade_permission,threshold_change_permitted,
    production_promotion_permitted,order_path
  ) values (
    'payoff-geometry-'||md5(v_spec.spec_id||'|'||new.execution_event_id),
    v_spec.spec_id,new.execution_event_id,new.decision_observation_id,
    new.strategy_instance_id,new.decision_run_id,new.symbol,new.strategy_id,
    new.direction,new.action,new.decision_observed_at_utc,new.frozen_at_utc,
    new.planned_entry_price,new.stop_price,new.target_price,new.reward_risk,
    v_stop_pct,v_target_pct,v_cost_floor_bps,v_cost_r,
    v_history_n,v_median_mae,v_p75_mae,v_median_mfe,v_p90_mfe,
    v_stop_inside,v_target_beyond,v_cost_fragile,v_health,
    jsonb_build_object(
      'stop_inside_median_mae',v_stop_inside,
      'target_beyond_p90_mfe',v_target_beyond,
      'cost_fragile',v_cost_fragile
    ),
    jsonb_build_object(
      'model_version','payoff-geometry-health-v0.1',
      'history_cutoff_at_decision_utc',new.frozen_at_utc,
      'cost_floor_is_validated_model',false,
      'cost_floor_assumption','DESCRIPTIVE_MEDIAN_TAKER_ROUND_TRIP_FLOOR',
      'trade_gate_applied',false,
      'production_selector_changed',false
    ),
    true,false,false,false,'NONE'
  )
  on conflict(execution_event_id) do nothing;

  return new;
end;
$function$;

revoke all on function private.alpha_hunter_capture_payoff_geometry_health_v01()
from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_payoff_geometry_health_v01
  on public.alpha_hunter_execution_decision_freezes_v01;

create trigger trg_ah_payoff_geometry_health_v01
after insert on public.alpha_hunter_execution_decision_freezes_v01
for each row
execute function private.alpha_hunter_capture_payoff_geometry_health_v01();

create or replace view private.alpha_hunter_payoff_geometry_health_scorecard_v01
with (security_invoker=true,security_barrier=true)
as
select
  strategy_id,
  direction,
  geometry_health,
  count(*) as observation_count,
  count(distinct symbol) as symbol_count,
  min(frozen_at_utc) as first_observed_at_utc,
  max(frozen_at_utc) as last_observed_at_utc,
  avg(stop_distance_pct) as avg_stop_distance_pct,
  avg(target_distance_pct) as avg_target_distance_pct,
  avg(descriptive_cost_r) as avg_descriptive_cost_r,
  avg(history_n) as avg_history_n,
  true as shadow_only,
  false as trade_permission,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from private.alpha_hunter_payoff_geometry_health_observations_v01
group by strategy_id,direction,geometry_health;

revoke all on private.alpha_hunter_payoff_geometry_health_specs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_payoff_geometry_health_observations_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_payoff_geometry_health_scorecard_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_payoff_geometry_health_specs_v01
to service_role;
grant select on private.alpha_hunter_payoff_geometry_health_observations_v01
to service_role;
grant select on private.alpha_hunter_payoff_geometry_health_scorecard_v01
to service_role;

-- Forward-only: this migration does not insert any pre-registration decision.
