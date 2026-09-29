-- Alpha Hunter realistic calibrated paper execution v0.1
--
-- Purpose:
--   Make calibrated paper execution behave like an executable order path
--   without sending any exchange order.
--
-- EXECUTE_NOW:
--   paper fill = decision-time entry_cross_price from the immutable quote.
--
-- PLACE_LIMIT:
--   remains pending until forward evidence says TRIGGERED_LIMIT.
--
-- Outcome:
--   24H path evidence closes the paper outcome. Gross R is recomputed from the
--   paper fill and frozen stop/target geometry. Net R remains NULL while the
--   execution-cost model is unvalidated.
--
-- Safety:
--   PAPER ONLY; no Bitget writes; no live-money permission; no historical
--   decision backfill.

alter table private.alpha_hunter_calibrated_paper_orders_v01
  add column if not exists paper_fill_status text,
  add column if not exists paper_fill_price double precision,
  add column if not exists paper_fill_at_utc timestamptz,
  add column if not exists paper_fill_source text,
  add column if not exists paper_fill_horizon_hours integer,
  add column if not exists paper_entry_half_spread_bps double precision,
  add column if not exists paper_outcome_class text,
  add column if not exists paper_endpoint_price double precision,
  add column if not exists paper_gross_return_pct double precision,
  add column if not exists paper_gross_r double precision,
  add column if not exists paper_net_return_pct double precision,
  add column if not exists paper_net_r double precision,
  add column if not exists paper_cost_adjustment_status text,
  add column if not exists paper_outcome_evaluated_at_utc timestamptz,
  add column if not exists last_reconciled_at_utc timestamptz,
  add column if not exists paper_execution_evidence jsonb not null default '{}'::jsonb;

create or replace function private.alpha_hunter_create_calibrated_paper_order_v02()
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
  v_fill_status text;
  v_fill_price double precision;
  v_fill_at timestamptz;
  v_fill_source text;
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
     or not (
       new.target_price<new.planned_entry_price
       and new.planned_entry_price<new.stop_price
     )
  then
    return new;
  end if;

  select * into sf
  from public.alpha_hunter_signal_features x
  where x.run_id=new.decision_run_id
    and upper(x.symbol)=upper(new.symbol)
  order by abs(
    extract(epoch from(x.captured_at_utc-new.decision_observed_at_utc))
  ) asc
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

  if new.action='EXECUTE_NOW' then
    if new.quote_complete is not true
       or new.entry_cross_price is null
       or new.entry_cross_price<=0
    then
      return new;
    end if;

    v_state:='OPEN_PAPER';
    v_fill_status:='FILLED_EXECUTE_NOW_AT_CROSS';
    v_fill_price:=new.entry_cross_price::double precision;
    v_fill_at:=coalesce(new.decision_captured_at_utc,new.frozen_at_utc);
    v_fill_source:='IMMUTABLE_DECISION_QUOTE_ENTRY_CROSS';
  else
    v_state:='PENDING_LIMIT_PAPER';
    v_fill_status:='PENDING_LIMIT';
    v_fill_price:=null;
    v_fill_at:=null;
    v_fill_source:='AWAIT_FORWARD_LIMIT_TRIGGER';
  end if;

  insert into private.alpha_hunter_calibrated_paper_orders_v01(
    paper_order_id,policy_id,execution_event_id,decision_observation_id,
    strategy_instance_id,run_id,symbol,strategy_id,direction,action,
    decision_observed_at_utc,frozen_at_utc,planned_entry_price,stop_price,target_price,
    reward_risk,calibrated_confidence_pct,confidence_lower_95_pct,
    confidence_upper_95_pct,calibration_cohort,state,
    paper_fill_status,paper_fill_price,paper_fill_at_utc,paper_fill_source,
    paper_entry_half_spread_bps,paper_execution_evidence,
    paper_only,live_exchange_order_sent,trade_permission
  ) values (
    'cal-paper-'||md5(p.policy_id||'|'||new.execution_event_id),
    p.policy_id,new.execution_event_id,new.decision_observation_id,
    so.strategy_instance_id,new.decision_run_id,new.symbol,so.strategy_id,
    new.direction,new.action,new.decision_observed_at_utc,new.frozen_at_utc,
    new.planned_entry_price,new.stop_price,new.target_price,new.reward_risk,
    p.calibrated_confidence_pct,p.confidence_lower_95_pct,p.confidence_upper_95_pct,
    p.cohort,v_state,
    v_fill_status,v_fill_price,v_fill_at,v_fill_source,
    new.entry_cross_half_spread_bps::double precision,
    jsonb_build_object(
      'execution_model_version','realistic-paper-execution-v0.1',
      'decision_quote_complete',new.quote_complete,
      'decision_entry_cross_price',new.entry_cross_price,
      'decision_midpoint',new.midpoint,
      'decision_best_bid',new.best_bid,
      'decision_best_ask',new.best_ask,
      'paper_fill_hindsight_permitted',false,
      'live_exchange_order_sent',false,
      'validated_net_cost_model_available',false
    ),
    true,false,false
  )
  on conflict(execution_event_id) do nothing;

  return new;
