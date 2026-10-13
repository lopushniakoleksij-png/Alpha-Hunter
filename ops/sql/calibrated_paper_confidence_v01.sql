-- Alpha Hunter calibrated paper-confidence experiment v0.1
--
-- Replaces the raw model-confidence paper gate with a forward-only empirical
-- cohort derived from historical + holdout outcomes.
--
-- Outcome definition used for calibration:
--   24H direction-adjusted endpoint return > 0.
--
-- Cohort:
--   state=WATCH_SHORT
--   trend_1h=BEARISH
--   trend_4h=NEUTRAL
--   btc_regime=BTC_NEUTRAL
--   liquidity_state=GOOD
--   volume_expansion=false
--
-- Evidence:
--   training: 39 / 58 = 67.24%
--   holdout:   8 / 12 = 66.67%
--   combined: 47 / 70 = 67.14%
--   Wilson 95% CI on combined: 55.50% .. 77.00%
--
-- This is an experimental estimated win probability, NOT a guarantee and NOT
-- yet a statistically tight 65-75% confidence interval.
--
-- Additional execution gate:
--   frozen R3 decision
--   direction SHORT
--   action EXECUTE_NOW or PLACE_LIMIT
--   reward_risk >= 5
--   valid short geometry target < entry < stop
--
-- PAPER ONLY. No Bitget write path.

update private.alpha_hunter_paper_production_policy_v01
set status='PAUSED',updated_at=clock_timestamp()
where policy_id='PAPER-PROD-65-70-RR5-V01'
  and status='ACTIVE';

