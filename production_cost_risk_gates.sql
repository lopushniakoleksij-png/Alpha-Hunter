-- Alpha Hunter execution-cost and portfolio-risk production gates v0.1
-- Shadow/read-only evidence contracts only. No order submission and no trade permission.

create table if not exists public.alpha_hunter_execution_cost_model_versions (
  cost_model_id text primary key,
  status text not null check (status in ('DRAFT','VALIDATED','ACTIVE','RETIRED')),
  maker_fee_bps double precision,
  taker_fee_bps double precision,
  entry_slippage_bps double precision,
  exit_slippage_bps double precision,
  evidence_reference jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence_reference)='object'),
  validated_at_utc timestamptz,
  activated_at_utc timestamptz,
  model_version text not null,
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  check (status='DRAFT' or (
    maker_fee_bps is not null and maker_fee_bps>=0 and taker_fee_bps is not null and taker_fee_bps>=0 and
    entry_slippage_bps is not null and entry_slippage_bps>=0 and exit_slippage_bps is not null and exit_slippage_bps>=0
  )),
  check (status<>'ACTIVE' or (
    validated_at_utc is not null and activated_at_utc is not null and evidence_reference<>'{}'::jsonb
  ))
);

create table if not exists public.alpha_hunter_execution_cost_evidence (
  cost_evidence_id text primary key,
  control_run_id text not null references public.alpha_hunter_control_plane_runs(control_run_id),
  source_run_id text not null,
  stage_snapshot_id text not null references public.alpha_hunter_money_entry_stage_snapshots(stage_snapshot_id),
  source_bridge_id text not null,
  source_signal_id text,
  captured_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  bid_price double precision,
  ask_price double precision,
  mid_price double precision,
  observed_spread_abs double precision,
  observed_spread_pct double precision,
  funding_rate double precision,
  funding_interval_hours double precision,
  quote_volume_24h double precision,
  liquidity_state text,
  cost_model_id text references public.alpha_hunter_execution_cost_model_versions(cost_model_id),
  cost_model_status text not null,
  maker_fee_bps double precision,
  taker_fee_bps double precision,
  entry_slippage_bps double precision,
  exit_slippage_bps double precision,
  round_trip_taker_cost_bps double precision,
  estimated_cost_r double precision,
  realistic_net_r double precision,
  realistic_net_r_status text not null,
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  model_version text not null default 'execution-cost-evidence-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  unique(stage_snapshot_id)
);

create table if not exists public.alpha_hunter_risk_policy_versions (
  risk_policy_id text primary key,
  status text not null check (status in ('DRAFT','VALIDATED','ACTIVE','RETIRED')),
  risk_per_trade_usdt double precision,
  max_total_open_risk_usdt double precision,
  max_concurrent_positions integer,
  max_correlated_positions integer,
  max_daily_loss_usdt double precision,
  min_liquidation_buffer_pct double precision,
  evidence_reference jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence_reference)='object'),
  validated_at_utc timestamptz,
  activated_at_utc timestamptz,
  model_version text not null,
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  check (status='DRAFT' or (
    risk_per_trade_usdt is not null and risk_per_trade_usdt>0 and max_total_open_risk_usdt is not null and max_total_open_risk_usdt>0 and
    max_concurrent_positions is not null and max_concurrent_positions>0 and max_correlated_positions is not null and max_correlated_positions>0 and
    max_daily_loss_usdt is not null and max_daily_loss_usdt>0 and min_liquidation_buffer_pct is not null and min_liquidation_buffer_pct>0
  )),
  check (status<>'ACTIVE' or (
    validated_at_utc is not null and activated_at_utc is not null and evidence_reference<>'{}'::jsonb
  ))
);

create table if not exists public.alpha_hunter_account_state_snapshots (
  account_snapshot_id text primary key,
  captured_at_utc timestamptz not null,
  equity_usdt double precision,
  available_usdt double precision,
  margin_used_usdt double precision,
  unrealized_pnl_usdt double precision,
  daily_realized_pnl_usdt double precision,
  source text not null,
  connection_status text not null check (connection_status in ('CONNECTED_READ_ONLY','DISCONNECTED','DATA_INSUFFICIENT')),
  schema_validated boolean not null default false,
  complete boolean not null default false,
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);

