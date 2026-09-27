-- Alpha Hunter V15 candidate-retention target ledger + dedupe v0.2
--
-- PARALLEL SHADOW / AUDIT ONLY. Lives under ops/sql and is outside the
-- sealed V14 scientific fingerprint.
--
-- Improvements over v0.1:
-- 1) persist candidate-retention targets append-only so completed/expired
--    episodes remain auditable after leaving the transient active-target view;
-- 2) expose a collection-target view containing only still-relevant horizons;
-- 3) make coverage/timing status read from the persistent target ledger.
--
-- This migration does not alter V14 counted outcomes, scanner/universe logic,
-- strategy thresholds, trade permission, or order paths.

create table if not exists public.alpha_hunter_candidate_retention_shadow_targets_v02 (
  episode_id text primary key,
  first_candidate_observation_id text not null unique,
  symbol text not null,
  strategy_id text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  first_observed_at_utc timestamptz not null,
  first_candidate_at_utc timestamptz not null,
  first_candidate_action text not null
    check (first_candidate_action in ('EXECUTE_NOW','PLACE_LIMIT')),
  retention_start_utc timestamptz not null,
  retention_horizon_end_utc timestamptz not null,
  expected_closed_1h_candles integer not null
    check (expected_closed_1h_candles>=0),

  target_registered_at_utc timestamptz not null,
  target_source text not null default 'SEALED_CANDIDATE_EPISODES_ONLY'
    check (target_source='SEALED_CANDIDATE_EPISODES_ONLY'),
  scientific_role text not null default 'V15_PARALLEL_SHADOW'
    check (scientific_role='V15_PARALLEL_SHADOW'),
  audit_only boolean not null default true check (audit_only=true),
  counted_in_v14 boolean not null default false check (counted_in_v14=false),
  mutation_permitted boolean not null default false
    check (mutation_permitted=false),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),

  created_at timestamptz not null default clock_timestamp(),

  check (retention_start_utc>=date_trunc('hour',first_candidate_at_utc)),
  check (retention_horizon_end_utc>retention_start_utc)
);

create index if not exists idx_ah_candidate_retention_targets_horizon_v02
  on public.alpha_hunter_candidate_retention_shadow_targets_v02(
    retention_horizon_end_utc,episode_id
  );

create index if not exists idx_ah_candidate_retention_targets_symbol_v02
  on public.alpha_hunter_candidate_retention_shadow_targets_v02(
    symbol,first_candidate_at_utc
  );

alter table public.alpha_hunter_candidate_retention_shadow_targets_v02
  enable row level security;

revoke all on table public.alpha_hunter_candidate_retention_shadow_targets_v02
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_candidate_retention_shadow_targets_v02
  to service_role;

drop trigger if exists trg_ah_candidate_retention_shadow_targets_append_only_v02
  on public.alpha_hunter_candidate_retention_shadow_targets_v02;
create trigger trg_ah_candidate_retention_shadow_targets_append_only_v02
before update or delete
on public.alpha_hunter_candidate_retention_shadow_targets_v02
for each row execute function private.alpha_hunter_block_append_only_mutation();

-- Seed every target still visible in the v0.1 transient target view now, before
-- it can age out. Later collector runs append newly discovered targets.
insert into public.alpha_hunter_candidate_retention_shadow_targets_v02(
  episode_id,
  first_candidate_observation_id,
  symbol,
  strategy_id,
  direction,
  first_observed_at_utc,
  first_candidate_at_utc,
  first_candidate_action,
  retention_start_utc,
  retention_horizon_end_utc,
  expected_closed_1h_candles,
  target_registered_at_utc,
  target_source,
  scientific_role,
  audit_only,
  counted_in_v14,
  mutation_permitted,
  shadow_only,
  trade_permission,
  production_promotion_permitted,
  order_path
)
select
  t.episode_id,
  t.first_candidate_observation_id,
  t.symbol,
  t.strategy_id,
  t.direction,
  t.first_observed_at_utc,
  t.first_candidate_at_utc,
  t.first_candidate_action,
  t.retention_start_utc,
  t.retention_horizon_end_utc,
  t.expected_closed_1h_candles,
  clock_timestamp(),
  'SEALED_CANDIDATE_EPISODES_ONLY',
  'V15_PARALLEL_SHADOW',
  true,
  false,
  false,
  true,
  false,
  false,
  'NONE'
