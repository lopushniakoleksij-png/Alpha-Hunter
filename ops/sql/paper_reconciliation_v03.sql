begin;

-- Alpha Hunter paper reconciliation v0.3 (Release 2.3).
-- Cross-scan simulation only. No exchange-writing authority or path is added.

alter table public.alpha_hunter_paper_fills_v02
  add column if not exists source_run_id text
    references public.alpha_hunter_snapshots(run_id) on delete restrict;

create table if not exists public.alpha_hunter_paper_reconciliation_attempts_v03 (
  attempt_id text primary key,
  order_id text not null
    references public.alpha_hunter_paper_orders_v02(order_id) on delete restrict,
  decision_id text not null
    references public.alpha_hunter_paper_decisions_v01(decision_id) on delete restrict,
  source_run_id text not null
    references public.alpha_hunter_snapshots(run_id) on delete restrict,
  observed_at_utc timestamptz not null,
  symbol text not null,
  prior_state text not null check (prior_state in ('SUBMITTED','PARTIALLY_FILLED')),
  prior_filled_quantity numeric not null check (prior_filled_quantity >= 0),
  prior_remaining_quantity numeric not null check (prior_remaining_quantity > 0),
  best_bid numeric,
  best_ask numeric,
  best_bid_size numeric,
  best_ask_size numeric,
  outcome text not null check (outcome in ('INPUT_MISSING','NO_CROSS','FILL_MODELED')),
  blockers jsonb not null default '[]'::jsonb check (jsonb_typeof(blockers)='array'),
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check (paper_only=true),
  exchange_authority boolean not null default false check (exchange_authority=false),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  unique (order_id,source_run_id)
);

create table if not exists public.alpha_hunter_paper_protective_orders_v03 (
  protective_order_id text primary key,
  entry_order_id text not null
    references public.alpha_hunter_paper_orders_v02(order_id) on delete restrict,
  decision_id text not null
    references public.alpha_hunter_paper_decisions_v01(decision_id) on delete restrict,
  activated_by_fill_id text not null
    references public.alpha_hunter_paper_fills_v02(fill_id) on delete restrict,
  created_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  protection_type text not null check (protection_type in ('STOP_LOSS','TAKE_PROFIT')),
  side text not null check (side in ('BUY','SELL')),
  trigger_price numeric not null check (trigger_price > 0),
  quantity numeric not null check (quantity > 0),
  reduce_only boolean not null default true check (reduce_only=true),
  status text not null check (status='ACTIVE_PAPER'),
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check (paper_only=true),
  exchange_authority boolean not null default false check (exchange_authority=false),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  unique (entry_order_id,protection_type),
  check ((direction='LONG' and side='SELL') or (direction='SHORT' and side='BUY'))
);

create index if not exists idx_ah_paper_reconciliation_run_v03
  on public.alpha_hunter_paper_reconciliation_attempts_v03(source_run_id,observed_at_utc);
create index if not exists idx_ah_paper_protective_entry_v03
  on public.alpha_hunter_paper_protective_orders_v03(entry_order_id,protection_type);
create index if not exists idx_ah_paper_fills_source_run_v03
  on public.alpha_hunter_paper_fills_v02(source_run_id,filled_at_utc);

alter table public.alpha_hunter_paper_reconciliation_attempts_v03 enable row level security;
alter table public.alpha_hunter_paper_protective_orders_v03 enable row level security;

revoke all on table public.alpha_hunter_paper_reconciliation_attempts_v03
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_paper_protective_orders_v03
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_paper_reconciliation_attempts_v03 to service_role;
grant select,insert on table public.alpha_hunter_paper_protective_orders_v03 to service_role;

drop trigger if exists trg_ah_paper_reconciliation_append_only_v03
  on public.alpha_hunter_paper_reconciliation_attempts_v03;
create trigger trg_ah_paper_reconciliation_append_only_v03
before update or delete on public.alpha_hunter_paper_reconciliation_attempts_v03
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

drop trigger if exists trg_ah_paper_protective_append_only_v03
  on public.alpha_hunter_paper_protective_orders_v03;
create trigger trg_ah_paper_protective_append_only_v03
before update or delete on public.alpha_hunter_paper_protective_orders_v03
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

create or replace function private.alpha_hunter_validate_paper_fill_capacity_v03()
returns trigger
language plpgsql
security invoker
set search_path=''
as $$
declare
  ordered numeric;
  already_filled numeric;
  expected_decision text;