end;
$function$;

revoke all on function private.alpha_hunter_create_calibrated_paper_order_v02()
from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_calibrated_paper_order_v01
  on public.alpha_hunter_execution_decision_freezes_v01;

drop trigger if exists trg_ah_calibrated_paper_order_v02
  on public.alpha_hunter_execution_decision_freezes_v01;

create trigger trg_ah_calibrated_paper_order_v02
after insert on public.alpha_hunter_execution_decision_freezes_v01
for each row
execute function private.alpha_hunter_create_calibrated_paper_order_v02();

create or replace function private.alpha_hunter_reconcile_calibrated_paper_orders_v01()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  r private.alpha_hunter_calibrated_paper_orders_v01%rowtype;
  o public.alpha_hunter_strategy_forward_outcomes_v01%rowtype;
  v_fill_price double precision;
  v_risk_pct double precision;
  v_target_pct double precision;
  v_gross_return_pct double precision;
  v_gross_r double precision;
  v_filled integer:=0;
  v_closed integer:=0;
  v_not_filled integer:=0;
begin
  for r in
    select *
    from private.alpha_hunter_calibrated_paper_orders_v01
    where state in ('PENDING_LIMIT_PAPER','OPEN_PAPER')
    order by paper_order_created_at_utc
  loop
    if r.state='PENDING_LIMIT_PAPER' then
      select x.* into o
      from public.alpha_hunter_strategy_forward_outcomes_v01 x
      where x.episode_id=r.strategy_instance_id
        and x.entry_trigger_status='TRIGGERED_LIMIT'
        and x.fill_price is not null
      order by x.horizon_hours asc,x.evaluated_at_utc asc
      limit 1;

      if o.episode_id is not null then
        update private.alpha_hunter_calibrated_paper_orders_v01
        set state='OPEN_PAPER',
            paper_fill_status='FILLED_LIMIT_FROM_FORWARD_PATH',
            paper_fill_price=o.fill_price,
            paper_fill_at_utc=coalesce(
              o.entry_trigger_known_at_utc,
              o.entry_trigger_candle_open_utc,
              o.evaluated_at_utc
            ),
            paper_fill_source='FORWARD_OUTCOME_TRIGGERED_LIMIT',
            paper_fill_horizon_hours=o.horizon_hours,
            last_reconciled_at_utc=clock_timestamp(),
            paper_execution_evidence=
              paper_execution_evidence||jsonb_build_object(
                'limit_trigger_status',o.entry_trigger_status,
                'limit_trigger_candle_open_utc',o.entry_trigger_candle_open_utc,
                'limit_trigger_known_at_utc',o.entry_trigger_known_at_utc,
                'time_to_entry_trigger_minutes',o.time_to_entry_trigger_minutes
              )
        where paper_order_id=r.paper_order_id;

        r.state:='OPEN_PAPER';
        r.paper_fill_price:=o.fill_price;
        v_filled:=v_filled+1;
      else
        select x.* into o
        from public.alpha_hunter_strategy_forward_outcomes_v01 x
        where x.episode_id=r.strategy_instance_id
          and x.horizon_hours=24
        order by x.evaluated_at_utc desc
        limit 1;

        if o.episode_id is not null
           and o.entry_trigger_status='NOT_TRIGGERED_WITHIN_HORIZON'
        then
          update private.alpha_hunter_calibrated_paper_orders_v01
          set state='OUTCOME_AVAILABLE',
              paper_fill_status='NOT_FILLED_WITHIN_24H',
              paper_outcome_class='NO_TRADE_LIMIT_NOT_FILLED',
              paper_outcome_evaluated_at_utc=o.evaluated_at_utc,
              paper_cost_adjustment_status='NO_TRADE',
              last_reconciled_at_utc=clock_timestamp(),
              paper_execution_evidence=
                paper_execution_evidence||jsonb_build_object(
                  'final_entry_trigger_status',o.entry_trigger_status,
                  'paper_trade_counted_as_win_or_loss',false
                )
          where paper_order_id=r.paper_order_id;

          v_not_filled:=v_not_filled+1;
          continue;
        end if;
      end if;
    end if;

    if r.state='OPEN_PAPER' then
      select x.* into o
      from public.alpha_hunter_strategy_forward_outcomes_v01 x
      where x.episode_id=r.strategy_instance_id
        and x.horizon_hours=24
        and x.entry_trigger_status in ('TRIGGERED_LIMIT','TRIGGERED_EXECUTE_NOW')
      order by x.evaluated_at_utc desc
      limit 1;

      if o.episode_id is null then
        update private.alpha_hunter_calibrated_paper_orders_v01
        set last_reconciled_at_utc=clock_timestamp()
        where paper_order_id=r.paper_order_id;
        continue;
      end if;

      select coalesce(
        r.paper_fill_price,
        case
          when r.action='PLACE_LIMIT' then o.fill_price
          else null
        end
      ) into v_fill_price;

      if v_fill_price is null or v_fill_price<=0 then
        update private.alpha_hunter_calibrated_paper_orders_v01
        set paper_fill_status='BLOCKED_MISSING_REALISTIC_FILL_PRICE',
            last_reconciled_at_utc=clock_timestamp()
        where paper_order_id=r.paper_order_id;
        continue;
      end if;

      v_risk_pct:=100.0*abs(v_fill_price-r.stop_price)/v_fill_price;
      v_target_pct:=100.0*abs(r.target_price-v_fill_price)/v_fill_price;

      v_gross_return_pct:=case
        when o.path_outcome_class='STOP_FIRST' then -v_risk_pct
        when o.path_outcome_class='TARGET_FIRST' then v_target_pct
        when o.path_outcome_class='OPEN_AT_HORIZON' and o.endpoint_close_price is not null
          then case
            when r.direction='LONG'
              then 100.0*(o.endpoint_close_price-v_fill_price)/v_fill_price
            else 100.0*(v_fill_price-o.endpoint_close_price)/v_fill_price
          end
        else null
      end;

      v_gross_r:=case
        when v_gross_return_pct is null or v_risk_pct<=0 then null
        else v_gross_return_pct/v_risk_pct
      end;

      update private.alpha_hunter_calibrated_paper_orders_v01
      set state='OUTCOME_AVAILABLE',
          paper_outcome_class=o.path_outcome_class,
          paper_endpoint_price=o.endpoint_close_price,
          paper_gross_return_pct=v_gross_return_pct,
          paper_gross_r=v_gross_r,
          paper_net_return_pct=null,
          paper_net_r=null,
          paper_cost_adjustment_status=
            'BLOCKED_UNVALIDATED_EXECUTION_COST_MODEL',
          paper_outcome_evaluated_at_utc=o.evaluated_at_utc,
          last_reconciled_at_utc=clock_timestamp(),
          paper_execution_evidence=
            paper_execution_evidence||jsonb_build_object(
              'forward_outcome_entry_trigger_status',o.entry_trigger_status,
              'forward_outcome_path_class',o.path_outcome_class,
              'forward_outcome_endpoint_close_price',o.endpoint_close_price,
              'forward_outcome_cost_adjustment_status',o.cost_adjustment_status,
              'realistic_net_r_claim_permitted',false
            )
      where paper_order_id=r.paper_order_id;

      v_closed:=v_closed+1;
    end if;
  end loop;

  return jsonb_build_object(
    'model_version','realistic-paper-execution-v0.1',
    'new_limit_fills',v_filled,
    'closed_24h_outcomes',v_closed,
    'unfilled_limit_orders',v_not_filled,
    'paper_only',true,
    'live_exchange_order_sent',false,
    'realistic_net_r_claim_permitted',false,
    'trade_permission',false
  );
