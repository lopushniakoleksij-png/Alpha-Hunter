-- Alpha Hunter P0 / Supabase Logs Explorer ClickHouse SQL (NOT PostgreSQL).
-- READ-ONLY, privacy-preserving aggregate. Does NOT export parsed.context,
-- PostgreSQL query SQL, raw request headers, JWTs, IP addresses or function bodies.
-- Verified on 2026-11-08 with:
--   iso_timestamp_start = 2026-11-08T08:00:00Z
--   iso_timestamp_end   = 2026-11-08T10:39:00Z
-- This time window yielded total=25, payoff_function=21,
-- percentile_context=20, cost_floor_context=1, no_context=3.
-- Different time windows will have different counts; do not treat as p95/p99
-- or claim full trigger latency solely from interrupted SQL location.
SELECT
  count() AS total_postgres_timeout_events,
  countIf(
    positionCaseInsensitive(
      log_attributes['parsed.context'],
      'alpha_hunter_capture_payoff_geometry_health_v01'
    ) > 0
  ) AS payoff_function_present,
  countIf(
    positionCaseInsensitive(log_attributes['parsed.context'], 'percentile_cont') > 0
  ) AS interrupted_in_percentile_context,
  countIf(
    positionCaseInsensitive(
      log_attributes['parsed.context'],
      'alpha_hunter_execution_cost_floor_status_v01'
    ) > 0
  ) AS interrupted_in_cost_floor_context,
  countIf(length(log_attributes['parsed.context']) = 0)
    AS missing_structured_context,
  uniqExact(log_attributes['parsed.query_id']) AS distinct_query_ids
FROM logs
WHERE source = 'postgres_logs'
  AND event_message = 'canceling statement due to statement timeout';
