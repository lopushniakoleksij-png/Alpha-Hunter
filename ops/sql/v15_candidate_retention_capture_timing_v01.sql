-- Alpha Hunter V15 candidate retention capture timing audit v0.1
--
-- Operations/scientific observability only. Lives under ops/sql and is outside
-- the sealed V14 scientific fingerprint.
--
-- Purpose:
-- Distinguish prompt forward capture from late historical backfill so the V15
-- shadow lane cannot overstate prospective retention quality.
--
-- Operational timing class only:
-- - FORWARD_FIRST_CYCLE: captured within 90 minutes after the candle became
--   fully closed/known.
-- - LATE_BACKFILL: captured later than that.
--
-- The 90-minute boundary is an ops SLA, not a profitability rule and not V14
-- counted evidence.

create or replace view public.alpha_hunter_candidate_retention_timing_v01
with (security_invoker=true,security_barrier=true) as
select
  c.retention_row_id,
  c.episode_id,
  c.first_candidate_observation_id,
  c.symbol,
  c.strategy_id,
  c.direction,
  c.first_observed_at_utc,
  c.first_candidate_at_utc,
  c.retention_start_utc,
  c.retention_horizon_end_utc,
  c.candle_open_utc,
  c.candle_known_at_utc,
  c.captured_at_utc,
  extract(
    epoch from (c.captured_at_utc-c.candle_known_at_utc)
  )/60.0 as capture_lag_minutes,
  case
    when c.captured_at_utc<=c.candle_known_at_utc+interval '90 minutes'
      then 'FORWARD_FIRST_CYCLE'
    else 'LATE_BACKFILL'
  end as capture_timing_class,
  c.fully_closed,
  c.scientific_role,
  c.target_source,
  c.audit_only,
  c.counted_in_v14,
  false as timing_class_is_profitability_rule,
  false as mutation_permitted,
  c.shadow_only,
  c.trade_permission,
  c.production_promotion_permitted,
  c.order_path
from public.alpha_hunter_candidate_retention_shadow_candles_v01 c;

revoke all on public.alpha_hunter_candidate_retention_timing_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_candidate_retention_timing_v01
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
  from public.alpha_hunter_candidate_retention_targets_v01
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
