-- Alpha Hunter V15 retention -> V14 outcome coverage recovery audit v0.1
--
-- Parallel-shadow scientific observability only. Lives under ops/sql and is
-- outside the sealed V14 scientific fingerprint.
--
-- Purpose:
-- Compare matured V14 candidate episodes with the independent V15 retention
-- lane to determine whether candidate retention can recover canonical 24h path
-- coverage. Late bootstrap/backfill is kept explicitly diagnostic; only full
-- forward-first-cycle coverage may be labeled forward recovery.
--
-- This migration does not mutate V14 outcomes, paper economics, strategy logic,
-- profitability rules, trade permission, or order paths.

create or replace view public.alpha_hunter_v15_retention_outcome_recovery_v01
with (security_invoker=true,security_barrier=true) as
with active as (
  select
    e.spec_id,
    v.started_at_utc
  from public.alpha_hunter_test_engine_latest_v01 e
  join public.alpha_hunter_profitability_validation_status_v01 v
    on v.spec_id=e.spec_id
  order by e.evaluated_at_utc desc
  limit 1
),
targets as (
  select t.*
  from public.alpha_hunter_candidate_retention_shadow_targets_v02 t
  join active a
    on t.first_candidate_at_utc>=a.started_at_utc
),
retained as (
  select
    c.episode_id,
    count(*)::integer as retained_rows,
    count(*) filter(
      where tm.capture_timing_class='FORWARD_FIRST_CYCLE'
    )::integer as forward_first_cycle_rows,
    count(*) filter(
      where tm.capture_timing_class='LATE_BACKFILL'
    )::integer as late_backfill_rows,
    min(c.candle_open_utc) as first_retained_candle_open_utc,
    max(c.candle_open_utc) as latest_retained_candle_open_utc,
    min(c.captured_at_utc) as first_retained_at_utc,
    max(c.captured_at_utc) as latest_retained_at_utc
  from public.alpha_hunter_candidate_retention_shadow_candles_v01 c
  join public.alpha_hunter_candidate_retention_timing_v01 tm
    on tm.retention_row_id=c.retention_row_id
  group by c.episode_id
),
outcomes as (
  select o.*
  from public.alpha_hunter_strategy_forward_outcomes_v01 o
  join active a
    on o.first_candidate_at_utc>=a.started_at_utc
  where o.horizon_hours=24
),
joined as (
  select
    a.spec_id,
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

    coalesce(r.retained_rows,0) as retained_rows,
    coalesce(r.forward_first_cycle_rows,0) as forward_first_cycle_rows,
    coalesce(r.late_backfill_rows,0) as late_backfill_rows,
    r.first_retained_candle_open_utc,
    r.latest_retained_candle_open_utc,
    r.first_retained_at_utc,
    r.latest_retained_at_utc,

    o.evaluated_at_utc as v14_24h_evaluated_at_utc,
    o.entry_trigger_status as v14_entry_trigger_status,
    o.path_outcome_class as v14_path_outcome_class,
    o.path_measurement_quality as v14_path_measurement_quality,
    o.expected_path_candle_count as v14_expected_path_candle_count,
    o.observed_path_candle_count as v14_observed_path_candle_count,
    o.path_coverage_pct as v14_path_coverage_pct,
    o.ordering_ambiguous as v14_ordering_ambiguous,
    o.fill_price as v14_fill_price,
    o.cost_adjustment_status as v14_cost_adjustment_status
  from active a
  join targets t on true
  left join retained r using(episode_id)
  left join outcomes o using(episode_id)
)
select
  clock_timestamp() as checked_at_utc,
  j.*,

  (clock_timestamp()>=j.retention_horizon_end_utc) as retention_horizon_matured,

  (
    j.expected_closed_1h_candles>0
    and j.retained_rows>=j.expected_closed_1h_candles
  ) as retention_full_coverage,

  (
    j.expected_closed_1h_candles>0
    and j.forward_first_cycle_rows>=j.expected_closed_1h_candles
  ) as retention_forward_full_coverage,

  case
    when j.expected_closed_1h_candles=0 then null
    else least(
      100.0,
      100.0*j.retained_rows::double precision
        /j.expected_closed_1h_candles
    )
  end as retention_full_horizon_coverage_pct,

  case
    when j.expected_closed_1h_candles=0 then null
    else least(
      100.0,
      100.0*j.forward_first_cycle_rows::double precision
        /j.expected_closed_1h_candles
    )
  end as retention_forward_full_horizon_coverage_pct,

  case
    when clock_timestamp()<j.retention_horizon_end_utc
      then 'IN_PROGRESS'
    when j.v14_24h_evaluated_at_utc is null
      then 'WAITING_FOR_V14_24H_OUTCOME'
    when j.v14_path_measurement_quality='COMPLETE_ENOUGH'
      then 'V14_ALREADY_COMPLETE'
    when j.expected_closed_1h_candles>0
     and j.forward_first_cycle_rows>=j.expected_closed_1h_candles
      then 'FORWARD_RETENTION_RECOVERY_PROVEN'
    when j.expected_closed_1h_candles>0
     and j.retained_rows>=j.expected_closed_1h_candles
     and j.late_backfill_rows>0
      then 'BACKFILL_RECOVERY_DIAGNOSTIC_ONLY'
    when j.expected_closed_1h_candles>0
     and j.retained_rows<j.expected_closed_1h_candles
      then 'RETENTION_COVERAGE_INCOMPLETE'
    else 'UNRESOLVED'
  end as coverage_recovery_class,

  case
    when j.v14_24h_evaluated_at_utc is null then 'NO_V14_24H_OUTCOME'
    when j.v14_path_measurement_quality='COMPLETE_ENOUGH'
      then 'V14_COMPLETE_ENOUGH'
    when j.v14_path_measurement_quality='INCOMPLETE_CANONICAL_CANDLE_COVERAGE'
      then 'V14_INCOMPLETE_CANONICAL_CANDLE_COVERAGE'
    else coalesce(j.v14_path_measurement_quality,'V14_UNKNOWN')
  end as v14_coverage_class,

  'V15_PARALLEL_SHADOW_COVERAGE_RECOVERY_AUDIT'::text as scientific_role,
  true as audit_only,
  false as counted_in_v14,
  false as profitability_rule_change_permitted,
  false as mutation_permitted,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from joined j;