from public.alpha_hunter_candidate_retention_targets_v01 t
on conflict (episode_id) do nothing;


create or replace view public.alpha_hunter_candidate_retention_collection_targets_v02
with (security_invoker=true,security_barrier=true) as
select
  t.episode_id,
  t.first_candidate_observation_id,
  t.symbol,
  t.strategy_id,
  t.direction,
  t.first_observed_at_utc,
  t.first_candidate_at_utc,
  t.first_candidate_action,
  t.retention_start_utc,
  t.retention_horizon_end_utc,
  t.expected_closed_1h_candles,
  t.target_registered_at_utc,
  t.target_source,
  t.scientific_role,
  t.audit_only,
  t.counted_in_v14,
  t.mutation_permitted,
  t.shadow_only,
  t.trade_permission,
  t.production_promotion_permitted,
  t.order_path
from public.alpha_hunter_candidate_retention_shadow_targets_v02 t
where t.retention_horizon_end_utc>clock_timestamp()-interval '2 hours';

revoke all on public.alpha_hunter_candidate_retention_collection_targets_v02
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_candidate_retention_collection_targets_v02
  to service_role;


create or replace view public.alpha_hunter_candidate_retention_shadow_coverage_v01
with (security_invoker=true,security_barrier=true) as
with targets as (
  select *
  from public.alpha_hunter_candidate_retention_shadow_targets_v02
),
coverage as (
  select
    t.episode_id,
    t.first_candidate_observation_id,
    t.symbol,
    t.strategy_id,
    t.direction,
    t.first_observed_at_utc,
    t.first_candidate_at_utc,
    t.first_candidate_action,
    t.retention_start_utc,
    t.retention_horizon_end_utc,
    t.expected_closed_1h_candles,
    count(c.*)::integer as captured_closed_1h_candles,
    min(c.candle_open_utc) as first_candle_open_utc,
    max(c.candle_open_utc) as latest_candle_open_utc
  from targets t
  left join public.alpha_hunter_candidate_retention_shadow_candles_v01 c
    on c.episode_id=t.episode_id
  group by
    t.episode_id,t.first_candidate_observation_id,t.symbol,t.strategy_id,
    t.direction,t.first_observed_at_utc,t.first_candidate_at_utc,
    t.first_candidate_action,t.retention_start_utc,
    t.retention_horizon_end_utc,t.expected_closed_1h_candles
)
select
  clock_timestamp() as checked_at_utc,
  c.*,
  case
    when c.expected_closed_1h_candles=0 then null
    else least(
      100.0,
      100.0*c.captured_closed_1h_candles::double precision
        /c.expected_closed_1h_candles
    )
  end as retention_coverage_pct,
  case
    when clock_timestamp()<c.retention_horizon_end_utc
      then 'IN_PROGRESS'
    when c.captured_closed_1h_candles>=c.expected_closed_1h_candles
      then 'COMPLETE'
    else 'INCOMPLETE'
  end as retention_status,
  'V15_PARALLEL_SHADOW'::text as scientific_role,
  true as audit_only,
  false as counted_in_v14,
  false as mutation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from coverage c;

revoke all on public.alpha_hunter_candidate_retention_shadow_coverage_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_candidate_retention_shadow_coverage_v01
  to service_role;


create or replace view public.alpha_hunter_candidate_retention_shadow_status_v01
with (security_invoker=true,security_barrier=true) as
with latest_run as (
  select r.*
  from public.alpha_hunter_candidate_retention_shadow_runs_v01 r
  order by r.checked_at_utc desc,r.created_at desc
  limit 1
),
summary as (
  select
    count(*)::integer as target_episodes,
    count(distinct symbol)::integer as target_symbols,
    count(*) filter(where retention_status='IN_PROGRESS')::integer
      as in_progress_episodes,
    count(*) filter(where retention_status='COMPLETE')::integer
      as completed_coverage_episodes,
    count(*) filter(where retention_status='INCOMPLETE')::integer
      as incomplete_coverage_episodes,
    avg(retention_coverage_pct) as avg_retention_coverage_pct
  from public.alpha_hunter_candidate_retention_shadow_coverage_v01
)
select
  clock_timestamp() as checked_at_utc,
  r.collector_run_id,
  r.checked_at_utc as collector_checked_at_utc,
  r.result_class as collector_result_class,
  r.target_episode_count,
  r.target_symbol_count,
  r.symbols_requested,
  r.symbols_succeeded,
  r.symbols_failed,
  r.candles_considered,
  r.rows_attempted,
  r.error_classes,
  s.target_episodes,
  s.target_symbols,
  s.in_progress_episodes,
  s.completed_coverage_episodes,
  s.incomplete_coverage_episodes,
  s.avg_retention_coverage_pct,
  'V15_PARALLEL_SHADOW'::text as scientific_role,
  true as audit_only,
  false as counted_in_v14,
  false as mutation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from (select 1) anchor
