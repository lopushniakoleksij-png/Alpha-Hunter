-- Alpha Hunter read-only execution-quality collector telemetry v0.1
--
-- Operations observability only. Lives under ops/sql and is outside the sealed
-- V14 scientific fingerprint.
--
-- No exchange write authority is added. This table records only sanitized
-- collector health/result metadata; no API credentials or raw order IDs.

create table if not exists public.alpha_hunter_execution_quality_collector_runs_v01 (
  collector_run_id text primary key,
  source_run_id text,
  checked_at_utc timestamptz not null,
  snapshot_source text,
  collector_exists boolean not null,
  bitget_credentials_configured boolean not null,
  supabase_configured boolean not null,
  subprocess_started boolean not null,
  subprocess_exit_code integer,
  collector_status text not null,
  fills_considered integer,
  order_details_connected integer,
  order_detail_failures integer,
  rows_persisted integer,
  explicit_limit_benchmarks integer,
  market_slippage_withheld integer,
  read_only_get boolean,
  no_order_write_path boolean,
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  evidence jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default clock_timestamp(),
  check (collector_status in (
    'PASS',
    'DEGRADED',
    'COLLECTOR_NOT_FOUND',
    'RESULT_JSON_UNAVAILABLE'
  ))
);

alter table public.alpha_hunter_execution_quality_collector_runs_v01
  enable row level security;

revoke all on table public.alpha_hunter_execution_quality_collector_runs_v01
  from public,anon,authenticated,service_role;

grant select,insert on table public.alpha_hunter_execution_quality_collector_runs_v01
  to service_role;

drop trigger if exists trg_ah_execution_quality_collector_runs_append_only
  on public.alpha_hunter_execution_quality_collector_runs_v01;

create trigger trg_ah_execution_quality_collector_runs_append_only
before update or delete
on public.alpha_hunter_execution_quality_collector_runs_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace view public.alpha_hunter_execution_quality_collector_status_v01
with (security_invoker=true,security_barrier=true) as
select
  collector_run_id,
  source_run_id,
  checked_at_utc,
  snapshot_source,
  collector_exists,
  bitget_credentials_configured,
  supabase_configured,
  subprocess_started,
  subprocess_exit_code,
  collector_status,
  fills_considered,
  order_details_connected,
  order_detail_failures,
  rows_persisted,
  explicit_limit_benchmarks,
  market_slippage_withheld,
  read_only_get,
  no_order_write_path,
  shadow_only,
  trade_permission,
  evidence,
  created_at
from public.alpha_hunter_execution_quality_collector_runs_v01
order by checked_at_utc desc
limit 1;

revoke all on public.alpha_hunter_execution_quality_collector_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_quality_collector_status_v01
  to service_role;
