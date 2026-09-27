-- Alpha Hunter V15 candidate retention real-time coverage v0.3
--
-- Operations/scientific observability only. Lives under ops/sql and is outside
-- the sealed V14 scientific fingerprint.
--
-- The v0.1/v0.2 full-horizon coverage denominator is useful only after an
-- episode matures. For in-progress episodes it can look artificially low
-- because future candles do not exist yet.
--
-- This audit compares retained rows with the number of fully closed 1H candles
-- that should exist by clock time, while still separating prompt forward
-- capture from late bootstrap/backfill.

create or replace view public.alpha_hunter_candidate_retention_realtime_coverage_v03
with (security_invoker=true,security_barrier=true) as
with captured as (
  select
    c.episode_id,
    count(*)::integer as retained_rows,
    count(*) filter(
      where t.capture_timing_class='FORWARD_FIRST_CYCLE'
    )::integer as forward_first_cycle_rows,
    count(*) filter(
      where t.capture_timing_class='LATE_BACKFILL'
    )::integer as late_backfill_rows,
    min(c.candle_open_utc) as first_candle_open_utc,
    max(c.candle_open_utc) as latest_candle_open_utc,
    min(c.captured_at_utc) as first_captured_at_utc,
    max(c.captured_at_utc) as latest_captured_at_utc
  from public.alpha_hunter_candidate_retention_shadow_candles_v01 c
  join public.alpha_hunter_candidate_retention_timing_v01 t
    on t.retention_row_id=c.retention_row_id
  group by c.episode_id
),
joined as (
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
    greatest(
      0,
      least(
        t.expected_closed_1h_candles,
        floor(
          extract(
            epoch from (
              least(clock_timestamp(),t.retention_horizon_end_utc)
              - t.retention_start_utc
            )
          )/3600.0
        )::integer
      )
    ) as expected_closed_1h_candles_by_now,
    coalesce(c.retained_rows,0) as retained_rows,
    coalesce(c.forward_first_cycle_rows,0) as forward_first_cycle_rows,
    coalesce(c.late_backfill_rows,0) as late_backfill_rows,
    c.first_candle_open_utc,
    c.latest_candle_open_utc,
    c.first_captured_at_utc,
    c.latest_captured_at_utc
  from public.alpha_hunter_candidate_retention_shadow_targets_v02 t
  left join captured c using(episode_id)
)
select
  clock_timestamp() as checked_at_utc,
  j.*,
  case
    when j.expected_closed_1h_candles_by_now=0 then null
    else least(
      100.0,
      100.0*j.retained_rows::double precision
        /j.expected_closed_1h_candles_by_now
    )
  end as retention_coverage_to_date_pct,
  case
    when j.expected_closed_1h_candles_by_now=0 then null
    else least(
      100.0,
      100.0*j.forward_first_cycle_rows::double precision
        /j.expected_closed_1h_candles_by_now
    )
  end as forward_first_cycle_coverage_to_date_pct,
  case
    when j.expected_closed_1h_candles=0 then null
    else least(
      100.0,
      100.0*j.retained_rows::double precision
        /j.expected_closed_1h_candles
    )
  end as full_horizon_retention_coverage_pct,
  case
    when j.expected_closed_1h_candles_by_now=0
      then 'WAITING_FOR_FIRST_DUE_CANDLE'
    when j.retained_rows>=j.expected_closed_1h_candles_by_now
      then 'COMPLETE_TO_DATE'
    else 'LAGGING_TO_DATE'
  end as realtime_capture_status,
  case
    when clock_timestamp()>=j.retention_horizon_end_utc
      then 'MATURED'
    else 'IN_PROGRESS'
  end as horizon_status,
  'OPS_REALTIME_COVERAGE_NOT_PROFITABILITY_RULE'::text as coverage_policy,
  'V15_PARALLEL_SHADOW'::text as scientific_role,
  true as audit_only,
  false as counted_in_v14,
  false as coverage_metric_is_profitability_rule,
  false as mutation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from joined j;

revoke all on public.alpha_hunter_candidate_retention_realtime_coverage_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_candidate_retention_realtime_coverage_v03
  to service_role;


create or replace view public.alpha_hunter_candidate_retention_realtime_status_v03
with (security_invoker=true,security_barrier=true) as
with c as (
  select *
  from public.alpha_hunter_candidate_retention_realtime_coverage_v03
)
select
  clock_timestamp() as checked_at_utc,
  count(*)::integer as target_episodes,
  count(distinct symbol)::integer as target_symbols,
  count(*) filter(where horizon_status='MATURED')::integer
    as matured_target_episodes,
  count(*) filter(where horizon_status='IN_PROGRESS')::integer
    as in_progress_target_episodes,
  count(*) filter(
    where expected_closed_1h_candles_by_now>0
  )::integer as targets_with_due_candles,
  count(*) filter(
    where realtime_capture_status='WAITING_FOR_FIRST_DUE_CANDLE'
  )::integer as waiting_first_due_candle_targets,
  count(*) filter(
    where realtime_capture_status='COMPLETE_TO_DATE'
  )::integer as complete_to_date_targets,
  count(*) filter(
    where realtime_capture_status='LAGGING_TO_DATE'
  )::integer as lagging_to_date_targets,
  sum(expected_closed_1h_candles_by_now)::bigint
    as expected_closed_1h_candles_by_now,
  sum(retained_rows)::bigint as retained_rows,
  sum(forward_first_cycle_rows)::bigint as forward_first_cycle_rows,
  sum(late_backfill_rows)::bigint as late_backfill_rows,
  case
    when sum(expected_closed_1h_candles_by_now)=0 then null
    else least(
      100.0,
      100.0*sum(retained_rows)::double precision
        /sum(expected_closed_1h_candles_by_now)
    )
  end as retention_coverage_to_date_pct,
  case
    when sum(expected_closed_1h_candles_by_now)=0 then null
    else least(
      100.0,
      100.0*sum(forward_first_cycle_rows)::double precision
        /sum(expected_closed_1h_candles_by_now)
    )
  end as forward_first_cycle_coverage_to_date_pct,
  case
    when count(*)=0 then 'NO_TARGETS'
    when count(*) filter(
      where expected_closed_1h_candles_by_now>0
    )=0 then 'WAITING_FOR_FIRST_DUE_CANDLE'
    when count(*) filter(
      where realtime_capture_status='LAGGING_TO_DATE'
    )=0 then 'PASS_TO_DATE'
    else 'DEGRADED_TO_DATE'
  end as realtime_capture_health,
  'OPS_REALTIME_COVERAGE_NOT_PROFITABILITY_RULE'::text as coverage_policy,
  'V15_PARALLEL_SHADOW'::text as scientific_role,
  true as audit_only,
  false as counted_in_v14,
  false as coverage_metric_is_profitability_rule,
  false as mutation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from c;

revoke all on public.alpha_hunter_candidate_retention_realtime_status_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_candidate_retention_realtime_status_v03
  to service_role;
