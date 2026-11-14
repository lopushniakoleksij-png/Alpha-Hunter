-- ALPHA HUNTER P0: READ-ONLY TOP-LEVEL DATABASE WRITE PRESSURE
-- This query is safe for direct production inspection. It never exposes
-- raw query text, query parameters, roles, credentials, function bodies,
-- customer data, IP addresses or user IDs.
-- pg_stat_statements counters accumulate since stats_reset; results are NOT
-- current p95/p99, isolated benchmarks, or individual trigger timings.
-- This query MUST NOT be used to certify the authentic trigger graph.
SELECT
  (SELECT stats_reset FROM extensions.pg_stat_statements_info) AS accumulated_since_utc,
  current_setting('pg_stat_statements.track', true) AS statement_tracking_scope,
  current_setting('track_functions', true) AS function_tracking_scope,
  CASE
    WHEN query ILIKE '%alpha_hunter_symbol_snapshots%' THEN 'symbols'
    WHEN query ILIKE '%alpha_hunter_signal_features%' THEN 'features'
    WHEN query ILIKE '%alpha_hunter_signals%' THEN 'signals'
    WHEN query ILIKE '%alpha_hunter_readiness_observations_v01%' THEN 'readiness'
    WHEN query ILIKE '%alpha_hunter_snapshots%' THEN 'parents'
    ELSE 'other'
  END AS probable_core_family,
  left(md5(query),12) AS statement_fingerprint_only,
  calls,
  round(mean_exec_time::numeric,2) AS cumulative_mean_sql_ms,
  round(max_exec_time::numeric,2) AS cumulative_max_sql_ms,
  round(total_exec_time::numeric,2) AS cumulative_total_sql_ms,
  round(stddev_exec_time::numeric,2) AS cumulative_stddev_sql_ms,
  query ILIKE '%ON CONFLICT%' AS mentions_upsert,
  wal_bytes,
  rows AS returned_sql_rows
FROM extensions.pg_stat_statements
WHERE (query ILIKE '%alpha_hunter_symbol_snapshots%'
    OR query ILIKE '%alpha_hunter_readiness_observations_v01%'
    OR query ILIKE '%alpha_hunter_signal_features%'
    OR query ILIKE '%alpha_hunter_signals%'
    OR query ILIKE '%alpha_hunter_snapshots%')
  AND calls > 0
ORDER BY total_exec_time DESC
LIMIT 20;
