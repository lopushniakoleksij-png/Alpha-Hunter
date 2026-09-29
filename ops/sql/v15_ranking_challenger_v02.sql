-- Alpha Hunter V15 early-ranking challenger v0.2
--
-- PARALLEL SHADOW ONLY. This file lives under ops/sql so it is outside the
-- sealed V14 scientific fingerprint.
--
-- Purpose:
--   Deep-investigate a very small set of early, prefilter-eligible symbols
--   that production did not select for the canonical deep scan.
--
-- Safety / scientific isolation:
--   * canonical production selector is not mutated;
--   * no threshold is changed;
--   * no order path is created;
--   * no V14 outcome is counted;
--   * candidate selection uses only contemporaneous canonical universe data;
--   * no mover answer-key or future outcome is used to select a target.

create or replace view public.alpha_hunter_v15_ranking_challenger_targets_v02
with (security_invoker=true,security_barrier=true)
as
with latest_run as (
  select
    u.selection_run_id,
    max(u.observed_at_utc) as observed_at_utc
  from public.alpha_hunter_universe_hourly u
  where u.observed_at_utc >= clock_timestamp()-interval '2 hours'
  group by u.selection_run_id
  order by max(u.observed_at_utc) desc,u.selection_run_id desc
  limit 1
),
current_rows as (
  select u.*
  from public.alpha_hunter_universe_hourly u
  join latest_run r
    on r.selection_run_id=u.selection_run_id
  where u.prefilter_eligible is true
    and u.deep_scan_selected is false
    and abs(u.change_24h_pct)<5.0
    and u.quote_volume_24h>0
),
paired as (
  select
    c.observation_id,
    c.selection_run_id,
    c.observed_at_utc,
    c.symbol,
    c.last_price,
    c.change_24h_pct,
    c.quote_volume_24h,
    c.measurement_quality,
    p.observation_id as previous_observation_id,
    p.observed_at_utc as previous_observed_at_utc,
    p.quote_volume_24h as previous_quote_volume_24h,
    extract(epoch from (c.observed_at_utc-p.observed_at_utc))
      as previous_gap_seconds
  from current_rows c
  join lateral (
    select p.*
    from public.alpha_hunter_universe_hourly p
    where p.symbol=c.symbol
      and p.observed_at_utc<=c.observed_at_utc-interval '5 minutes'
      and p.observed_at_utc>=c.observed_at_utc-interval '30 minutes'
      and p.quote_volume_24h>0
    order by p.observed_at_utc desc,p.observation_id desc
    limit 1
  ) p on true
),
features as (
  select
    p.*,
    ln(p.quote_volume_24h/p.previous_quote_volume_24h)
      *3600.0/nullif(p.previous_gap_seconds,0)
      as hourly_normalized_volume_log_growth
  from paired p
  where p.previous_gap_seconds between 300 and 1800
    and p.previous_quote_volume_24h>0
),
ranked as (
  select
    f.*,
    row_number() over(
      order by
        f.hourly_normalized_volume_log_growth desc,
        abs(f.change_24h_pct) asc,
        f.quote_volume_24h desc,
        f.symbol asc
    ) as challenger_rank
  from features f
  where f.hourly_normalized_volume_log_growth>0
)
select
  observation_id as target_observation_id,
  selection_run_id,
  observed_at_utc as target_observed_at_utc,
  symbol,
  last_price,
  change_24h_pct,
  quote_volume_24h,
  previous_observation_id,
  previous_observed_at_utc,
  previous_quote_volume_24h,
  previous_gap_seconds,
  hourly_normalized_volume_log_growth,
  challenger_rank,
  measurement_quality,
  'EARLY_VOLUME_GROWTH_TOP5_V02'::text as challenger_rule,
  false as production_selector_changed,
  false as outcome_evidence_used,
  false as counted_in_v14,
  false as t0_authorized,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path,
  'v15-ranking-challenger-v0.2'::text as model_version
from ranked
where challenger_rank<=5;

revoke all on public.alpha_hunter_v15_ranking_challenger_targets_v02
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_v15_ranking_challenger_targets_v02
  to service_role;