create table if not exists public.alpha_hunter_open_position_snapshots (
  position_snapshot_id text primary key,
  account_snapshot_id text not null references public.alpha_hunter_account_state_snapshots(account_snapshot_id),
  captured_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  quantity double precision,
  average_entry double precision,
  mark_price double precision,
  liquidation_price double precision,
  notional_usdt double precision,
  unrealized_pnl_usdt double precision,
  source_position_id text,
  structural_stop_price double precision,
  planned_risk_usdt double precision,
  strategy_event_id text,
  source_order_intent_id text,
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);

create table if not exists public.alpha_hunter_portfolio_risk_assessments (
  risk_assessment_id text primary key,
  control_run_id text not null references public.alpha_hunter_control_plane_runs(control_run_id),
  source_run_id text not null,
  stage_snapshot_id text not null references public.alpha_hunter_money_entry_stage_snapshots(stage_snapshot_id),
  cost_evidence_id text references public.alpha_hunter_execution_cost_evidence(cost_evidence_id),
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  stage_status text not null,
  stage_eligible boolean not null,
  risk_policy_id text references public.alpha_hunter_risk_policy_versions(risk_policy_id),
  risk_policy_status text not null,
  cost_model_status text not null,
  account_state_status text not null,
  position_ledger_status text not null,
  risk_decision text not null check (risk_decision in ('BLOCK','ELIGIBLE_FOR_RISK_REVIEW')),
  monetary_risk_usdt double precision,
  candidate_entry double precision,
  stop_price double precision,
  stop_distance_pct double precision,
  derived_position_notional_usdt double precision,
  open_position_count integer,
  aggregate_open_risk_usdt double precision,
  daily_realized_pnl_usdt double precision,
  blockers jsonb not null default '[]'::jsonb check (jsonb_typeof(blockers)='array'),
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  model_version text not null default 'portfolio-risk-veto-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  account_snapshot_id text references public.alpha_hunter_account_state_snapshots(account_snapshot_id),
  current_available_usdt double precision,
  realistic_net_r_status text,
  symbol_position_conflict boolean,
  aggregate_risk_complete boolean,
  unique(stage_snapshot_id)
);

alter table public.alpha_hunter_execution_cost_model_versions enable row level security;
alter table public.alpha_hunter_execution_cost_evidence enable row level security;
alter table public.alpha_hunter_risk_policy_versions enable row level security;
alter table public.alpha_hunter_account_state_snapshots enable row level security;
alter table public.alpha_hunter_open_position_snapshots enable row level security;
alter table public.alpha_hunter_portfolio_risk_assessments enable row level security;

revoke all on table public.alpha_hunter_execution_cost_model_versions from public,anon,authenticated;
revoke all on table public.alpha_hunter_execution_cost_evidence from public,anon,authenticated;
revoke all on table public.alpha_hunter_risk_policy_versions from public,anon,authenticated;
revoke all on table public.alpha_hunter_account_state_snapshots from public,anon,authenticated;
revoke all on table public.alpha_hunter_open_position_snapshots from public,anon,authenticated;
revoke all on table public.alpha_hunter_portfolio_risk_assessments from public,anon,authenticated;

grant select,insert on table public.alpha_hunter_execution_cost_model_versions to service_role;
grant select,insert on table public.alpha_hunter_execution_cost_evidence to service_role;
grant select,insert on table public.alpha_hunter_risk_policy_versions to service_role;
grant select,insert on table public.alpha_hunter_account_state_snapshots to service_role;
grant select,insert on table public.alpha_hunter_open_position_snapshots to service_role;
grant select,insert on table public.alpha_hunter_portfolio_risk_assessments to service_role;

create index if not exists idx_ah_cost_evidence_run on public.alpha_hunter_execution_cost_evidence(control_run_id,created_at desc);
create index if not exists idx_ah_risk_assessments_run on public.alpha_hunter_portfolio_risk_assessments(control_run_id,created_at desc);
create index if not exists idx_ah_account_state_time on public.alpha_hunter_account_state_snapshots(captured_at_utc desc);
create index if not exists idx_ah_open_positions_account on public.alpha_hunter_open_position_snapshots(account_snapshot_id,symbol);