begin
  -- SELECT ... FOR SHARE requires UPDATE privilege in PostgreSQL. Keep the
  -- immutable order table read-only for service_role and serialize capacity
  -- checks with a per-order transaction advisory lock instead.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'alpha-hunter-paper-order:' || new.order_id,
      0
    )
  );
  select o.quantity,o.decision_id
    into ordered,expected_decision
  from public.alpha_hunter_paper_orders_v02 o
  where o.order_id=new.order_id;
  if ordered is null or expected_decision<>new.decision_id then
    raise exception 'paper fill does not match an existing entry order';
  end if;
  -- Nullable only for Release 2.2 rollout compatibility. Release 2.3 writers
  -- always supply this FK, while the capacity guard protects both versions.
  select coalesce(sum(f.quantity),0)
    into already_filled
  from public.alpha_hunter_paper_fills_v02 f
  where f.order_id=new.order_id;
  if already_filled+new.quantity > ordered+0.000000000001 then
    raise exception 'paper fill exceeds remaining entry quantity';
  end if;
  return new;
end;
$$;

revoke all on function private.alpha_hunter_validate_paper_fill_capacity_v03()
  from public,anon,authenticated;

drop trigger if exists trg_ah_paper_fill_capacity_v03
  on public.alpha_hunter_paper_fills_v02;
create trigger trg_ah_paper_fill_capacity_v03
before insert on public.alpha_hunter_paper_fills_v02
for each row execute function private.alpha_hunter_validate_paper_fill_capacity_v03();

create or replace function private.alpha_hunter_validate_protective_after_full_fill_v03()
returns trigger
language plpgsql
security invoker
set search_path=''
as $$
declare
  ordered numeric;
  filled numeric;
  expected_decision text;
  expected_direction text;
  expected_stop numeric;
  expected_target numeric;
  average_fill_price numeric;
  fill_matches boolean;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'alpha-hunter-paper-order:' || new.entry_order_id,
      0
    )
  );
  select o.quantity,o.decision_id,o.direction,d.stop_price,d.target_price
    into ordered,expected_decision,expected_direction,expected_stop,expected_target
  from public.alpha_hunter_paper_orders_v02 o
  join public.alpha_hunter_paper_decisions_v01 d on d.decision_id=o.decision_id
  where o.order_id=new.entry_order_id;
  select coalesce(sum(f.quantity),0),
         sum(f.quantity*f.fill_price)/nullif(sum(f.quantity),0),
         bool_or(f.fill_id=new.activated_by_fill_id)
    into filled,average_fill_price,fill_matches
  from public.alpha_hunter_paper_fills_v02 f
  where f.order_id=new.entry_order_id;
  if ordered is null or expected_decision<>new.decision_id then
    raise exception 'protective order does not match an existing entry order';
  end if;
  if not coalesce(fill_matches,false) then
    raise exception 'protective activation fill does not belong to entry order';
  end if;
  if filled < ordered-0.000000000001 then
    raise exception 'protective order forbidden before complete entry fill';
  end if;
  if new.quantity > filled+0.000000000001 then
    raise exception 'protective quantity exceeds cumulative entry fill';
  end if;
  if average_fill_price is null then
    raise exception 'protective order missing cumulative entry average';
  end if;
  if (
    expected_direction='LONG'
    and not (expected_stop < average_fill_price and average_fill_price < expected_target)
  ) or (
    expected_direction='SHORT'
    and not (expected_target < average_fill_price and average_fill_price < expected_stop)
  ) then
    raise exception 'protective order geometry invalid relative to cumulative entry fill';
  end if;
  return new;
end;
$$;

revoke all on function private.alpha_hunter_validate_protective_after_full_fill_v03()
  from public,anon,authenticated;

drop trigger if exists trg_ah_paper_protective_after_full_fill_v03
  on public.alpha_hunter_paper_protective_orders_v03;
create trigger trg_ah_paper_protective_after_full_fill_v03
before insert on public.alpha_hunter_paper_protective_orders_v03
for each row execute function private.alpha_hunter_validate_protective_after_full_fill_v03();

