-- Alpha Hunter V15 candidate-retention parallel shadow v0.1
--
-- AUDIT/PARALLEL-SHADOW ONLY. Lives under ops/sql and is outside the sealed
-- V14 scientific fingerprint.
--
-- Objective:
-- Preserve future fully closed 1H candles for prospectively selected candidate
-- episodes even when their symbol drops out of the canonical ranked snapshot
-- set. This evidence is explicitly excluded from V14 counted outcomes.
--
-- No second universe scanner:
-- Targets come only from already-persisted sealed strategy episodes and their
-- first SHADOW_CANDIDATE observation.

create or replace view public.alpha_hunter_candidate_retention_targets_v01
with (security_invoker=true,security_barrier=true) as
with first_candidate as (
  select distinct on (o.strategy_instance_id)
    o.strategy_instance_id as episode_id,
    o.observation_id as first_candidate_observation_id,
    o.symbol,
    o.strategy_id,
    o.direction,
    o.observed_at_utc as first_candidate_at_utc,
    o.action as first_candidate_action
  from public.alpha_hunter_strategy_observations_v01 o
  where o.strategy_instance_id is not null
    and o.status='SHADOW_CANDIDATE'
    and o.action in ('EXECUTE_NOW','PLACE_LIMIT')
  order by o.strategy_instance_id,o.observed_at_utc,o.observation_id
)
select
  e.episode_id,
  c.first_candidate_observation_id,
  e.symbol,
  e.strategy_id,
  e.direction,
  e.first_observed_at_utc,
  c.first_candidate_at_utc,
  c.first_candidate_action,
  date_trunc('hour',c.first_candidate_at_utc)+interval '1 hour'
    as retention_start_utc,
  e.first_observed_at_utc+interval '24 hours'
    as retention_horizon_end_utc,
  greatest(
    0,
    floor(
      extract(
        epoch from (
          e.first_observed_at_utc+interval '24 hours'
          - (date_trunc('hour',c.first_candidate_at_utc)+interval '1 hour')
        )
      )/3600.0
    )::integer
  ) as expected_closed_1h_candles,
  'SEALED_CANDIDATE_EPISODES_ONLY'::text as target_source,
  'V15_PARALLEL_SHADOW'::text as scientific_role,
  true as audit_only,
  false as counted_in_v14,
  false as mutation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from first_candidate c
join public.alpha_hunter_strategy_episodes_v01 e
  on e.episode_id=c.episode_id
where e.first_observed_at_utc+interval '24 hours' > clock_timestamp()-interval '2 hours'
  and c.first_candidate_at_utc <= clock_timestamp();

revoke all on public.alpha_hunter_candidate_retention_targets_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_candidate_retention_targets_v01
  to service_role;


create table if not exists public.alpha_hunter_candidate_retention_shadow_candles_v01 (
  retention_row_id text primary key,
  episode_id text not null,
  first_candidate_observation_id text not null,
  symbol text not null,
  strategy_id text not null,
  direction text not null check (direction in ('LONG','SHORT')),
  first_observed_at_utc timestamptz not null,
  first_candidate_at_utc timestamptz not null,
  first_candidate_action text not null
    check (first_candidate_action in ('EXECUTE_NOW','PLACE_LIMIT')),
  retention_start_utc timestamptz not null,
  retention_horizon_end_utc timestamptz not null,

  candle_open_utc timestamptz not null,
  candle_known_at_utc timestamptz not null,
  captured_at_utc timestamptz not null,
  open_price double precision not null,
  high_price double precision not null,
  low_price double precision not null,
  close_price double precision not null,
  base_volume double precision,
  quote_volume double precision,

  source_exchange text not null default 'BITGET'
    check (source_exchange='BITGET'),
  source_endpoint text not null default '/api/v2/mix/market/candles'
    check (source_endpoint='/api/v2/mix/market/candles'),
  product_type text not null default 'USDT-FUTURES'
    check (product_type='USDT-FUTURES'),
  granularity text not null default '1H'
    check (granularity='1H'),
  fully_closed boolean not null default true check (fully_closed=true),

  scientific_role text not null default 'V15_PARALLEL_SHADOW'
    check (scientific_role='V15_PARALLEL_SHADOW'),
  target_source text not null default 'SEALED_CANDIDATE_EPISODES_ONLY'
    check (target_source='SEALED_CANDIDATE_EPISODES_ONLY'),
  audit_only boolean not null default true check (audit_only=true),
  counted_in_v14 boolean not null default false check (counted_in_v14=false),
  mutation_permitted boolean not null default false check (mutation_permitted=false),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),

  created_at timestamptz not null default clock_timestamp(),
  unique(episode_id,candle_open_utc),
  check (candle_known_at_utc=candle_open_utc+interval '1 hour'),
  check (candle_open_utc>=retention_start_utc),
  check (candle_open_utc+interval '1 hour'<=retention_horizon_end_utc),
  check (captured_at_utc>=candle_known_at_utc)
);

create index if not exists idx_ah_candidate_retention_shadow_episode_v01
  on public.alpha_hunter_candidate_retention_shadow_candles_v01(
    episode_id,candle_open_utc
  );

create index if not exists idx_ah_candidate_retention_shadow_symbol_v01
  on public.alpha_hunter_candidate_retention_shadow_candles_v01(
    symbol,candle_open_utc
  );

alter table public.alpha_hunter_candidate_retention_shadow_candles_v01
  enable row level security;

revoke all on table public.alpha_hunter_candidate_retention_shadow_candles_v01
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_candidate_retention_shadow_candles_v01
  to service_role;

drop trigger if exists trg_ah_candidate_retention_shadow_append_only
  on public.alpha_hunter_candidate_retention_shadow_candles_v01;
create trigger trg_ah_candidate_retention_shadow_append_only
before update or delete
on public.alpha_hunter_candidate_retention_shadow_candles_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create table if not exists public.alpha_hunter_candidate_retention_shadow_runs_v01 (
  collector_run_id text primary key,
  checked_at_utc timestamptz not null,
  target_episode_count integer not null,
  target_symbol_count integer not null,
  symbols_requested integer not null,
  symbols_succeeded integer not null,
  symbols_failed integer not null,
  candles_considered integer not null,
  rows_attempted integer not null,
  result_class text not null
    check (result_class in ('PASS','DEGRADED','NO_TARGETS')),
  error_classes jsonb not null default '{}'::jsonb,

  public_get_only boolean not null default true check (public_get_only=true),
  private_credentials_required boolean not null default false
    check (private_credentials_required=false),
  universe_discovery_permitted boolean not null default false
    check (universe_discovery_permitted=false),
  audit_only boolean not null default true check (audit_only=true),
  counted_in_v14 boolean not null default false check (counted_in_v14=false),
  mutation_permitted boolean not null default false check (mutation_permitted=false),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),

  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_candidate_retention_shadow_runs_v01
  enable row level security;

revoke all on table public.alpha_hunter_candidate_retention_shadow_runs_v01
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_candidate_retention_shadow_runs_v01
  to service_role;

drop trigger if exists trg_ah_candidate_retention_shadow_runs_append_only
  on public.alpha_hunter_candidate_retention_shadow_runs_v01;
create trigger trg_ah_candidate_retention_shadow_runs_append_only
before update or delete
on public.alpha_hunter_candidate_retention_shadow_runs_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace view public.alpha_hunter_candidate_retention_shadow_coverage_v01
with (security_invoker=true,security_barrier=true) as
with targets as (
  select *
  from public.alpha_hunter_candidate_retention_targets_v01
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
