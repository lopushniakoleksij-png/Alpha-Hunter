-- Alpha Hunter Supabase capacity guard v0.1
--
-- Purpose:
--   1) keep rolling READY->execution traceability independent from bulky raw
--      per-symbol JSON;
--   2) expose database size for production capacity monitoring;
--   3) preserve fail-closed behavior. This migration grants no trade authority.
--
-- Raw scanner evidence remains in alpha_hunter_symbol_snapshots for near-term
-- forward science. Long-lived traceability uses this compact ledger.

create table if not exists public.alpha_hunter_readiness_observations_v01 (
  run_id text not null,
  symbol text not null,
  observed_at_utc timestamptz not null,
  state text,
  direction text,
  trade_permission boolean not null default false,
  v7_trade_ready boolean not null default false,
  reference_price double precision,
  entry_price double precision,
  stop_loss double precision,
  take_profit double precision,
  reward_risk double precision,
  lifecycle_id text,
  t1_id text,
  lifecycle_stage text,
  archetype text,
  capital_risk_status text,
  created_at timestamptz not null default clock_timestamp(),
  primary key (run_id, symbol)
);

create index if not exists idx_ah_readiness_observed_v01
  on public.alpha_hunter_readiness_observations_v01(observed_at_utc desc);

create index if not exists idx_ah_readiness_ready_v01
  on public.alpha_hunter_readiness_observations_v01(
    v7_trade_ready,
    trade_permission,
    observed_at_utc desc
  );

comment on table public.alpha_hunter_readiness_observations_v01 is
  'Compact canonical scanner readiness evidence for rolling traceability. '
  'No order path; no trade authorization; raw symbol JSON is not duplicated.';

alter table public.alpha_hunter_readiness_observations_v01 enable row level security;

create or replace view public.alpha_hunter_storage_pressure_v01 as
select
  clock_timestamp() as checked_at_utc,
  pg_database_size(current_database())::bigint as database_bytes,
  pg_size_pretty(pg_database_size(current_database())) as database_size_pretty,
  500::bigint * 1024 * 1024 as free_plan_read_only_threshold_bytes,
  round(
    pg_database_size(current_database())::numeric
    / (500::numeric * 1024 * 1024)
    * 100,
    2
  ) as free_plan_threshold_pct;

comment on view public.alpha_hunter_storage_pressure_v01 is
  'Capacity telemetry only. The 500 MB reference is the Supabase Free-plan '
  'database-size read-only threshold; billing-plan state is not inferred here.';
