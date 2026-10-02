begin;

-- Alpha Hunter paper protective exit reconciliation v0.4 (Release 2.8).
-- Paper-only SL/TP lifecycle closure. No exchange-writing authority is added.

create table if not exists public.alpha_hunter_paper_exit_attempts_v04 (
  attempt_id text primary key,
  entry_order_id text not null
    references public.alpha_hunter_paper_orders_v02(order_id) on delete restrict,
  decision_id text not null
    references public.alpha_hunter_paper_decisions_v01(decision_id) on delete restrict,
  source_run_id text not null
    references public.alpha_hunter_snapshots(run_id) on delete restrict,
  observed_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  best_bid numeric,
  best_ask numeric,
  best_bid_size numeric,
  best_ask_size numeric,
  outcome text not null check (
    outcome in (
      'INPUT_MISSING','NO_TRIGGER','STOP_TRIGGERED','TARGET_TRIGGERED','AMBIGUOUS'
    )
  ),
  triggered_protection_type text check (
    triggered_protection_type is null
    or triggered_protection_type in ('STOP_LOSS','TAKE_PROFIT')
  ),
  blockers jsonb not null default '[]'::jsonb check (jsonb_typeof(blockers)='array'),
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check (paper_only=true),
  exchange_authority boolean not null default false check (exchange_authority=false),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  unique(entry_order_id,source_run_id)
);

create table if not exists public.alpha_hunter_paper_exit_fills_v04 (
  exit_fill_id text primary key,
  entry_order_id text not null unique
    references public.alpha_hunter_paper_orders_v02(order_id) on delete restrict,
  decision_id text not null
    references public.alpha_hunter_paper_decisions_v01(decision_id) on delete restrict,
  source_run_id text not null
    references public.alpha_hunter_snapshots(run_id) on delete restrict,
  triggered_protective_order_id text not null unique
    references public.alpha_hunter_paper_protective_orders_v03(protective_order_id)
    on delete restrict,
  protection_type text not null
    check (protection_type in ('STOP_LOSS','TAKE_PROFIT')),
  filled_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  side text not null check (side in ('BUY','SELL')),
  quantity numeric not null check (quantity > 0),
  entry_average_fill_price numeric not null check (entry_average_fill_price > 0),
  exit_price numeric not null check (exit_price > 0),
  notional_usdt numeric not null check (notional_usdt > 0),
  midpoint_reference numeric not null check (midpoint_reference > 0),
  cross_price_reference numeric not null check (cross_price_reference > 0),
  spread_cost_usdt numeric not null check (spread_cost_usdt >= 0),
  slippage_bps numeric not null check (slippage_bps >= 0),
  slippage_cost_usdt numeric not null check (slippage_cost_usdt >= 0),
  fee_bps numeric not null check (fee_bps >= 0),
  fee_usdt numeric not null check (fee_usdt >= 0),
  entry_costs_usdt numeric not null check (entry_costs_usdt >= 0),
  exit_costs_usdt numeric not null check (exit_costs_usdt >= 0),
  gross_pnl_usdt numeric not null,
  paper_net_pnl_ex_funding numeric not null,
  planned_risk_usdt numeric not null check (planned_risk_usdt > 0),
  gross_r numeric not null,
  net_r_ex_funding numeric not null,
  funding_bound boolean not null default false check (funding_bound=false),
  full_economic_pnl_claim_permitted boolean not null default false
    check (full_economic_pnl_claim_permitted=false),
  liquidity_source text not null check (
    liquidity_source in (
      'BITGET_TOP_OF_BOOK_SNAPSHOT',
      'BITGET_PUBLIC_ALL_TICKERS_RECONCILIATION_CAPTURE'
    )
  ),
  model_quality text not null check (
    model_quality='DETERMINISTIC_PAPER_MODEL_NOT_EXCHANGE_EXECUTION'
  ),
  paper_only boolean not null default true check (paper_only=true),
  exchange_authority boolean not null default false check (exchange_authority=false),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check (
    (direction='LONG' and side='SELL')
    or (direction='SHORT' and side='BUY')
  )
);

create index if not exists idx_ah_paper_exit_attempt_run_v04
  on public.alpha_hunter_paper_exit_attempts_v04(source_run_id,observed_at_utc);
create index if not exists idx_ah_paper_exit_fill_decision_v04
  on public.alpha_hunter_paper_exit_fills_v04(decision_id,filled_at_utc);

alter table public.alpha_hunter_paper_exit_attempts_v04 enable row level security;
alter table public.alpha_hunter_paper_exit_fills_v04 enable row level security;

revoke all on table public.alpha_hunter_paper_exit_attempts_v04
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_paper_exit_fills_v04
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_paper_exit_attempts_v04 to service_role;
grant select,insert on table public.alpha_hunter_paper_exit_fills_v04 to service_role;