drop trigger if exists trg_ah_cost_models_append_only on public.alpha_hunter_execution_cost_model_versions;
create trigger trg_ah_cost_models_append_only before update or delete on public.alpha_hunter_execution_cost_model_versions for each row execute function private.alpha_hunter_block_append_only_mutation();
drop trigger if exists trg_ah_cost_evidence_append_only on public.alpha_hunter_execution_cost_evidence;
create trigger trg_ah_cost_evidence_append_only before update or delete on public.alpha_hunter_execution_cost_evidence for each row execute function private.alpha_hunter_block_append_only_mutation();
drop trigger if exists trg_ah_risk_policies_append_only on public.alpha_hunter_risk_policy_versions;
create trigger trg_ah_risk_policies_append_only before update or delete on public.alpha_hunter_risk_policy_versions for each row execute function private.alpha_hunter_block_append_only_mutation();
drop trigger if exists trg_ah_account_state_append_only on public.alpha_hunter_account_state_snapshots;
create trigger trg_ah_account_state_append_only before update or delete on public.alpha_hunter_account_state_snapshots for each row execute function private.alpha_hunter_block_append_only_mutation();
drop trigger if exists trg_ah_open_positions_append_only on public.alpha_hunter_open_position_snapshots;
create trigger trg_ah_open_positions_append_only before update or delete on public.alpha_hunter_open_position_snapshots for each row execute function private.alpha_hunter_block_append_only_mutation();
drop trigger if exists trg_ah_risk_assessments_append_only on public.alpha_hunter_portfolio_risk_assessments;
create trigger trg_ah_risk_assessments_append_only before update or delete on public.alpha_hunter_portfolio_risk_assessments for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_text_float(p_value text)
returns double precision
language sql
immutable
set search_path = ''
as $$
  select case when p_value ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' then p_value::double precision else null end;
