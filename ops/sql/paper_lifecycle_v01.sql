begin;

-- Alpha Hunter paper lifecycle v0.1 (Release 2.1).
-- This ledger binds the final canonical Action Queue to an immutable paper-only
-- state machine. It contains no exchange submission function or LIVE mode.

create schema if not exists private;

create or replace function private.alpha_hunter_block_paper_lifecycle_mutation_v01()
returns trigger
language plpgsql
security invoker
set search_path=''
as $$
begin
  raise exception 'Alpha Hunter paper lifecycle rows are append-only';
end;
$$;

revoke all on function private.alpha_hunter_block_paper_lifecycle_mutation_v01()
  from public,anon,authenticated;

create table if not exists public.alpha_hunter_paper_decisions_v01 (
  decision_id text primary key,
  contract_version text not null check (contract_version='paper-lifecycle-v0.1'),
  run_id text not null references public.alpha_hunter_snapshots(run_id) on delete restrict,
  observed_at_utc timestamptz not null,
  symbol text not null,
  strategy_id text,
  strategy_name text,
  direction text check (direction is null or direction in ('LONG','SHORT')),
  action_status text not null check (
    action_status in (
      'EXECUTE_NOW_PAPER','PLACE_LIMIT_PAPER','WAIT_FOR_TRIGGER','BLOCKED',
      'BLOCKED_DIRECTION_CONFLICT'
    )
  ),
  disposition text not null check (
    disposition in ('CANONICAL','BLOCKED','SUPERSEDED')
  ),
  entry_price numeric,
  stop_price numeric,
  target_price numeric,
  reward_risk numeric,
  best_bid numeric,
  best_ask numeric,
  public_taker_fee_bps numeric,
  cost_floor_pct numeric,
  blockers jsonb not null default '[]'::jsonb
    check (jsonb_typeof(blockers)='array'),
  evidence jsonb not null default '{}'::jsonb
    check (jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check (paper_only=true),
  paper_authority boolean not null default false,
  exchange_authority boolean not null default false check (exchange_authority=false),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  check (
    paper_authority=false
    or (
      disposition='CANONICAL'
      and action_status in ('EXECUTE_NOW_PAPER','PLACE_LIMIT_PAPER')
      and direction in ('LONG','SHORT')
      and entry_price is not null
      and stop_price is not null
      and target_price is not null
    )
  )
);

create table if not exists public.alpha_hunter_paper_events_v01 (
  event_id text primary key,
  decision_id text not null
    references public.alpha_hunter_paper_decisions_v01(decision_id) on delete restrict,
  sequence integer not null check (sequence > 0),
  occurred_at_utc timestamptz not null,
  event_type text not null,
  state text not null check (
    state in (
      'CREATED','AUTHORIZED','WATCHING','BLOCKED','SUBMITTED',
      'PARTIALLY_FILLED','FILLED','CANCELLED','EXPIRED','STOPPED',
      'TARGETED','RECONCILIATION_REQUIRED'
    )
  ),
  payload jsonb not null default '{}'::jsonb
    check (jsonb_typeof(payload)='object'),
  paper_only boolean not null default true check (paper_only=true),
  exchange_authority boolean not null default false check (exchange_authority=false),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  unique (decision_id,sequence)
);

create index if not exists idx_ah_paper_decisions_run_symbol_v01
  on public.alpha_hunter_paper_decisions_v01(run_id,symbol);
create index if not exists idx_ah_paper_events_decision_sequence_v01
  on public.alpha_hunter_paper_events_v01(decision_id,sequence);

alter table public.alpha_hunter_paper_decisions_v01 enable row level security;
alter table public.alpha_hunter_paper_events_v01 enable row level security;

revoke all on table public.alpha_hunter_paper_decisions_v01
  from public,anon,authenticated,service_role;
revoke all on table public.alpha_hunter_paper_events_v01
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_paper_decisions_v01 to service_role;
grant select,insert on table public.alpha_hunter_paper_events_v01 to service_role;

drop trigger if exists trg_ah_paper_decisions_append_only_v01
  on public.alpha_hunter_paper_decisions_v01;
create trigger trg_ah_paper_decisions_append_only_v01
before update or delete on public.alpha_hunter_paper_decisions_v01
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

drop trigger if exists trg_ah_paper_events_append_only_v01
  on public.alpha_hunter_paper_events_v01;
create trigger trg_ah_paper_events_append_only_v01
before update or delete on public.alpha_hunter_paper_events_v01
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

create or replace view public.alpha_hunter_paper_lifecycle_current_v01
with (security_invoker=true,security_barrier=true)
as
select distinct on (d.decision_id)
  d.decision_id,
  d.run_id,
  d.observed_at_utc,
  d.symbol,
  d.strategy_id,
  d.direction,
  d.action_status,
  d.disposition,
  d.entry_price,
  d.stop_price,
  d.target_price,
  d.reward_risk,
  d.paper_authority,
  e.sequence,
  e.occurred_at_utc as state_at_utc,
  e.event_type,
  e.state,
  d.paper_only,
  d.exchange_authority,
  d.trade_permission,
  d.order_path
from public.alpha_hunter_paper_decisions_v01 d
join public.alpha_hunter_paper_events_v01 e using (decision_id)
order by d.decision_id,e.sequence desc,e.created_at desc;

revoke all on public.alpha_hunter_paper_lifecycle_current_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_lifecycle_current_v01 to service_role;

commit;