drop trigger if exists trg_ah_paper_exit_attempt_append_only_v04
  on public.alpha_hunter_paper_exit_attempts_v04;
create trigger trg_ah_paper_exit_attempt_append_only_v04
before update or delete on public.alpha_hunter_paper_exit_attempts_v04
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

drop trigger if exists trg_ah_paper_exit_fill_append_only_v04
  on public.alpha_hunter_paper_exit_fills_v04;
create trigger trg_ah_paper_exit_fill_append_only_v04
before update or delete on public.alpha_hunter_paper_exit_fills_v04
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

create or replace function private.alpha_hunter_validate_paper_exit_v04()
returns trigger
language plpgsql
security invoker
set search_path=''
as $$
declare
  ordered numeric;
  filled numeric;
  expected_decision text;
  protection_decision text;
  protection_entry text;
  protection_type text;
  latest_state text;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'alpha-hunter-paper-exit:' || new.entry_order_id,
      0
    )
  );

  select o.quantity,o.decision_id
    into ordered,expected_decision
  from public.alpha_hunter_paper_orders_v02 o
  where o.order_id=new.entry_order_id;

  select coalesce(sum(f.quantity),0)
    into filled
  from public.alpha_hunter_paper_fills_v02 f
  where f.order_id=new.entry_order_id;

  select p.decision_id,p.entry_order_id,p.protection_type
    into protection_decision,protection_entry,protection_type
  from public.alpha_hunter_paper_protective_orders_v03 p
  where p.protective_order_id=new.triggered_protective_order_id;

  select e.state
    into latest_state
  from public.alpha_hunter_paper_events_v01 e
  where e.decision_id=new.decision_id
  order by e.sequence desc,e.created_at desc
  limit 1;

  if ordered is null or expected_decision<>new.decision_id then
    raise exception 'paper exit does not match entry order decision';
  end if;
  if filled < ordered-0.000000000001 then
    raise exception 'paper exit forbidden before complete entry fill';
  end if;
  if new.quantity > filled+0.000000000001
     or abs(new.quantity-ordered)>0.000000000001 then
    raise exception 'paper exit quantity must close complete entry quantity';
  end if;
  if protection_decision<>new.decision_id
     or protection_entry<>new.entry_order_id
     or protection_type<>new.protection_type then
    raise exception 'paper exit trigger does not match protective order';
  end if;
  if latest_state<>'FILLED' then
    raise exception 'paper exit requires latest lifecycle state FILLED';
  end if;

  return new;
end;
$$;

revoke all on function private.alpha_hunter_validate_paper_exit_v04()
  from public,anon,authenticated;

drop trigger if exists trg_ah_validate_paper_exit_v04
  on public.alpha_hunter_paper_exit_fills_v04;
create trigger trg_ah_validate_paper_exit_v04
before insert on public.alpha_hunter_paper_exit_fills_v04
for each row execute function private.alpha_hunter_validate_paper_exit_v04();

create or replace view public.alpha_hunter_paper_protection_open_v04
with (security_invoker=true,security_barrier=true)
as
with latest_event as (
  select distinct on (e.decision_id)
    e.decision_id,e.sequence,e.state,e.occurred_at_utc
  from public.alpha_hunter_paper_events_v01 e
  order by e.decision_id,e.sequence desc,e.created_at desc
),
entry_fill as (
  select
    f.order_id,
    sum(f.quantity) as filled_quantity,
    sum(f.quantity*f.fill_price)/nullif(sum(f.quantity),0)
      as average_entry_fill_price,
    sum(f.fee_usdt) as entry_fee_usdt,
    sum(f.spread_cost_usdt) as entry_spread_cost_usdt,
    sum(f.slippage_cost_usdt) as entry_slippage_cost_usdt,
    max(f.filled_at_utc) as entry_completed_at_utc,
    (array_agg(f.source_run_id order by f.fill_sequence desc))[1]
      as entry_completed_source_run_id
  from public.alpha_hunter_paper_fills_v02 f
  group by f.order_id
),
protection as (
  select
    p.entry_order_id,
    count(*)::integer as protection_count,
    max(p.protective_order_id) filter(where p.protection_type='STOP_LOSS')
      as stop_protective_order_id,
    max(p.trigger_price) filter(where p.protection_type='STOP_LOSS')
      as stop_trigger_price,
    max(p.protective_order_id) filter(where p.protection_type='TAKE_PROFIT')
      as target_protective_order_id,
    max(p.trigger_price) filter(where p.protection_type='TAKE_PROFIT')
      as target_trigger_price
  from public.alpha_hunter_paper_protective_orders_v03 p
  group by p.entry_order_id
)
select
  o.order_id as entry_order_id,
  o.decision_id,
  o.symbol,
  o.direction,
  o.quantity as entry_quantity,
  ef.average_entry_fill_price,
  ef.entry_fee_usdt,
  ef.entry_spread_cost_usdt,
  ef.entry_slippage_cost_usdt,
  ef.entry_completed_at_utc,
  ef.entry_completed_source_run_id,
  o.planned_risk_usdt,
  o.public_taker_fee_bps,
  pr.protection_count,
  pr.stop_protective_order_id,
  pr.stop_trigger_price,
  pr.target_protective_order_id,
  pr.target_trigger_price,
  le.sequence as event_sequence,
  le.occurred_at_utc as filled_state_at_utc,
  o.paper_only,
  o.exchange_authority,
  o.trade_permission,
  o.order_path