create or replace view public.alpha_hunter_paper_reconciliation_open_v03
with (security_invoker=true,security_barrier=true)
as
select
  o.order_id,
  o.decision_id,
  o.symbol,
  o.direction,
  o.order_type,
  o.limit_price,
  o.quantity as ordered_quantity,
  coalesce(x.filled_quantity,0) as filled_quantity,
  o.quantity-coalesce(x.filled_quantity,0) as remaining_quantity,
  case when coalesce(x.filled_quantity,0)>0 then 'PARTIALLY_FILLED' else 'SUBMITTED' end
    as execution_state,
  coalesce(x.fill_count,0)::integer as fill_count,
  x.average_fill_price,
  coalesce(e.event_sequence,3)::integer as event_sequence,
  d.stop_price,
  d.target_price,
  o.public_maker_fee_bps,
  o.public_taker_fee_bps,
  o.paper_only,
  o.exchange_authority,
  o.trade_permission,
  o.order_path
from public.alpha_hunter_paper_orders_v02 o
join public.alpha_hunter_paper_decisions_v01 d using (decision_id)
left join lateral (
  select
    sum(f.quantity) as filled_quantity,
    sum(f.quantity*f.fill_price)/nullif(sum(f.quantity),0) as average_fill_price,
    count(*) as fill_count
  from public.alpha_hunter_paper_fills_v02 f
  where f.order_id=o.order_id
) x on true
left join lateral (
  select max(pe.sequence) as event_sequence
  from public.alpha_hunter_paper_events_v01 pe
  where pe.decision_id=o.decision_id
) e on true
where coalesce(x.filled_quantity,0) < o.quantity;

revoke all on public.alpha_hunter_paper_reconciliation_open_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_reconciliation_open_v03 to service_role;

create or replace view public.alpha_hunter_paper_protection_current_v03
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
  p.reduce_only,
  p.status,
  p.paper_only,
  p.exchange_authority,
  p.trade_permission,
  p.order_path
from public.alpha_hunter_paper_protective_orders_v03 p;

revoke all on public.alpha_hunter_paper_protection_current_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_protection_current_v03 to service_role;