revoke all on public.alpha_hunter_v15_retention_outcome_recovery_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_v15_retention_outcome_recovery_v01
  to service_role;


create or replace view public.alpha_hunter_v15_retention_outcome_recovery_status_v01
with (security_invoker=true,security_barrier=true) as
with r as (
  select *
  from public.alpha_hunter_v15_retention_outcome_recovery_v01
),
matured as (
  select *
  from r
  where retention_horizon_matured
)
select
  clock_timestamp() as checked_at_utc,
  max(spec_id) as spec_id,

  count(*)::integer as matured_target_episodes,
  count(*) filter(
    where v14_24h_evaluated_at_utc is not null
  )::integer as matured_with_v14_24h_outcome,

  count(*) filter(
    where v14_coverage_class='V14_COMPLETE_ENOUGH'
  )::integer as v14_complete_enough_rows,

  count(*) filter(
    where v14_coverage_class='V14_INCOMPLETE_CANONICAL_CANDLE_COVERAGE'
  )::integer as v14_incomplete_candle_coverage_rows,

  count(*) filter(
    where retention_full_coverage
  )::integer as retention_full_coverage_rows,

  count(*) filter(
    where retention_forward_full_coverage
  )::integer as retention_forward_full_coverage_rows,

  count(*) filter(
    where coverage_recovery_class='FORWARD_RETENTION_RECOVERY_PROVEN'
  )::integer as forward_recovery_proven_rows,

  count(*) filter(
    where coverage_recovery_class='BACKFILL_RECOVERY_DIAGNOSTIC_ONLY'
  )::integer as backfill_recovery_diagnostic_rows,

  count(*) filter(
    where coverage_recovery_class='RETENTION_COVERAGE_INCOMPLETE'
  )::integer as retention_incomplete_rows,

  count(*) filter(
    where coverage_recovery_class='WAITING_FOR_V14_24H_OUTCOME'
  )::integer as waiting_for_v14_24h_outcome_rows,

  case
    when count(*)=0 then 'WAITING_FOR_FIRST_MATURED_TARGET'
    when count(*) filter(
      where coverage_recovery_class='FORWARD_RETENTION_RECOVERY_PROVEN'
    )>0 then 'FORWARD_RECOVERY_EVIDENCE_PRESENT'
    when count(*) filter(
      where coverage_recovery_class='BACKFILL_RECOVERY_DIAGNOSTIC_ONLY'
    )>0 then 'BACKFILL_RECOVERY_ONLY'
    else 'NO_RECOVERY_EVIDENCE_YET'
  end as recovery_evidence_status,

  'V15_PARALLEL_SHADOW_COVERAGE_RECOVERY_AUDIT'::text as scientific_role,
  true as audit_only,
  false as counted_in_v14,
  false as profitability_rule_change_permitted,
  false as mutation_permitted,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from matured;

revoke all on public.alpha_hunter_v15_retention_outcome_recovery_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_v15_retention_outcome_recovery_status_v01
  to service_role;