left join latest_run r on true
left join summary s on true;

revoke all on public.alpha_hunter_candidate_retention_shadow_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_candidate_retention_shadow_status_v01
  to service_role;


create or replace view public.alpha_hunter_candidate_retention_timing_status_v01
with (security_invoker=true,security_barrier=true) as
with timing as (
  select *
  from public.alpha_hunter_candidate_retention_timing_v01
),
episode_stats as (
  select
    episode_id,
    count(*)::integer as retained_rows,
    count(*) filter(
      where capture_timing_class='FORWARD_FIRST_CYCLE'
    )::integer as forward_first_cycle_rows,
    count(*) filter(
      where capture_timing_class='LATE_BACKFILL'
    )::integer as late_backfill_rows,
    avg(capture_lag_minutes) as avg_capture_lag_minutes,
    max(capture_lag_minutes) as max_capture_lag_minutes
  from timing
  group by episode_id
),
targets as (
  select *
  from public.alpha_hunter_candidate_retention_shadow_targets_v02
),
joined as (
  select
    t.episode_id,
    t.symbol,
    t.strategy_id,
    t.direction,
    t.first_candidate_at_utc,
    t.retention_start_utc,
    t.retention_horizon_end_utc,
    t.expected_closed_1h_candles,
    coalesce(e.retained_rows,0) as retained_rows,
    coalesce(e.forward_first_cycle_rows,0) as forward_first_cycle_rows,
    coalesce(e.late_backfill_rows,0) as late_backfill_rows,
    e.avg_capture_lag_minutes,
    e.max_capture_lag_minutes
  from targets t
  left join episode_stats e using(episode_id)
)
select
  clock_timestamp() as checked_at_utc,
  count(*)::integer as target_episodes,
  count(*) filter(
    where clock_timestamp()>=retention_horizon_end_utc
  )::integer as matured_target_episodes,
  sum(expected_closed_1h_candles)::bigint as expected_closed_1h_candles,
  sum(retained_rows)::bigint as retained_rows,
  sum(forward_first_cycle_rows)::bigint as forward_first_cycle_rows,
  sum(late_backfill_rows)::bigint as late_backfill_rows,
  case
    when sum(expected_closed_1h_candles)=0 then null
    else 100.0*sum(retained_rows)::double precision
      /sum(expected_closed_1h_candles)
  end as total_retention_coverage_pct,
  case
    when sum(expected_closed_1h_candles)=0 then null
    else 100.0*sum(forward_first_cycle_rows)::double precision
      /sum(expected_closed_1h_candles)
  end as forward_first_cycle_coverage_pct,
  avg(avg_capture_lag_minutes) as avg_episode_capture_lag_minutes,
  max(max_capture_lag_minutes) as max_capture_lag_minutes,
  case
    when count(*)=0 then 'NO_TARGETS'
    when sum(retained_rows)=0 then 'WAITING_FOR_FIRST_CAPTURE'
    when sum(forward_first_cycle_rows)=0 and sum(late_backfill_rows)>0
      then 'BACKFILL_ONLY'
    when sum(forward_first_cycle_rows)>0
      then 'FORWARD_CAPTURE_PRESENT'
    else 'UNKNOWN'
  end as timing_status,
  'OPS_SLA_90_MINUTES_NOT_PROFITABILITY_RULE'::text as timing_policy,
  'V15_PARALLEL_SHADOW'::text as scientific_role,
  true as audit_only,
  false as counted_in_v14,
  false as timing_class_is_profitability_rule,
  false as mutation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from joined;

revoke all on public.alpha_hunter_candidate_retention_timing_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_candidate_retention_timing_status_v01
  to service_role;