create table if not exists private.alpha_hunter_calibrated_paper_policy_v01 (
  policy_id text primary key,
  status text not null check(status in ('ACTIVE','PAUSED','RETIRED')),
  outcome_definition text not null,
  calibrated_confidence_pct double precision not null,
  confidence_lower_95_pct double precision not null,
  confidence_upper_95_pct double precision not null,
  training_n integer not null,
  training_wins integer not null,
  holdout_n integer not null,
  holdout_wins integer not null,
  minimum_reward_risk double precision not null,
  max_active_paper_orders integer not null default 1,
  cohort jsonb not null,
  evidence jsonb not null,
  paper_only boolean not null default true check(paper_only=true),
  live_order_authority boolean not null default false check(live_order_authority=false),
  trade_permission boolean not null default false check(trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  check(calibrated_confidence_pct between 0 and 100),
  check(confidence_lower_95_pct between 0 and calibrated_confidence_pct),
  check(confidence_upper_95_pct between calibrated_confidence_pct and 100),
  check(training_n>0 and holdout_n>0),
  check(training_wins between 0 and training_n),
  check(holdout_wins between 0 and holdout_n),
  check(minimum_reward_risk>0),
  check(max_active_paper_orders>=1)
);

create table if not exists private.alpha_hunter_calibrated_paper_orders_v01 (
  paper_order_id text primary key,
  policy_id text not null references private.alpha_hunter_calibrated_paper_policy_v01(policy_id),
  execution_event_id text not null unique,
  decision_observation_id text not null,
  strategy_instance_id text not null,
  run_id text not null,
  symbol text not null,
  strategy_id text not null,
  direction text not null check(direction in ('LONG','SHORT')),
  action text not null check(action in ('EXECUTE_NOW','PLACE_LIMIT')),
  decision_observed_at_utc timestamptz not null,
  frozen_at_utc timestamptz not null,
  paper_order_created_at_utc timestamptz not null default clock_timestamp(),
  planned_entry_price double precision not null check(planned_entry_price>0),
  stop_price double precision not null check(stop_price>0),
  target_price double precision not null check(target_price>0),
  reward_risk double precision not null check(reward_risk>0),
  calibrated_confidence_pct double precision not null,
  confidence_lower_95_pct double precision not null,
  confidence_upper_95_pct double precision not null,
  calibration_cohort jsonb not null,
  state text not null check(state in ('PENDING_LIMIT_PAPER','OPEN_PAPER','OUTCOME_AVAILABLE')),
  paper_only boolean not null default true check(paper_only=true),
  live_exchange_order_sent boolean not null default false check(live_exchange_order_sent=false),
  trade_permission boolean not null default false check(trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_cal_paper_orders_state_time
  on private.alpha_hunter_calibrated_paper_orders_v01(state,paper_order_created_at_utc desc);

insert into private.alpha_hunter_calibrated_paper_policy_v01(
  policy_id,status,outcome_definition,
  calibrated_confidence_pct,confidence_lower_95_pct,confidence_upper_95_pct,
  training_n,training_wins,holdout_n,holdout_wins,
  minimum_reward_risk,max_active_paper_orders,cohort,evidence,
  paper_only,live_order_authority,trade_permission
) values (
  'CAL-PAPER-WATCHSHORT-67-V01',
  'ACTIVE',
  '24H_DIRECTION_ADJUSTED_ENDPOINT_RETURN_GT_0',
  67.1428571428571,
  55.5007161169824,
  77.0012881732822,
  58,39,12,8,
  5.0,
  1,
  jsonb_build_object(
    'state','WATCH_SHORT',
    'trend_1h','BEARISH',
    'trend_4h','NEUTRAL',
    'btc_regime','BTC_NEUTRAL',
    'liquidity_state','GOOD',
    'volume_expansion',false
  ),
  jsonb_build_object(
    'training_window_end_utc','2026-09-20T00:00:00+00:00',
    'holdout_window_start_utc','2026-09-20T00:00:00+00:00',
    'holdout_window_end_utc','2026-09-28T00:00:00+00:00',
    'training_win_rate_pct',67.2413793103448,
    'holdout_win_rate_pct',66.6666666666667,
    'combined_n',70,
    'combined_wins',47,
    'combined_win_rate_pct',67.1428571428571,
    'uncertainty_note','95% CI is wider than 65-75; this remains experimental calibration',
    'production_claim_permitted',false,
    'live_money_permitted',false
  ),
  true,false,false
)
on conflict(policy_id) do update
set status='ACTIVE',
    calibrated_confidence_pct=excluded.calibrated_confidence_pct,
    confidence_lower_95_pct=excluded.confidence_lower_95_pct,
    confidence_upper_95_pct=excluded.confidence_upper_95_pct,
    training_n=excluded.training_n,
    training_wins=excluded.training_wins,
    holdout_n=excluded.holdout_n,
    holdout_wins=excluded.holdout_wins,
    minimum_reward_risk=excluded.minimum_reward_risk,
    cohort=excluded.cohort,
    evidence=excluded.evidence,
    updated_at=clock_timestamp();

create or replace function private.alpha_hunter_create_calibrated_paper_order_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $function$
declare
  p private.alpha_hunter_calibrated_paper_policy_v01%rowtype;
  sf public.alpha_hunter_signal_features%rowtype;
  so public.alpha_hunter_strategy_observations_v01%rowtype;
  v_active integer;
  v_state text;
begin
  select * into p
  from private.alpha_hunter_calibrated_paper_policy_v01
  where status='ACTIVE'
  order by updated_at desc
  limit 1;

  if p.policy_id is null then
    return new;
  end if;

  if new.spec_id<>'SEALED-ARCH-V14R3-FP-20M-20260929'
     or new.direction<>'SHORT'
     or new.action not in ('EXECUTE_NOW','PLACE_LIMIT')
     or new.reward_risk is null
     or new.reward_risk<p.minimum_reward_risk
     or new.planned_entry_price is null
     or new.stop_price is null
     or new.target_price is null
     or not (new.target_price<new.planned_entry_price and new.planned_entry_price<new.stop_price)
  then
    return new;
  end if;

  select * into sf
  from public.alpha_hunter_signal_features x
  where x.run_id=new.decision_run_id
    and upper(x.symbol)=upper(new.symbol)
  order by abs(extract(epoch from(x.captured_at_utc-new.decision_observed_at_utc))) asc
  limit 1;

  if sf.signal_id is null
     or sf.state<>'WATCH_SHORT'
     or sf.trend_1h<>'BEARISH'
     or sf.trend_4h<>'NEUTRAL'
     or sf.btc_regime<>'BTC_NEUTRAL'
     or sf.liquidity_state<>'GOOD'
     or sf.volume_expansion is distinct from false
  then
    return new;
  end if;

  select * into so
  from public.alpha_hunter_strategy_observations_v01 s
  where s.observation_id=new.decision_observation_id
  limit 1;

  if so.observation_id is null or so.strategy_instance_id is null then
    return new;
  end if;

  select count(*) into v_active
  from private.alpha_hunter_calibrated_paper_orders_v01
  where state in ('PENDING_LIMIT_PAPER','OPEN_PAPER');

  if v_active>=p.max_active_paper_orders then
    return new;
  end if;

  v_state:=case when new.action='EXECUTE_NOW' then 'OPEN_PAPER' else 'PENDING_LIMIT_PAPER' end;

  insert into private.alpha_hunter_calibrated_paper_orders_v01(
    paper_order_id,policy_id,execution_event_id,decision_observation_id,
    strategy_instance_id,run_id,symbol,strategy_id,direction,action,
    decision_observed_at_utc,frozen_at_utc,planned_entry_price,stop_price,target_price,
    reward_risk,calibrated_confidence_pct,confidence_lower_95_pct,
    confidence_upper_95_pct,calibration_cohort,state,
    paper_only,live_exchange_order_sent,trade_permission
  ) values (
    'cal-paper-'||md5(p.policy_id||'|'||new.execution_event_id),
    p.policy_id,new.execution_event_id,new.decision_observation_id,
    so.strategy_instance_id,new.decision_run_id,new.symbol,so.strategy_id,
    new.direction,new.action,new.decision_observed_at_utc,new.frozen_at_utc,
    new.planned_entry_price,new.stop_price,new.target_price,new.reward_risk,
    p.calibrated_confidence_pct,p.confidence_lower_95_pct,p.confidence_upper_95_pct,
    p.cohort,v_state,true,false,false
  )
  on conflict(execution_event_id) do nothing;

  return new;
end;
$function$;

revoke all on function private.alpha_hunter_create_calibrated_paper_order_v01()
from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_calibrated_paper_order_v01
  on public.alpha_hunter_execution_decision_freezes_v01;

create trigger trg_ah_calibrated_paper_order_v01
after insert on public.alpha_hunter_execution_decision_freezes_v01
for each row
execute function private.alpha_hunter_create_calibrated_paper_order_v01();

create or replace view private.alpha_hunter_calibrated_paper_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  p.paper_order_id,p.policy_id,p.execution_event_id,p.strategy_instance_id,
  p.run_id,p.symbol,p.strategy_id,p.direction,p.action,
  p.decision_observed_at_utc,p.frozen_at_utc,p.paper_order_created_at_utc,
  p.planned_entry_price,p.stop_price,p.target_price,p.reward_risk,
  p.calibrated_confidence_pct,p.confidence_lower_95_pct,p.confidence_upper_95_pct,
  p.state,
  o.evaluated_at_utc,o.entry_trigger_status,o.fill_price,
  o.direction_adjusted_endpoint_return_pct,o.path_outcome_class,
  o.net_of_cost_return_pct,o.cost_adjustment_status,
  case
    when o.episode_id is null then 'WAITING_FOR_24H_OUTCOME'
    when o.direction_adjusted_endpoint_return_pct>0 then 'CALIBRATION_WIN'
    when o.direction_adjusted_endpoint_return_pct<=0 then 'CALIBRATION_LOSS'
    else 'OUTCOME_UNKNOWN'
  end as calibration_result,
  true as paper_only,
  false as live_exchange_order_sent,
  false as trade_permission
from private.alpha_hunter_calibrated_paper_orders_v01 p
left join public.alpha_hunter_strategy_forward_outcomes_v01 o
  on o.episode_id=p.strategy_instance_id
 and o.horizon_hours=24;

revoke all on private.alpha_hunter_calibrated_paper_policy_v01
  from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_calibrated_paper_orders_v01
  from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_calibrated_paper_status_v01
  from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_calibrated_paper_policy_v01
  to service_role;
grant select on private.alpha_hunter_calibrated_paper_orders_v01
  to service_role;
grant select on private.alpha_hunter_calibrated_paper_status_v01
  to service_role;

-- No historical freeze is backfilled. The experiment begins only from freezes
-- inserted after this deployment.