create or replace function public.alpha_hunter_commit_paper_reconciliation_v03(
  attempt_rows jsonb,
  fill_rows jsonb,
  event_rows jsonb,
  protective_rows jsonb
)
returns void
language plpgsql
security invoker
set search_path=''
as $$
begin
  if jsonb_typeof(attempt_rows)<>'array'
     or jsonb_typeof(fill_rows)<>'array'
     or jsonb_typeof(event_rows)<>'array'
     or jsonb_typeof(protective_rows)<>'array' then
    raise exception 'paper reconciliation payloads must be JSON arrays';
  end if;

  -- Serialize this tiny paper-only commit path. Filter attempts already committed
  -- by an idempotent retry before inserting any dependent evidence.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('alpha-hunter-paper-reconciliation-v03',0)
  );
  select coalesce(pg_catalog.jsonb_agg(j),'[]'::jsonb)
    into attempt_rows
  from pg_catalog.jsonb_array_elements(attempt_rows) j
  where not exists (
    select 1
    from public.alpha_hunter_paper_reconciliation_attempts_v03 a
    where a.attempt_id=j->>'attempt_id'
  );
  if pg_catalog.jsonb_array_length(attempt_rows)=0 then
    return;
  end if;

  insert into public.alpha_hunter_paper_reconciliation_attempts_v03 (
    attempt_id,order_id,decision_id,source_run_id,observed_at_utc,symbol,
    prior_state,prior_filled_quantity,prior_remaining_quantity,best_bid,best_ask,
    best_bid_size,best_ask_size,outcome,blockers,evidence,paper_only,
    exchange_authority,trade_permission,order_path
  )
  select
    j->>'attempt_id',j->>'order_id',j->>'decision_id',j->>'source_run_id',
    (j->>'observed_at_utc')::timestamptz,j->>'symbol',j->>'prior_state',
    (j->>'prior_filled_quantity')::numeric,(j->>'prior_remaining_quantity')::numeric,
    (j->>'best_bid')::numeric,(j->>'best_ask')::numeric,
    (j->>'best_bid_size')::numeric,(j->>'best_ask_size')::numeric,
    j->>'outcome',j->'blockers',j->'evidence',(j->>'paper_only')::boolean,
    (j->>'exchange_authority')::boolean,(j->>'trade_permission')::boolean,
    j->>'order_path'
  from pg_catalog.jsonb_array_elements(attempt_rows) j;

  insert into public.alpha_hunter_paper_fills_v02 (
    fill_id,order_id,decision_id,source_run_id,fill_sequence,filled_at_utc,
    quantity,fill_price,notional_usdt,midpoint_reference,cross_price_reference,
    spread_cost_usdt,slippage_bps,slippage_cost_usdt,fee_bps,fee_usdt,
    funding_rate_snapshot,projected_next_funding_usdt,accrued_funding_usdt,
    funding_status,liquidity_source,model_quality,paper_only,exchange_authority,
    trade_permission,order_path
  )
  select
    j->>'fill_id',j->>'order_id',j->>'decision_id',j->>'source_run_id',
    (j->>'fill_sequence')::integer,(j->>'filled_at_utc')::timestamptz,
    (j->>'quantity')::numeric,(j->>'fill_price')::numeric,
    (j->>'notional_usdt')::numeric,(j->>'midpoint_reference')::numeric,
    (j->>'cross_price_reference')::numeric,(j->>'spread_cost_usdt')::numeric,
    (j->>'slippage_bps')::numeric,(j->>'slippage_cost_usdt')::numeric,
    (j->>'fee_bps')::numeric,(j->>'fee_usdt')::numeric,
    (j->>'funding_rate_snapshot')::numeric,
    (j->>'projected_next_funding_usdt')::numeric,
    (j->>'accrued_funding_usdt')::numeric,j->>'funding_status',
    j->>'liquidity_source',j->>'model_quality',(j->>'paper_only')::boolean,
    (j->>'exchange_authority')::boolean,(j->>'trade_permission')::boolean,
    j->>'order_path'
  from pg_catalog.jsonb_array_elements(fill_rows) j
  where exists (
    select 1 from pg_catalog.jsonb_array_elements(attempt_rows) a
    where a->>'order_id'=j->>'order_id'
      and a->>'source_run_id'=j->>'source_run_id'
  );

  insert into public.alpha_hunter_paper_events_v01 (
    event_id,decision_id,sequence,occurred_at_utc,event_type,state,payload,
    paper_only,exchange_authority,trade_permission,order_path
  )
  select
    j->>'event_id',j->>'decision_id',(j->>'sequence')::integer,
    (j->>'occurred_at_utc')::timestamptz,j->>'event_type',j->>'state',j->'payload',
    (j->>'paper_only')::boolean,(j->>'exchange_authority')::boolean,
    (j->>'trade_permission')::boolean,j->>'order_path'
  from pg_catalog.jsonb_array_elements(event_rows) j
  where exists (
    select 1 from pg_catalog.jsonb_array_elements(attempt_rows) a
    where a->>'decision_id'=j->>'decision_id'
      and a->>'source_run_id'=j->'payload'->>'source_run_id'
  );

  insert into public.alpha_hunter_paper_protective_orders_v03 (
    protective_order_id,entry_order_id,decision_id,activated_by_fill_id,
    created_at_utc,symbol,direction,protection_type,side,trigger_price,quantity,
    reduce_only,status,evidence,paper_only,exchange_authority,trade_permission,order_path
  )
  select
    j->>'protective_order_id',j->>'entry_order_id',j->>'decision_id',
    j->>'activated_by_fill_id',(j->>'created_at_utc')::timestamptz,j->>'symbol',
    j->>'direction',j->>'protection_type',j->>'side',(j->>'trigger_price')::numeric,
    (j->>'quantity')::numeric,(j->>'reduce_only')::boolean,j->>'status',j->'evidence',
    (j->>'paper_only')::boolean,(j->>'exchange_authority')::boolean,
    (j->>'trade_permission')::boolean,j->>'order_path'
  from pg_catalog.jsonb_array_elements(protective_rows) j
  where exists (
    select 1 from pg_catalog.jsonb_array_elements(attempt_rows) a
    where a->>'order_id'=j->>'entry_order_id'
      and a->>'source_run_id'=j->'evidence'->>'source_run_id'
  );
end;
$$;

revoke all on function public.alpha_hunter_commit_paper_reconciliation_v03(
  jsonb,jsonb,jsonb,jsonb
) from public,anon,authenticated,service_role;
grant execute on function public.alpha_hunter_commit_paper_reconciliation_v03(
  jsonb,jsonb,jsonb,jsonb
) to service_role;

commit;