create table if not exists public.alpha_hunter_v15_ranking_challenger_observations_v01 (
  observation_id text primary key,
  challenger_run_id text not null,
  selection_run_id text not null,
  target_observation_id text not null,
  target_observed_at_utc timestamptz not null,
  deep_scanned_at_utc timestamptz not null default clock_timestamp(),
  symbol text not null,
  challenger_rank integer not null check(challenger_rank between 1 and 5),
  source_change_24h_pct double precision,
  source_quote_volume_24h double precision,
  previous_gap_seconds double precision,
  hourly_normalized_volume_log_growth double precision,
  collection_status text not null,
  error_class text,
  legacy_state text,
  legacy_trade_permission_would_be boolean,
  legacy_v7_trade_ready_would_be boolean,
  market_phase text,
  opportunity_timing text,
  behaviour_score double precision,
  best_shadow_strategy_id text,
  best_shadow_strategy_direction text,
  best_shadow_strategy_action text,
  best_shadow_strategy_rr double precision,
  best_shadow_strategy_score double precision,
  shadow_candidate_count integer,
  diagnostic jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'V15_PARALLEL_RANKING_CHALLENGER',
  model_version text not null default 'v15-ranking-challenger-v0.2',
  public_get_only boolean not null default true check(public_get_only=true),
  counted_in_v14 boolean not null default false check(counted_in_v14=false),
  production_selector_changed boolean not null default false
    check(production_selector_changed=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_v15_ranking_challenger_observations_v01
  enable row level security;

revoke all on table
  public.alpha_hunter_v15_ranking_challenger_observations_v01
  from public,anon,authenticated,service_role;
grant select,insert on table
  public.alpha_hunter_v15_ranking_challenger_observations_v01
  to service_role;

drop trigger if exists trg_ah_v15_ranking_challenger_observations_append_only
  on public.alpha_hunter_v15_ranking_challenger_observations_v01;
create trigger trg_ah_v15_ranking_challenger_observations_append_only
before update or delete
on public.alpha_hunter_v15_ranking_challenger_observations_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

create index if not exists idx_ah_v15_ranking_challenger_obs_time
on public.alpha_hunter_v15_ranking_challenger_observations_v01(
  deep_scanned_at_utc desc
);

create index if not exists idx_ah_v15_ranking_challenger_obs_symbol
on public.alpha_hunter_v15_ranking_challenger_observations_v01(
  symbol,deep_scanned_at_utc desc
);


create table if not exists public.alpha_hunter_v15_ranking_challenger_runs_v01 (
  challenger_run_id text primary key,
  checked_at_utc timestamptz not null,
  selection_run_id text,
  target_count integer not null default 0,
  succeeded_count integer not null default 0,
  failed_count integer not null default 0,
  legacy_ready_would_be_count integer not null default 0,
  shadow_candidate_count integer not null default 0,
  result_class text not null,
  error_classes jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'V15_PARALLEL_RANKING_CHALLENGER',
  model_version text not null default 'v15-ranking-challenger-v0.2',
  public_get_only boolean not null default true check(public_get_only=true),
  counted_in_v14 boolean not null default false check(counted_in_v14=false),
  production_selector_changed boolean not null default false
    check(production_selector_changed=false),
  threshold_change_permitted boolean not null default false
    check(threshold_change_permitted=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_v15_ranking_challenger_runs_v01
  enable row level security;

revoke all on table public.alpha_hunter_v15_ranking_challenger_runs_v01
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_v15_ranking_challenger_runs_v01
  to service_role;

drop trigger if exists trg_ah_v15_ranking_challenger_runs_append_only
  on public.alpha_hunter_v15_ranking_challenger_runs_v01;
create trigger trg_ah_v15_ranking_challenger_runs_append_only
before update or delete
on public.alpha_hunter_v15_ranking_challenger_runs_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

create index if not exists idx_ah_v15_ranking_challenger_runs_time
on public.alpha_hunter_v15_ranking_challenger_runs_v01(
  checked_at_utc desc
);
