begin;

-- R8 shadow-only depth diagnostic v0.1.
-- Evidence-only companion for Issue #302.
-- This does not alter R8 execution, fills, thresholds, cadence, sizing,
-- scientific fingerprint, paper authority, trade permission, or order path.

create table if not exists public.alpha_hunter_r8_depth_shadow_v01 (
  capture_id text primary key,
  captured_at_utc timestamptz not null,
  order_id text not null,
  decision_id text not null,
  symbol text not null,
  strategy_id text,
  direction text not null check (direction in ('LONG','SHORT')),
  limit_price numeric not null check (limit_price > 0),
  remaining_quantity numeric not null check (remaining_quantity > 0),
  best_bid numeric,
  best_ask numeric,
  top_side_size numeric,
  crossed_limit boolean not null,
  depth_source text not null,
  exchange_timestamp_ms bigint,
  depth_levels jsonb not null default '[]'::jsonb,
  eligible_depth_quantity numeric not null default 0
    check (eligible_depth_quantity >= 0),
  eligible_depth_notional numeric not null default 0
    check (eligible_depth_notional >= 0),
  conservative_vwap numeric,
  required_to_l1_ratio numeric,
  required_to_depth_ratio numeric,
  diagnostic_verdict text not null check (
    diagnostic_verdict in (
      'TRUE_INSUFFICIENT_DEPTH',
      'DEPTH_SUFFICIENT_BUT_L1_INSUFFICIENT',
      'DEPTH_EVIDENCE_UNAVAILABLE',
      'NOT_CROSSED',
      'L1_SUFFICIENT'
    )
  ),
  evidence jsonb not null default '{}'::jsonb,
  shadow_only boolean not null default true check (shadow_only),
  paper_only boolean not null default true check (paper_only),
  trade_permission boolean not null default false check (not trade_permission),
  production_promotion_permitted boolean not null default false
    check (not production_promotion_permitted),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default now(),
  unique(order_id,captured_at_utc)
);

alter table public.alpha_hunter_r8_depth_shadow_v01
  enable row level security;

revoke all on table public.alpha_hunter_r8_depth_shadow_v01
  from public, anon, authenticated, service_role;
grant select, insert on table public.alpha_hunter_r8_depth_shadow_v01
  to service_role;

create index if not exists alpha_hunter_r8_depth_shadow_v01_order_time_idx
  on public.alpha_hunter_r8_depth_shadow_v01(order_id,captured_at_utc desc);

drop trigger if exists alpha_hunter_r8_depth_shadow_v01_append_only
  on public.alpha_hunter_r8_depth_shadow_v01;

create trigger alpha_hunter_r8_depth_shadow_v01_append_only
before update or delete on public.alpha_hunter_r8_depth_shadow_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace view public.alpha_hunter_r8_depth_shadow_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  count(*)::integer as captures,
  count(*) filter(
    where diagnostic_verdict='DEPTH_SUFFICIENT_BUT_L1_INSUFFICIENT'
  )::integer as depth_sufficient_l1_insufficient,
  count(*) filter(
    where diagnostic_verdict='TRUE_INSUFFICIENT_DEPTH'
  )::integer as true_insufficient_depth,
  count(*) filter(
    where diagnostic_verdict='DEPTH_EVIDENCE_UNAVAILABLE'
  )::integer as depth_evidence_unavailable,
  max(captured_at_utc) as latest_capture_at_utc,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_r8_depth_shadow_v01;

revoke all on public.alpha_hunter_r8_depth_shadow_status_v01
  from public, anon, authenticated, service_role;
grant select on public.alpha_hunter_r8_depth_shadow_status_v01
  to service_role;

commit;
