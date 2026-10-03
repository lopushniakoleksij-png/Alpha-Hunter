-- Alpha Hunter execution-cost benchmark collection v0.3
--
-- Purpose:
--   Continuously extend the existing append-only v0.2 order-minute benchmark
--   whenever new private fill/order evidence arrives.
--
-- Important scientific boundary:
--   the v0.2 minute-open benchmark mixes market movement and execution.
--   It is NOT slippage, NOT Alpha Hunter execution performance, and cannot
--   activate a realistic cost model by itself.

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname='alpha-hunter-order-minute-benchmark-v02-hourly'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
end;
$$;

select cron.schedule(
  'alpha-hunter-order-minute-benchmark-v02-hourly',
  '49 * * * *',
  'select private.alpha_hunter_collect_order_minute_benchmark_v02(25);'
);

create or replace view public.alpha_hunter_execution_cost_validation_readiness_v03
with (security_invoker=true,security_barrier=true)
as
with eligible as (
  select
    count(*)::bigint as eligible_market_fill_rows
  from public.alpha_hunter_execution_order_evidence_v01 e
  where e.order_type='MARKET'
    and e.order_created_at_utc is not null
    and e.fill_time_utc is not null
    and e.fill_price>0
    and e.fill_side in ('BUY','SELL')
    and e.symbol ~ '^[A-Z0-9]+USDT$'
),
bench as (
  select
    count(*)::bigint as benchmark_rows,
    count(*) filter(where evaluation_status='EVALUATED')::bigint
      as benchmark_evaluated_rows,
    count(*) filter(where evaluation_status='DATA_INSUFFICIENT')::bigint
      as benchmark_data_insufficient_rows,
    count(*) filter(where evaluation_status='DATA_INTEGRITY_ERROR')::bigint
      as benchmark_integrity_error_rows,
    min(fill_time_utc) as first_benchmark_fill_at_utc,
    max(fill_time_utc) as latest_benchmark_fill_at_utc
  from public.alpha_hunter_execution_order_minute_benchmark_v02
),
failures as (
  select count(*)::bigint as benchmark_failure_rows
  from public.alpha_hunter_execution_order_minute_benchmark_failures_v02
),
fees as (
  select
    count(*)::bigint as realized_fee_rows,
    count(*) filter(where realized_fee_bps is not null)::bigint
      as realized_fee_bps_rows,
    min(fill_time_utc) as first_fee_fill_at_utc,
    max(fill_time_utc) as latest_fee_fill_at_utc
  from public.alpha_hunter_realized_fee_observations_v01
),
model as (
  select
    count(*) filter(
      where upper(status)='ACTIVE'
        and validated_at_utc is not null
        and activated_at_utc is not null
    )::bigint as active_validated_model_rows
  from public.alpha_hunter_execution_cost_model_versions
),
floor as (
  select *
  from public.alpha_hunter_execution_cost_floor_status_v01
  where cost_scope='ALL'
  limit 1
)
select
  e.eligible_market_fill_rows,
  b.benchmark_rows,
  b.benchmark_evaluated_rows,
  b.benchmark_data_insufficient_rows,
  b.benchmark_integrity_error_rows,
  f.benchmark_failure_rows,
  case
    when e.eligible_market_fill_rows>0 then
      100.0*b.benchmark_rows/e.eligible_market_fill_rows
  end as coarse_benchmark_coverage_pct,
  b.first_benchmark_fill_at_utc,
  b.latest_benchmark_fill_at_utc,
  fees.realized_fee_rows,
  fees.realized_fee_bps_rows,
  fees.first_fee_fill_at_utc,
  fees.latest_fee_fill_at_utc,
  floor.observed_maker_fee_bps,
  floor.observed_taker_fee_bps,
  floor.observable_taker_round_trip_floor_p90_bps,
  floor.cost_model_validated,
  floor.realistic_net_r_claim_permitted,
  m.active_validated_model_rows,
  false as coarse_benchmark_is_slippage,
  false as alpha_hunter_execution_performance_claim_permitted,
  false as cost_model_activation_permitted,
  false as realistic_net_r_model_activation_permitted,
  'WAITING_FOR_DECISION_TIME_QUOTE_AND_FILL_SLIPPAGE_VALIDATION'::text
    as validation_status,
  'CAPTURE_PROSPECTIVE_DECISION_TIME_TOP_OF_BOOK_PLUS_MATCHED_FILL'::text
    as next_gate,
  true as evidence_collection_active,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from eligible e
cross join bench b
cross join failures f
cross join fees
cross join model m
cross join floor;

revoke all on public.alpha_hunter_execution_cost_validation_readiness_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_cost_validation_readiness_v03
  to service_role;
