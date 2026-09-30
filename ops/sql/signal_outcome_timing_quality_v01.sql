-- Alpha Hunter legacy signal-outcome timing quality v0.1
--
-- Purpose:
--   Make the legacy OutcomeEvaluator timing defect explicit without deleting or
--   mutating historical evidence.
--
-- Scientific rule:
--   A legacy outcome may only be treated as bounded endpoint evidence when the
--   evaluation timestamp is within 30 minutes after its intended due horizon.
--
-- Important:
--   This does NOT repair the underlying price timestamp.
--   It only classifies evidence quality.
--   New scientific work should prefer timestamp-correct forward ledgers.

create or replace view private.alpha_hunter_signal_outcome_timing_quality_v01
with (security_invoker=true,security_barrier=true)
as
select
  o.signal_id,
  o.horizon_hours,
  s.symbol,
  s.detected_at_utc,
  s.detected_at_utc+make_interval(hours=>o.horizon_hours) as due_at_utc,
  o.evaluated_at_utc,
  extract(epoch from(
    o.evaluated_at_utc
      -(s.detected_at_utc+make_interval(hours=>o.horizon_hours))
  )) as lateness_seconds,
  extract(epoch from(
    o.evaluated_at_utc
      -(s.detected_at_utc+make_interval(hours=>o.horizon_hours))
  ))/60.0 as lateness_minutes,
  o.evaluation_price,
  o.return_pct,
  o.direction_adjusted_return_pct,
  o.target_hit,
  o.stop_hit,
  o.outcome_class,
  case
    when o.evaluated_at_utc
      < s.detected_at_utc+make_interval(hours=>o.horizon_hours)
      then 'EARLY_INVALID'
    when o.evaluated_at_utc
      <= s.detected_at_utc+make_interval(hours=>o.horizon_hours)+interval '30 minutes'
      then 'BOUNDED_WITHIN_30M'
    when o.evaluated_at_utc
      <= s.detected_at_utc+make_interval(hours=>o.horizon_hours)+interval '6 hours'
      then 'LATE_30M_TO_6H'
    when o.evaluated_at_utc
      <= s.detected_at_utc+make_interval(hours=>o.horizon_hours)+interval '24 hours'
      then 'LATE_6H_TO_24H'
    else 'LATE_GT_24H'
  end as timing_quality,
  (
    o.evaluated_at_utc
      >= s.detected_at_utc+make_interval(hours=>o.horizon_hours)
    and
    o.evaluated_at_utc
      <= s.detected_at_utc+make_interval(hours=>o.horizon_hours)+interval '30 minutes'
  ) as bounded_endpoint_evidence_permitted,
  false as exact_horizon_claim_permitted,
  false as stop_target_path_claim_permitted,
  'LEGACY_CURRENT_PRICE_EVALUATOR_TIMING_CLASSIFICATION_ONLY'::text
    as scientific_role,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_signal_outcomes o
join public.alpha_hunter_signals s using(signal_id);

create or replace view private.alpha_hunter_signal_outcome_timing_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  horizon_hours,
  timing_quality,
  count(*) as rows,
  count(distinct signal_id) as signals,
  avg(lateness_minutes) as avg_lateness_minutes,
  percentile_cont(0.5) within group(order by lateness_minutes)
    as median_lateness_minutes,
  percentile_cont(0.9) within group(order by lateness_minutes)
    as p90_lateness_minutes,
  max(lateness_minutes) as max_lateness_minutes,
  100.0*count(*) filter(where bounded_endpoint_evidence_permitted)
    /nullif(count(*),0) as bounded_endpoint_pct,
  false as exact_horizon_claim_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'LEGACY_TIMING_QUALITY_ONLY'::text as claim_ceiling,
  'NONE'::text as order_path
from private.alpha_hunter_signal_outcome_timing_quality_v01
group by horizon_hours,timing_quality;

revoke all on private.alpha_hunter_signal_outcome_timing_quality_v01
from public,anon,authenticated,service_role;
revoke all on private.alpha_hunter_signal_outcome_timing_status_v01
from public,anon,authenticated,service_role;

grant select on private.alpha_hunter_signal_outcome_timing_quality_v01
to service_role;
grant select on private.alpha_hunter_signal_outcome_timing_status_v01
to service_role;

-- No legacy outcome row is updated or deleted by this script.