from public.alpha_hunter_paper_orders_v02 o
join entry_fill ef on ef.order_id=o.order_id
join protection pr on pr.entry_order_id=o.order_id
join latest_event le on le.decision_id=o.decision_id
left join public.alpha_hunter_paper_exit_fills_v04 x
  on x.entry_order_id=o.order_id
where ef.filled_quantity >= o.quantity-0.000000000001
  and le.state='FILLED'
  and x.entry_order_id is null;

revoke all on public.alpha_hunter_paper_protection_open_v04
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_protection_open_v04 to service_role;

create or replace view public.alpha_hunter_paper_protection_current_v04
with (security_invoker=true,security_barrier=true)
as
select
  p.protective_order_id,
  p.entry_order_id,
  p.decision_id,
  p.created_at_utc,
  p.symbol,
  p.direction,
  p.protection_type,
  p.side,
  p.trigger_price,
  p.quantity,
  case
    when x.exit_fill_id is null then 'ACTIVE_PAPER'
    when x.triggered_protective_order_id=p.protective_order_id
      then 'TRIGGERED_PAPER'
    else 'CANCELLED_OCO'
  end as derived_status,
  x.exit_fill_id,
  x.filled_at_utc as exit_filled_at_utc,
  p.paper_only,
  p.exchange_authority,
  p.trade_permission,
  p.order_path
from public.alpha_hunter_paper_protective_orders_v03 p
left join public.alpha_hunter_paper_exit_fills_v04 x
  on x.entry_order_id=p.entry_order_id;

revoke all on public.alpha_hunter_paper_protection_current_v04
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_protection_current_v04 to service_role;

create or replace view public.alpha_hunter_paper_completed_trades_v04
with (security_invoker=true,security_barrier=true)
as
select
  x.exit_fill_id,
  x.entry_order_id,
  x.decision_id,
  d.run_id as entry_decision_run_id,
  x.source_run_id as exit_source_run_id,
  x.symbol,
  x.direction,
  x.protection_type as exit_reason,
  x.filled_at_utc as closed_at_utc,
  x.quantity,
  x.entry_average_fill_price,
  x.exit_price,
  x.gross_pnl_usdt,
  x.entry_costs_usdt,
  x.exit_costs_usdt,
  x.paper_net_pnl_ex_funding,
  x.planned_risk_usdt,
  x.gross_r,
  x.net_r_ex_funding,
  x.funding_bound,
  x.full_economic_pnl_claim_permitted,
  x.liquidity_source,
  x.model_quality,
  x.paper_only,
  x.exchange_authority,
  x.trade_permission,
  x.order_path
from public.alpha_hunter_paper_exit_fills_v04 x
join public.alpha_hunter_paper_decisions_v01 d using (decision_id);

revoke all on public.alpha_hunter_paper_completed_trades_v04
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trades_v04 to service_role;

