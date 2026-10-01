begin;

-- Alpha Hunter paper execution v0.2 (Release 2.2).
-- Deterministic simulated order/fill evidence only. No exchange write path exists.

alter table public.alpha_hunter_paper_decisions_v01
  add column if not exists best_bid_size numeric,
  add column if not exists best_ask_size numeric,
  add column if not exists public_maker_fee_bps numeric;

create table if not exists public.alpha_hunter_paper_orders_v02 (
  order_id text primary key,
  decision_id text not null unique
    references public.alpha_hunter_paper_decisions_v01(decision_id) on delete restrict,
  model_version text not null check (model_version='paper-execution-v0.2'),
  submitted_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  order_type text not null check (order_type in ('MARKET','LIMIT')),
  limit_price numeric,
  quantity numeric not null check (quantity > 0),
  virtual_equity_usdt numeric not null check (virtual_equity_usdt > 0),
  risk_fraction numeric not null check (risk_fraction > 0 and risk_fraction <= 0.01),
  planned_risk_usdt numeric not null check (planned_risk_usdt > 0),
  sizing_source text not null check (sizing_source='VIRTUAL_PAPER_CAPITAL'),
  best_bid numeric,
  best_ask numeric,
  best_bid_size numeric,
  best_ask_size numeric,
  public_maker_fee_bps numeric,
  public_taker_fee_bps numeric,
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check (paper_only=true),
  exchange_authority boolean not null default false check (exchange_authority=false),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check ((order_type='LIMIT' and limit_price is not null) or (order_type='MARKET' and limit_price is null))
);

create table if not exists public.alpha_hunter_paper_fills_v02 (
  fill_id text primary key,
  order_id text not null
    references public.alpha_hunter_paper_orders_v02(order_id) on delete restrict,
  decision_id text not null
    references public.alpha_hunter_paper_decisions_v01(decision_id) on delete restrict,
  fill_sequence integer not null check (fill_sequence > 0),
  filled_at_utc timestamptz not null,
  quantity numeric not null check (quantity > 0),
  fill_price numeric not null check (fill_price > 0),
  notional_usdt numeric not null check (notional_usdt > 0),
  midpoint_reference numeric not null check (midpoint_reference > 0),
  cross_price_reference numeric not null check (cross_price_reference > 0),
  spread_cost_usdt numeric not null check (spread_cost_usdt >= 0),
  slippage_bps numeric not null check (slippage_bps >= 0),
  slippage_cost_usdt numeric not null check (slippage_cost_usdt >= 0),
  fee_bps numeric not null check (fee_bps >= 0),
  fee_usdt numeric not null check (fee_usdt >= 0),
  funding_rate_snapshot numeric,
  projected_next_funding_usdt numeric,
  accrued_funding_usdt numeric not null default 0 check (accrued_funding_usdt=0),
  funding_status text not null check (funding_status='NOT_ACCRUED'),
  liquidity_source text not null check (liquidity_source='BITGET_TOP_OF_BOOK_SNAPSHOT'),
  model_quality text not null check (
    model_quality='DETERMINISTIC_PAPER_MODEL_NOT_EXCHANGE_EXECUTION'
  ),
  paper_only boolean not null default true check (paper_only=true),
  exchange_authority boolean not null default false check (exchange_authority=false),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  unique (order_id,fill_sequence)
);

create index if not exists idx_ah_paper_orders_symbol_time_v02
  on public.alpha_hunter_paper_orders_v02(symbol,submitted_at_utc desc);
create index if not exists idx_ah_paper_fills_decision_v02
  on public.alpha_hunter_paper_fills_v02(decision_id,fill_sequence);

alter table public.alpha_hunter_paper_orders_v02 enable row level security;
alter table public.alpha_hunter_paper_fills_v02 enable row level security;

revoke all on table public.alpha_hunter_paper_orders_v02
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_paper_fills_v02
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_paper_orders_v02 to service_role;
grant select,insert on table public.alpha_hunter_paper_fills_v02 to service_role;

drop trigger if exists trg_ah_paper_orders_append_only_v02
  on public.alpha_hunter_paper_orders_v02;
create trigger trg_ah_paper_orders_append_only_v02
before update or delete on public.alpha_hunter_paper_orders_v02
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

drop trigger if exists trg_ah_paper_fills_append_only_v02
  on public.alpha_hunter_paper_fills_v02;
create trigger trg_ah_paper_fills_append_only_v02
before update or delete on public.alpha_hunter_paper_fills_v02
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

create or replace view public.alpha_hunter_paper_execution_current_v02
with (security_invoker=true,security_barrier=true)
as
select
  o.order_id,
  o.decision_id,
  o.submitted_at_utc,
  o.symbol,
  o.direction,
  o.order_type,
  o.limit_price,
  o.quantity as ordered_quantity,
  coalesce(sum(f.quantity),0) as filled_quantity,
  o.quantity-coalesce(sum(f.quantity),0) as remaining_quantity,
  case
    when coalesce(sum(f.quantity),0) >= o.quantity then 'FILLED'
    when coalesce(sum(f.quantity),0) > 0 then 'PARTIALLY_FILLED'
    else 'SUBMITTED'
  end as execution_state,
  case when coalesce(sum(f.quantity),0) > 0
    then sum(f.quantity*f.fill_price)/sum(f.quantity) end as average_fill_price,
  coalesce(sum(f.fee_usdt),0) as fee_usdt,
  coalesce(sum(f.spread_cost_usdt),0) as spread_cost_usdt,
  coalesce(sum(f.slippage_cost_usdt),0) as slippage_cost_usdt,
  coalesce(sum(f.accrued_funding_usdt),0) as accrued_funding_usdt,
  o.sizing_source,
  o.paper_only,
  o.exchange_authority,
  o.trade_permission,
  o.order_path
from public.alpha_hunter_paper_orders_v02 o
left join public.alpha_hunter_paper_fills_v02 f using (order_id,decision_id)
group by o.order_id;

revoke all on public.alpha_hunter_paper_execution_current_v02
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_execution_current_v02 to service_role;

commit;