end;
$function$;

revoke all on function private.alpha_hunter_reconcile_calibrated_paper_orders_v01()
from public,anon,authenticated,service_role;
grant execute on function private.alpha_hunter_reconcile_calibrated_paper_orders_v01()
to postgres;

create or replace view private.alpha_hunter_calibrated_paper_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  p.paper_order_id,p.policy_id,p.execution_event_id,p.strategy_instance_id,
  p.run_id,p.symbol,p.strategy_id,p.direction,p.action,
  p.decision_observed_at_utc,p.frozen_at_utc,p.paper_order_created_at_utc,
  p.planned_entry_price,p.stop_price,p.target_price,p.reward_risk,
  p.calibrated_confidence_pct,p.confidence_lower_95_pct,p.confidence_upper_95_pct,
  p.paper_fill_status,p.paper_fill_price,p.paper_fill_at_utc,p.paper_fill_source,
  p.paper_fill_horizon_hours,p.paper_entry_half_spread_bps,
  p.state,p.paper_outcome_class,p.paper_endpoint_price,
  p.paper_gross_return_pct,p.paper_gross_r,
  p.paper_net_return_pct,p.paper_net_r,p.paper_cost_adjustment_status,
  p.paper_outcome_evaluated_at_utc,p.last_reconciled_at_utc,
  case
    when p.paper_fill_status='NOT_FILLED_WITHIN_24H' then 'NO_TRADE'
    when p.state<>'OUTCOME_AVAILABLE' then 'WAITING'
    when p.paper_gross_r>0 then 'PAPER_WIN'
    when p.paper_gross_r<=0 then 'PAPER_LOSS'
    else 'OUTCOME_UNKNOWN'
  end as calibration_result,
  true as paper_only,
  false as live_exchange_order_sent,
  false as realistic_net_r_claim_permitted,
  false as trade_permission
from private.alpha_hunter_calibrated_paper_orders_v01 p;

revoke all on private.alpha_hunter_calibrated_paper_status_v01
from public,anon,authenticated,service_role;
grant select on private.alpha_hunter_calibrated_paper_status_v01
to service_role;

do $cron$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-calibrated-paper-reconcile-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;
end;
$cron$;

select cron.schedule(
  'alpha-hunter-calibrated-paper-reconcile-v01',
  '7,37,57 * * * *',
  $cmd$
    select private.alpha_hunter_reconcile_calibrated_paper_orders_v01();
  $cmd$
);

-- No historical execution-decision freeze is inserted or backfilled here.