$$;
revoke all on function private.alpha_hunter_text_float(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_text_float(text) to service_role;

create or replace function private.alpha_hunter_capture_execution_cost_evidence(p_control_run_id text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_cost_model_id text;
  v_maker_fee_bps double precision;
  v_taker_fee_bps double precision;
  v_entry_slippage_bps double precision;
  v_exit_slippage_bps double precision;
  v_cost_model_status text := 'NO_ACTIVE_VALIDATED_COST_MODEL';
  v_inserted integer := 0;
  v_source_run_id text;
  v_status_counts jsonb := '{}'::jsonb;
begin
  if not exists(select 1 from public.alpha_hunter_control_plane_runs r where r.control_run_id=p_control_run_id) then
    raise exception 'control run does not exist: %',p_control_run_id;
  end if;

  select c.cost_model_id,c.maker_fee_bps,c.taker_fee_bps,c.entry_slippage_bps,c.exit_slippage_bps
  into v_cost_model_id,v_maker_fee_bps,v_taker_fee_bps,v_entry_slippage_bps,v_exit_slippage_bps
  from public.alpha_hunter_execution_cost_model_versions c
  where c.status='ACTIVE' and c.validated_at_utc is not null and c.activated_at_utc is not null
  order by c.activated_at_utc desc limit 1;
  if v_cost_model_id is not null then v_cost_model_status := 'ACTIVE_VALIDATED_COST_MODEL'; end if;

  select s.source_run_id into v_source_run_id
  from public.alpha_hunter_money_entry_stage_snapshots s
  where s.control_run_id=p_control_run_id order by s.created_at desc limit 1;

  with base as (
    select s.*,coalesce(sf.source_payload,'{}'::jsonb) source_payload
    from public.alpha_hunter_money_entry_stage_snapshots s
    left join lateral (
      select f.source_payload from public.alpha_hunter_signal_features f
      where (s.source_signal_id is not null and f.signal_id=s.source_signal_id)
         or (s.source_signal_id is null and f.run_id=s.source_run_id and f.symbol=s.symbol)
      order by case when s.source_signal_id is not null and f.signal_id=s.source_signal_id then 0 else 1 end,f.captured_at_utc desc limit 1
    ) sf on true
    where s.control_run_id=p_control_run_id
  ), normalized as (
    select b.*,
      private.alpha_hunter_text_float(b.source_payload->>'bid_price') bid,
      private.alpha_hunter_text_float(b.source_payload->>'ask_price') ask,
      private.alpha_hunter_text_float(b.source_payload#>>'{behaviour,spread_pct}') spread_pct_source,
      private.alpha_hunter_text_float(b.source_payload->>'funding_rate') funding,
      private.alpha_hunter_text_float(b.source_payload->>'funding_interval_hours') funding_hours,
      private.alpha_hunter_text_float(b.source_payload->>'quote_volume_24h') quote_volume
    from base b
  ), ins as (
    insert into public.alpha_hunter_execution_cost_evidence(
      cost_evidence_id,control_run_id,source_run_id,stage_snapshot_id,source_bridge_id,source_signal_id,captured_at_utc,symbol,direction,
      bid_price,ask_price,mid_price,observed_spread_abs,observed_spread_pct,funding_rate,funding_interval_hours,quote_volume_24h,liquidity_state,
      cost_model_id,cost_model_status,maker_fee_bps,taker_fee_bps,entry_slippage_bps,exit_slippage_bps,round_trip_taker_cost_bps,estimated_cost_r,
      realistic_net_r,realistic_net_r_status,evidence,model_version,shadow_only,trade_permission
    )
    select md5('execution-cost-evidence-v0.1|'||n.stage_snapshot_id),p_control_run_id,n.source_run_id,n.stage_snapshot_id,n.source_bridge_id,n.source_signal_id,
      n.source_captured_at_utc,n.symbol,n.direction,n.bid,n.ask,
      case when n.bid is not null and n.ask is not null and n.bid>0 and n.ask>=n.bid then (n.bid+n.ask)/2.0 end,
      case when n.bid is not null and n.ask is not null and n.bid>0 and n.ask>=n.bid then n.ask-n.bid end,
      coalesce(n.spread_pct_source,case when n.bid is not null and n.ask is not null and n.bid>0 and n.ask>=n.bid then (n.ask-n.bid)/((n.ask+n.bid)/2.0)*100.0 end),
      n.funding,n.funding_hours,n.quote_volume,n.liquidity_state,v_cost_model_id,v_cost_model_status,v_maker_fee_bps,v_taker_fee_bps,v_entry_slippage_bps,v_exit_slippage_bps,
      case when v_cost_model_id is not null then 2.0*v_taker_fee_bps+v_entry_slippage_bps+v_exit_slippage_bps end,
      case when v_cost_model_id is not null and n.stop_distance_pct is not null and n.stop_distance_pct>0
        then ((2.0*v_taker_fee_bps+v_entry_slippage_bps+v_exit_slippage_bps)/100.0)/n.stop_distance_pct end,
      null,
      case
        when v_cost_model_id is null then 'WITHHELD_NO_ACTIVE_VALIDATED_COST_MODEL'
        when n.stop_distance_pct is null or n.stop_distance_pct<=0 then 'WITHHELD_STOP_DISTANCE_UNAVAILABLE'
        when n.funding is null then 'WITHHELD_FUNDING_EVIDENCE_UNAVAILABLE'
        else 'WITHHELD_HOLD_TIME_AND_FUNDING_PATH_UNVERIFIED'
      end,
      jsonb_build_object(
        'source','CONTEMPORANEOUS_SCANNER_SNAPSHOT','spread_observed',n.bid is not null and n.ask is not null,'funding_observed',n.funding is not null,
        'fee_model_verified',v_cost_model_id is not null,'funding_included_in_realistic_net_r',false,'realistic_net_r_claim_permitted',false,
        'no_fee_or_slippage_values_invented',true
      ),'execution-cost-evidence-v0.1',true,false
    from normalized n
    on conflict(stage_snapshot_id) do nothing returning 1
  ) select count(*) into v_inserted from ins;

  select coalesce(jsonb_object_agg(cost_model_status,n),'{}'::jsonb) into v_status_counts
  from (select cost_model_status,count(*)::integer n from public.alpha_hunter_execution_cost_evidence where control_run_id=p_control_run_id group by cost_model_status) q;

  return jsonb_build_object(
    'mode','EXECUTION_COST_EVIDENCE','control_run_id',p_control_run_id,'run_id',v_source_run_id,'rows_inserted',v_inserted,
    'cost_model_id',v_cost_model_id,'cost_model_status',v_cost_model_status,'status_counts',v_status_counts,
    'realistic_net_r_status','WITHHELD_UNTIL_VERIFIED_FULL_COST_PATH','shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_capture_execution_cost_evidence(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_execution_cost_evidence(text) to service_role;

create or replace function private.alpha_hunter_assess_portfolio_risk(p_control_run_id text)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_policy_id text;v_risk_per_trade double precision;v_max_total_risk double precision;v_max_positions integer;v_max_correlated integer;
  v_max_daily_loss double precision;v_min_liq_buffer double precision;v_policy_status text:='NO_ACTIVE_VALIDATED_RISK_POLICY';
  v_account record;v_account_status text:='NO_RECENT_VERIFIED_ACCOUNT_STATE';v_position_status text:='POSITION_LEDGER_NOT_CONNECTED';
  v_open_count integer;v_aggregate_risk double precision;v_aggregate_complete boolean:=false;v_inserted integer:=0;v_source_run_id text;
  v_decision_counts jsonb:='{}'::jsonb;
begin
  if not exists(select 1 from public.alpha_hunter_control_plane_runs r where r.control_run_id=p_control_run_id) then
    raise exception 'control run does not exist: %',p_control_run_id;
  end if;

  select p.risk_policy_id,p.risk_per_trade_usdt,p.max_total_open_risk_usdt,p.max_concurrent_positions,p.max_correlated_positions,p.max_daily_loss_usdt,p.min_liquidation_buffer_pct
  into v_policy_id,v_risk_per_trade,v_max_total_risk,v_max_positions,v_max_correlated,v_max_daily_loss,v_min_liq_buffer
  from public.alpha_hunter_risk_policy_versions p
  where p.status='ACTIVE' and p.validated_at_utc is not null and p.activated_at_utc is not null
  order by p.activated_at_utc desc limit 1;
  if v_policy_id is not null then v_policy_status:='ACTIVE_VALIDATED_RISK_POLICY'; end if;

  select a.* into v_account
  from public.alpha_hunter_account_state_snapshots a
  where a.connection_status='CONNECTED_READ_ONLY' and a.complete=true and a.schema_validated=true
    and clock_timestamp()-a.captured_at_utc<=interval '90 minutes'
  order by a.captured_at_utc desc limit 1;

  if found then
    v_account_status:='CONNECTED_READ_ONLY_COMPLETE';
    select count(*)::integer,coalesce(sum(p.planned_risk_usdt),0),coalesce(bool_and(p.planned_risk_usdt is not null),true)
    into v_open_count,v_aggregate_risk,v_aggregate_complete
    from public.alpha_hunter_open_position_snapshots p where p.account_snapshot_id=v_account.account_snapshot_id;
    v_position_status:=case when v_aggregate_complete then 'VERIFIED_SNAPSHOT' else 'INCOMPLETE_RISK_FIELDS' end;
  else
    v_open_count:=null;v_aggregate_risk:=null;v_aggregate_complete:=false;
  end if;

  select s.source_run_id into v_source_run_id from public.alpha_hunter_money_entry_stage_snapshots s
  where s.control_run_id=p_control_run_id order by s.created_at desc limit 1;

  with base as (
    select s.*,c.cost_evidence_id,c.cost_model_status,c.realistic_net_r_status,
      case when v_account.account_snapshot_id is not null then exists(
        select 1 from public.alpha_hunter_open_position_snapshots p where p.account_snapshot_id=v_account.account_snapshot_id and p.symbol=s.symbol
      ) else null end symbol_conflict
    from public.alpha_hunter_money_entry_stage_snapshots s
    left join public.alpha_hunter_execution_cost_evidence c on c.stage_snapshot_id=s.stage_snapshot_id
    where s.control_run_id=p_control_run_id
  ), evaluated as (
    select b.*,
      (select coalesce(jsonb_agg(x order by ord),'[]'::jsonb)
       from unnest(array[
         case when b.stage_eligible is not true then 'MONEY_ENTRY_STAGE_NOT_ELIGIBLE' end,
         case when v_policy_id is null then 'NO_ACTIVE_VALIDATED_RISK_POLICY' end,
         case when b.cost_evidence_id is null then 'COST_EVIDENCE_MISSING' end,
         case when coalesce(b.cost_model_status,'')<>'ACTIVE_VALIDATED_COST_MODEL' then 'NO_ACTIVE_VALIDATED_COST_MODEL' end,
         case when coalesce(b.realistic_net_r_status,'') not in ('VERIFIED_FULL_COST_PATH','VERIFIED_NET_R') then 'REALISTIC_NET_R_NOT_VERIFIED' end,
         case when v_account.account_snapshot_id is null then 'ACCOUNT_STATE_NOT_CONNECTED_OR_STALE' end,
         case when v_account.account_snapshot_id is not null and v_position_status<>'VERIFIED_SNAPSHOT' then 'POSITION_LEDGER_NOT_VERIFIED' end,
         case when b.stop_distance_pct is null or b.stop_distance_pct<=0 then 'STOP_DISTANCE_MISSING_OR_INVALID' end,
         case when b.symbol_conflict is true then 'SYMBOL_ALREADY_OPEN' end,
         case when v_account.account_snapshot_id is not null and v_policy_id is not null and v_open_count>=v_max_positions then 'MAX_CONCURRENT_POSITIONS_REACHED' end,
         case when v_account.account_snapshot_id is not null and v_policy_id is not null and v_aggregate_complete and v_aggregate_risk+v_risk_per_trade>v_max_total_risk then 'MAX_TOTAL_OPEN_RISK_EXCEEDED' end,
         case when v_account.account_snapshot_id is not null and v_policy_id is not null and v_account.daily_realized_pnl_usdt is not null and v_account.daily_realized_pnl_usdt<=-v_max_daily_loss then 'DAILY_LOSS_CIRCUIT_BREAKER' end
       ]) with ordinality u(x,ord) where x is not null) blockers_eval
    from base b
  ), ins as (
    insert into public.alpha_hunter_portfolio_risk_assessments(
      risk_assessment_id,control_run_id,source_run_id,stage_snapshot_id,cost_evidence_id,symbol,direction,stage_status,stage_eligible,
      risk_policy_id,risk_policy_status,cost_model_status,account_state_status,position_ledger_status,risk_decision,monetary_risk_usdt,
      candidate_entry,stop_price,stop_distance_pct,derived_position_notional_usdt,open_position_count,aggregate_open_risk_usdt,daily_realized_pnl_usdt,
      blockers,evidence,model_version,shadow_only,trade_permission,account_snapshot_id,current_available_usdt,realistic_net_r_status,symbol_position_conflict,aggregate_risk_complete
    )
    select md5('portfolio-risk-veto-v0.1|'||e.stage_snapshot_id),p_control_run_id,e.source_run_id,e.stage_snapshot_id,e.cost_evidence_id,e.symbol,e.direction,e.stage_status,e.stage_eligible,
      v_policy_id,v_policy_status,coalesce(e.cost_model_status,'NO_COST_EVIDENCE'),v_account_status,v_position_status,
      case when jsonb_array_length(e.blockers_eval)=0 then 'ELIGIBLE_FOR_RISK_REVIEW' else 'BLOCK' end,
      case when v_policy_id is not null then v_risk_per_trade end,e.candidate_entry,e.stop_price,e.stop_distance_pct,
      case when v_policy_id is not null and e.stop_distance_pct is not null and e.stop_distance_pct>0 then v_risk_per_trade/(e.stop_distance_pct/100.0) end,
      v_open_count,v_aggregate_risk,case when v_account.account_snapshot_id is not null then v_account.daily_realized_pnl_usdt end,e.blockers_eval,
      jsonb_build_object(
        'risk_is_veto_only',true,'leverage_selected',false,'leverage_must_come_after_structural_stop_and_position_size',true,
        'account_source',case when v_account.account_snapshot_id is null then null else v_account.source end,
        'max_correlated_positions_policy',case when v_policy_id is null then null else v_max_correlated end,
        'min_liquidation_buffer_pct_policy',case when v_policy_id is null then null else v_min_liq_buffer end,
        'correlation_model_status','NOT_YET_CONNECTED','no_order_permission_granted',true
      ),'portfolio-risk-veto-v0.1',true,false,
      v_account.account_snapshot_id,case when v_account.account_snapshot_id is not null then v_account.available_usdt end,
      e.realistic_net_r_status,e.symbol_conflict,v_aggregate_complete
    from evaluated e
    on conflict(stage_snapshot_id) do nothing returning 1
  ) select count(*) into v_inserted from ins;

  select coalesce(jsonb_object_agg(risk_decision,n),'{}'::jsonb) into v_decision_counts
  from (select risk_decision,count(*)::integer n from public.alpha_hunter_portfolio_risk_assessments where control_run_id=p_control_run_id group by risk_decision) q;

  return jsonb_build_object(
    'mode','PORTFOLIO_RISK_VETO','control_run_id',p_control_run_id,'run_id',v_source_run_id,'rows_inserted',v_inserted,
    'risk_policy_id',v_policy_id,'risk_policy_status',v_policy_status,'account_state_status',v_account_status,
    'position_ledger_status',v_position_status,'decision_counts',v_decision_counts,
    'execution_authorized',false,'shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_assess_portfolio_risk(text) from public,anon,authenticated;
grant execute on function private.alpha_hunter_assess_portfolio_risk(text) to service_role;
