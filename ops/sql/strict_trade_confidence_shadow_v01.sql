-- Alpha Hunter strict trade-confidence shadow engine v0.1
--
-- Purpose:
--   Estimate probability from PATH-AWARE triggered strategy trades only.
--   This explicitly excludes the old endpoint-only confidence semantics.
--
-- Historical outcome definition:
--   TARGET_FIRST        -> WIN
--   STOP_FIRST          -> LOSS
--   OPEN_AT_HORIZON     -> WIN iff direction-adjusted endpoint return > 0
--   all other / ambiguous / untriggered outcomes -> excluded
--
-- Calibration cutoff is frozen before deployment. New R3 decisions are scored
-- prospectively and never used to retrain themselves.
--
-- Research only:
--   no paper-order authority
--   no exchange authority
--   no threshold change
--   no production promotion

create table if not exists private.alpha_hunter_strict_trade_confidence_specs_v01 (
  spec_id text primary key,
  experiment_started_at_utc timestamptz not null,
  historical_cutoff_utc timestamptz not null,
  outcome_horizon_hours integer not null,
  minimum_exact_sample integer not null,
  minimum_base_sample integer not null,
  z_score_95 double precision not null,
  target_band_min_pct double precision not null,
  target_band_max_pct double precision not null,
  outcome_definition text not null,
  scientific_role text not null,
  shadow_only boolean not null default true check(shadow_only=true),
  paper_order_permission boolean not null default false check(paper_order_permission=false),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

insert into private.alpha_hunter_strict_trade_confidence_specs_v01(
  spec_id,experiment_started_at_utc,historical_cutoff_utc,
  outcome_horizon_hours,minimum_exact_sample,minimum_base_sample,z_score_95,
  target_band_min_pct,target_band_max_pct,outcome_definition,scientific_role,
  shadow_only,paper_order_permission,trade_permission,threshold_change_permitted,
  production_promotion_permitted,order_path
) values (
  'STRICT-TRADE-CONFIDENCE-R3-V01',
  clock_timestamp(),
  timestamptz '2026-09-28 00:00:00+00',
  24,10,20,1.96,
  65.0,75.0,
  'PATH_AWARE_TRIGGERED_24H_GROSS_WIN',
  'FORWARD_STRICT_TRADE_CONFIDENCE_SHADOW',
  true,false,false,false,false,'NONE'
)
on conflict(spec_id) do nothing;

create table if not exists private.alpha_hunter_strict_trade_confidence_scores_v01 (
  score_id text primary key,
  spec_id text not null references private.alpha_hunter_strict_trade_confidence_specs_v01(spec_id),
  execution_event_id text not null unique,
  decision_observation_id text not null,
  run_id text not null,
  symbol text not null,
  strategy_id text not null,
  direction text not null,
  action text not null,
  frozen_at_utc timestamptz not null,
  reward_risk double precision,
  market_phase text,
  opportunity_timing text,
  persistence_state text,
  selected_level text not null,
  sample_n integer,
  sample_wins integer,
  point_estimate_pct double precision,
  lower_95_pct double precision,
  upper_95_pct double precision,
  evidence_tier text not null,
  target_band_status text not null,
  paper_eligible boolean not null default false check(paper_eligible=false),
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  paper_order_permission boolean not null default false check(paper_order_permission=false),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  scored_at_utc timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_strict_confidence_scores_time_v01
  on private.alpha_hunter_strict_trade_confidence_scores_v01(scored_at_utc desc);

create index if not exists idx_ah_strict_confidence_scores_symbol_v01
  on private.alpha_hunter_strict_trade_confidence_scores_v01(symbol,frozen_at_utc desc);

create table if not exists private.alpha_hunter_strict_trade_confidence_runs_v01 (
  research_run_id text primary key,
  spec_id text not null references private.alpha_hunter_strict_trade_confidence_specs_v01(spec_id),
  checked_at_utc timestamptz not null,
  decisions_scored integer not null,
  exact_level_scores integer not null,
  base_level_scores integer not null,
  insufficient_scores integer not null,
  in_target_band_point_estimates integer not null,
  paper_eligible_scores integer not null,
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

create or replace function private.alpha_hunter_run_strict_trade_confidence_shadow_v01()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  v_spec private.alpha_hunter_strict_trade_confidence_specs_v01%rowtype;
  d record;
  v_n integer;
  v_wins integer;
  v_level text;
  v_point double precision;
  v_den double precision;
  v_center double precision;
  v_margin double precision;
  v_lower double precision;
  v_upper double precision;
  v_tier text;
  v_band text;
  v_scored integer:=0;
  v_exact integer:=0;
  v_base integer:=0;
  v_insufficient integer:=0;
  v_band_count integer:=0;
  v_research_run_id text;
begin
  select * into v_spec
  from private.alpha_hunter_strict_trade_confidence_specs_v01
  where spec_id='STRICT-TRADE-CONFIDENCE-R3-V01';

  if v_spec.spec_id is null then
    raise exception 'strict trade confidence spec missing';
  end if;

  for d in
    select
      f.execution_event_id,
      f.decision_observation_id,
      f.decision_run_id,
      f.symbol,
      o.strategy_id,
      f.direction,
      f.action,
      f.frozen_at_utc,
      f.reward_risk,
      o.market_phase,
      o.opportunity_timing,
      o.persistence_state
    from public.alpha_hunter_execution_decision_freezes_v01 f
    join public.alpha_hunter_strategy_observations_v01 o
      on o.observation_id=f.decision_observation_id
    where f.spec_id='SEALED-ARCH-V14R3-FP-20M-20260929'
      and f.frozen_at_utc>=v_spec.experiment_started_at_utc
      and not exists(
        select 1
        from private.alpha_hunter_strict_trade_confidence_scores_v01 s
        where s.execution_event_id=f.execution_event_id
      )
    order by f.frozen_at_utc
    limit 500
  loop
    v_n:=0;
    v_wins:=0;
    v_level:='INSUFFICIENT';

    with hist as (
      select
        x.strategy_id,
        x.direction,
        x.first_candidate_action as action,
        case
          when x.path_outcome_class='TARGET_FIRST' then true
          when x.path_outcome_class='STOP_FIRST' then false
          when x.path_outcome_class='OPEN_AT_HORIZON'
            then x.direction_adjusted_endpoint_return_pct>0
          else null
        end as trade_win
      from public.alpha_hunter_strategy_forward_outcomes_v01 x
      where x.horizon_hours=v_spec.outcome_horizon_hours
        and x.first_observed_at_utc<v_spec.historical_cutoff_utc
        and x.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
        and x.path_measurement_quality='COMPLETE_ENOUGH'
        and x.ordering_ambiguous=false
    )
    select count(*),count(*) filter(where trade_win)
      into v_n,v_wins
    from hist
    where trade_win is not null
      and strategy_id=d.strategy_id
      and direction=d.direction
      and action=d.action;

    if v_n>=v_spec.minimum_exact_sample then
      v_level:='STRATEGY_DIRECTION_ACTION';
      v_exact:=v_exact+1;
    else
      with hist as (
        select
          x.direction,
          x.first_candidate_action as action,
          case
            when x.path_outcome_class='TARGET_FIRST' then true
            when x.path_outcome_class='STOP_FIRST' then false
            when x.path_outcome_class='OPEN_AT_HORIZON'
              then x.direction_adjusted_endpoint_return_pct>0
            else null
          end as trade_win
        from public.alpha_hunter_strategy_forward_outcomes_v01 x
        where x.horizon_hours=v_spec.outcome_horizon_hours
          and x.first_observed_at_utc<v_spec.historical_cutoff_utc
          and x.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
          and x.path_measurement_quality='COMPLETE_ENOUGH'
          and x.ordering_ambiguous=false
      )
      select count(*),count(*) filter(where trade_win)
        into v_n,v_wins
      from hist
      where trade_win is not null
        and direction=d.direction
        and action=d.action;

      if v_n>=v_spec.minimum_base_sample then
        v_level:='DIRECTION_ACTION_BASE';
        v_base:=v_base+1;
      else
        v_level:='INSUFFICIENT';
        v_insufficient:=v_insufficient+1;
      end if;
    end if;

    if v_level='INSUFFICIENT' or v_n<=0 then
      v_point:=null;
      v_lower:=null;
      v_upper:=null;
      v_tier:='INSUFFICIENT_SAMPLE';
      v_band:='INSUFFICIENT_EVIDENCE';
    else
      v_point:=100.0*v_wins::double precision/v_n::double precision;

      v_den:=1.0+(v_spec.z_score_95*v_spec.z_score_95/v_n::double precision);
      v_center:=(
        (v_wins::double precision/v_n::double precision)
        +(v_spec.z_score_95*v_spec.z_score_95/(2.0*v_n::double precision))
      )/v_den;
      v_margin:=(
        v_spec.z_score_95
        *sqrt(
          ((v_wins::double precision/v_n::double precision)
           *(1.0-(v_wins::double precision/v_n::double precision))
           /v_n::double precision)
          +(v_spec.z_score_95*v_spec.z_score_95/(4.0*v_n::double precision*v_n::double precision))
        )
      )/v_den;

      v_lower:=100.0*greatest(0.0,v_center-v_margin);
      v_upper:=100.0*least(1.0,v_center+v_margin);

      v_tier:=case
        when v_n>=100 then 'LARGE_SAMPLE'
        when v_n>=30 then 'MEDIUM_SAMPLE'
        else 'SMALL_SAMPLE'
      end;

      v_band:=case
        when v_point between v_spec.target_band_min_pct and v_spec.target_band_max_pct
          then 'POINT_ESTIMATE_IN_65_75_BAND_NOT_VALIDATED'
        else 'POINT_ESTIMATE_OUTSIDE_65_75_BAND'
      end;

      if v_point between v_spec.target_band_min_pct and v_spec.target_band_max_pct then
        v_band_count:=v_band_count+1;
      end if;
    end if;

    insert into private.alpha_hunter_strict_trade_confidence_scores_v01(
      score_id,spec_id,execution_event_id,decision_observation_id,
      run_id,symbol,strategy_id,direction,action,frozen_at_utc,reward_risk,
      market_phase,opportunity_timing,persistence_state,
      selected_level,sample_n,sample_wins,point_estimate_pct,
      lower_95_pct,upper_95_pct,evidence_tier,target_band_status,
      paper_eligible,evidence,
      shadow_only,paper_order_permission,trade_permission,
      threshold_change_permitted,production_promotion_permitted,order_path
    ) values (
      'strict-conf-'||md5(v_spec.spec_id||'|'||d.execution_event_id),
      v_spec.spec_id,d.execution_event_id,d.decision_observation_id,
      d.decision_run_id,d.symbol,d.strategy_id,d.direction,d.action,
      d.frozen_at_utc,d.reward_risk,d.market_phase,d.opportunity_timing,
      d.persistence_state,
      v_level,
      case when v_level='INSUFFICIENT' then null else v_n end,
      case when v_level='INSUFFICIENT' then null else v_wins end,
      v_point,v_lower,v_upper,v_tier,v_band,
      false,
      jsonb_build_object(
        'outcome_definition',v_spec.outcome_definition,
        'historical_cutoff_utc',v_spec.historical_cutoff_utc,
        'minimum_exact_sample',v_spec.minimum_exact_sample,
        'minimum_base_sample',v_spec.minimum_base_sample,
        'confidence_interval','WILSON_95',
        'point_estimate_is_trade_permission',false,
        'paper_order_permission',false,
        'live_money_permission',false
      ),
      true,false,false,false,false,'NONE'
    )
    on conflict(execution_event_id) do nothing;

    v_scored:=v_scored+1;
  end loop;

  v_research_run_id:='strict-confidence-run-'||md5(clock_timestamp()::text);

  insert into private.alpha_hunter_strict_trade_confidence_runs_v01(
    research_run_id,spec_id,checked_at_utc,decisions_scored,
    exact_level_scores,base_level_scores,insufficient_scores,
    in_target_band_point_estimates,paper_eligible_scores,evidence,
    shadow_only,trade_permission,production_promotion_permitted,order_path
  ) values (
    v_research_run_id,v_spec.spec_id,clock_timestamp(),v_scored,
    v_exact,v_base,v_insufficient,v_band_count,0,
    jsonb_build_object(
      'model_version','strict-trade-confidence-shadow-v0.1',
      'outcome_definition',v_spec.outcome_definition,
      'paper_policy_created',false,
      'trade_permission',false,
      'production_promotion_permitted',false
    ),
    true,false,false,'NONE'
  );

  return jsonb_build_object(
    'research_run_id',v_research_run_id,
    'decisions_scored',v_scored,
    'exact_level_scores',v_exact,
    'base_level_scores',v_base,
    'insufficient_scores',v_insufficient,
    'in_target_band_point_estimates',v_band_count,
    'paper_eligible_scores',0,
    'shadow_only',true,
    'paper_order_permission',false,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_run_strict_trade_confidence_shadow_v01()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_run_strict_trade_confidence_shadow_v01()
to postgres;

create or replace view private.alpha_hunter_strict_trade_confidence_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  s.execution_event_id,s.run_id,s.symbol,s.strategy_id,s.direction,s.action,
  s.frozen_at_utc,s.reward_risk,s.market_phase,s.opportunity_timing,
  s.persistence_state,s.selected_level,s.sample_n,s.sample_wins,
  s.point_estimate_pct,s.lower_95_pct,s.upper_95_pct,
  s.evidence_tier,s.target_band_status,s.paper_eligible,
  true as shadow_only,
  false as paper_order_permission,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from private.alpha_hunter_strict_trade_confidence_scores_v01 s;

revoke all on private.alpha_hunter_strict_trade_confidence_specs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_strict_trade_confidence_scores_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_strict_trade_confidence_runs_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_strict_trade_confidence_status_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_strict_trade_confidence_specs_v01
to service_role;
grant select on private.alpha_hunter_strict_trade_confidence_scores_v01
to service_role;
grant select on private.alpha_hunter_strict_trade_confidence_runs_v01
to service_role;
grant select on private.alpha_hunter_strict_trade_confidence_status_v01
to service_role;

do $cron$
declare
  j record;
begin
  for j in
    select jobid
    from cron.job
    where jobname='alpha-hunter-strict-trade-confidence-shadow-v01'
  loop
    perform cron.unschedule(j.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-strict-trade-confidence-shadow-v01',
  '12 * * * *',
  $cmd$
    select private.alpha_hunter_run_strict_trade_confidence_shadow_v01();
  $cmd$
);

-- Research only. No score from this object can create a paper or live order.