create or replace function public.alpha_hunter_commit_paper_exit_reconciliation_v04(
  attempt_rows jsonb,
  exit_fill_rows jsonb,
  event_rows jsonb
)
returns void
language plpgsql
security invoker
set search_path=''
as $$
begin
  if jsonb_typeof(attempt_rows)<>'array'
     or jsonb_typeof(exit_fill_rows)<>'array'
     or jsonb_typeof(event_rows)<>'array' then
    raise exception 'paper exit reconciliation payloads must be JSON arrays';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('alpha-hunter-paper-exit-reconciliation-v04',0)
  );

  select coalesce(pg_catalog.jsonb_agg(j),'[]'::jsonb)
    into attempt_rows
  from pg_catalog.jsonb_array_elements(attempt_rows) j
  where not exists (
    select 1
    from public.alpha_hunter_paper_exit_attempts_v04 a
    where a.attempt_id=j->>'attempt_id'
  );

  if pg_catalog.jsonb_array_length(attempt_rows)=0 then
    return;
  end if;

  insert into public.alpha_hunter_paper_exit_attempts_v04 (
    attempt_id,entry_order_id,decision_id,source_run_id,observed_at_utc,
    symbol,direction,best_bid,best_ask,best_bid_size,best_ask_size,outcome,
    triggered_protection_type,blockers,evidence,paper_only,exchange_authority,
    trade_permission,order_path
  )
  select
    j->>'attempt_id',j->>'entry_order_id',j->>'decision_id',j->>'source_run_id',
    (j->>'observed_at_utc')::timestamptz,j->>'symbol',j->>'direction',
    (j->>'best_bid')::numeric,(j->>'best_ask')::numeric,
    (j->>'best_bid_size')::numeric,(j->>'best_ask_size')::numeric,
    j->>'outcome',j->>'triggered_protection_type',j->'blockers',j->'evidence',
    (j->>'paper_only')::boolean,(j->>'exchange_authority')::boolean,
    (j->>'trade_permission')::boolean,j->>'order_path'
  from pg_catalog.jsonb_array_elements(attempt_rows) j;

  insert into public.alpha_hunter_paper_exit_fills_v04 (
    exit_fill_id,entry_order_id,decision_id,source_run_id,
    triggered_protective_order_id,protection_type,filled_at_utc,symbol,
    direction,side,quantity,entry_average_fill_price,exit_price,notional_usdt,
    midpoint_reference,cross_price_reference,spread_cost_usdt,slippage_bps,
    slippage_cost_usdt,fee_bps,fee_usdt,entry_costs_usdt,exit_costs_usdt,
    gross_pnl_usdt,paper_net_pnl_ex_funding,planned_risk_usdt,gross_r,
    net_r_ex_funding,funding_bound,full_economic_pnl_claim_permitted,
    liquidity_source,model_quality,paper_only,exchange_authority,
    trade_permission,order_path
  )
  select
    j->>'exit_fill_id',j->>'entry_order_id',j->>'decision_id',
    j->>'source_run_id',j->>'triggered_protective_order_id',
    j->>'protection_type',(j->>'filled_at_utc')::timestamptz,
    j->>'symbol',j->>'direction',j->>'side',(j->>'quantity')::numeric,
    (j->>'entry_average_fill_price')::numeric,(j->>'exit_price')::numeric,
    (j->>'notional_usdt')::numeric,(j->>'midpoint_reference')::numeric,
    (j->>'cross_price_reference')::numeric,(j->>'spread_cost_usdt')::numeric,
    (j->>'slippage_bps')::numeric,(j->>'slippage_cost_usdt')::numeric,
    (j->>'fee_bps')::numeric,(j->>'fee_usdt')::numeric,
    (j->>'entry_costs_usdt')::numeric,(j->>'exit_costs_usdt')::numeric,
    (j->>'gross_pnl_usdt')::numeric,(j->>'paper_net_pnl_ex_funding')::numeric,
    (j->>'planned_risk_usdt')::numeric,(j->>'gross_r')::numeric,
    (j->>'net_r_ex_funding')::numeric,(j->>'funding_bound')::boolean,
    (j->>'full_economic_pnl_claim_permitted')::boolean,
    j->>'liquidity_source',j->>'model_quality',(j->>'paper_only')::boolean,
    (j->>'exchange_authority')::boolean,(j->>'trade_permission')::boolean,
    j->>'order_path'
  from pg_catalog.jsonb_array_elements(exit_fill_rows) j
  where exists (
    select 1
    from pg_catalog.jsonb_array_elements(attempt_rows) a
    where a->>'entry_order_id'=j->>'entry_order_id'
      and a->>'source_run_id'=j->>'source_run_id'
      and a->>'outcome' in ('STOP_TRIGGERED','TARGET_TRIGGERED')
  )
  on conflict(entry_order_id) do nothing;

  insert into public.alpha_hunter_paper_events_v01 (
    event_id,decision_id,sequence,occurred_at_utc,event_type,state,payload,
    paper_only,exchange_authority,trade_permission,order_path
  )
  select
    j->>'event_id',j->>'decision_id',(j->>'sequence')::integer,
    (j->>'occurred_at_utc')::timestamptz,j->>'event_type',j->>'state',
    j->'payload',(j->>'paper_only')::boolean,
    (j->>'exchange_authority')::boolean,(j->>'trade_permission')::boolean,
    j->>'order_path'
  from pg_catalog.jsonb_array_elements(event_rows) j
  where exists (
    select 1
    from public.alpha_hunter_paper_exit_fills_v04 x
    where x.exit_fill_id=j->'payload'->>'exit_fill_id'
      and x.decision_id=j->>'decision_id'
  )
  on conflict(event_id) do nothing;
end;
$$;

revoke all on function public.alpha_hunter_commit_paper_exit_reconciliation_v04(
  jsonb,jsonb,jsonb
) from public,anon,authenticated,service_role;
grant execute on function public.alpha_hunter_commit_paper_exit_reconciliation_v04(
  jsonb,jsonb,jsonb
) to service_role;

commit;
