-- Alpha Hunter in-project real-time test engine v0.1
--
-- Immutable engine-run ledger. The engine reads the sealed forward-only
-- profitability views and records what the production system knew at each
-- evaluation timestamp.
--
-- This is paper/shadow validation only. It cannot place orders, grant trade
-- permission, change thresholds, or promote a strategy.

create table if not exists public.alpha_hunter_test_engine_runs_v01 (
  test_engine_run_id text primary key,
  evaluated_at_utc timestamptz not null,
  engine_version text not null default 'realtime-test-engine-v0.1',

  spec_id text,
  real_test_requested_at_utc timestamptz,
  real_counted_baseline_started_at_utc timestamptz,

  latest_live_run_id text,
  latest_live_scan_at_utc timestamptz,
  latest_live_scan_age_seconds double precision,
  latest_live_git_commit text,
  latest_live_config_sha256 text,
  previous_snapshot_source text,
  catalyst_version text,
  configured_strategy_count integer,

  real_scans_since_registration integer not null default 0,
  real_strategy_observations_since_registration integer not null default 0,
  real_shadow_candidates_since_registration integer not null default 0,
  real_24h_forward_outcomes_since_registration integer not null default 0,

  completed_paper_trades integer not null default 0,
  test_days_elapsed double precision not null default 0,
  minimum_test_days integer,
  minimum_completed_paper_trades integer,

  avg_gross_r double precision,
  gross_r_lower_95 double precision,
  avg_floor_adjusted_r double precision,
  floor_adjusted_r_lower_95 double precision,
  floor_profit_factor double precision,
  avg_modeled_net_r double precision,
  modeled_net_r_lower_95 double precision,
  modeled_net_profit_factor double precision,

  cost_model_validated boolean not null default false,
  realistic_net_r_claim_permitted boolean not null default false,

  operational_status text not null,
  profitability_status text not null,
  verdict text not null,
  blockers jsonb not null default '[]'::jsonb,
  source_status jsonb not null default '{}'::jsonb,
  economics jsonb not null default '{}'::jsonb,

  real_time boolean not null default true check(real_time=true),
  forward_only boolean not null default true check(forward_only=true),
  historical_replay_counted boolean not null default false
    check(historical_replay_counted=false),
  backtest_counted boolean not null default false
    check(backtest_counted=false),
  paper_only boolean not null default true check(paper_only=true),
  live_money_claim_permitted boolean not null default false
    check(live_money_claim_permitted=false),
  trade_permission boolean not null default false check(trade_permission=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),

  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_test_engine_runs_time_v01
  on public.alpha_hunter_test_engine_runs_v01(evaluated_at_utc desc);

create index if not exists idx_ah_test_engine_runs_spec_time_v01
  on public.alpha_hunter_test_engine_runs_v01(spec_id,evaluated_at_utc desc);

alter table public.alpha_hunter_test_engine_runs_v01 enable row level security;

revoke all on public.alpha_hunter_test_engine_runs_v01
  from public,anon,authenticated,service_role;
grant select, insert on public.alpha_hunter_test_engine_runs_v01
  to service_role;

drop trigger if exists trg_ah_test_engine_runs_append_only_v01
  on public.alpha_hunter_test_engine_runs_v01;

create trigger trg_ah_test_engine_runs_append_only_v01
before update or delete on public.alpha_hunter_test_engine_runs_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace view public.alpha_hunter_test_engine_latest_v01
with (security_invoker=true,security_barrier=true)
as
select *
from public.alpha_hunter_test_engine_runs_v01
order by evaluated_at_utc desc
limit 1;

revoke all on public.alpha_hunter_test_engine_latest_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_test_engine_latest_v01 to service_role;
