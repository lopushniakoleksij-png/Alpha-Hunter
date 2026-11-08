-- ALPHA HUNTER / P0 / READ-ONLY PAYOFF-TRIGGER LATENCY DIAGNOSTICS V0.1
-- Created 2026-11-08; previously validated constituent SELECTs on live Supabase.
-- USE: reproduce correlation / index statistics without modifying production.
-- NO EXPLAIN ANALYZE, performance probes, DDL, role changes, production credentials,
-- mutation, scanner invocation, paper-admission, orders, or source body extraction.
-- A retained freeze does NOT prove that failed/rolled-back attempts had none.
-- A missing child is a persistence failure; source errors may justify lower
-- signal/feature/readiness counts but not absent canonical symbol children.
-- Child published latency includes network, timeouts, retry backoff, and all
-- synchronous triggers; it is NOT a direct per-trigger execution measurement.

WITH recent_render AS (
  SELECT p.run_id,p.collected_at_utc,p.created_at,p.symbol_count
  FROM public.alpha_hunter_snapshots p
  WHERE p.collected_at_utc >= now() - interval '24 hours'
    AND p.payload->'validation_identity'->>'run_source'='RENDER_CRON'
  ORDER BY p.collected_at_utc DESC
  LIMIT 100
), publication AS (
  SELECT r.*,
     (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots s
       WHERE s.run_id=r.run_id) AS child_rows,
     (SELECT max(s.created_at) FROM public.alpha_hunter_symbol_snapshots s
       WHERE s.run_id=r.run_id) AS child_created_at,
     (SELECT count(*) FROM public.alpha_hunter_execution_decision_freezes_v01 f
       WHERE f.decision_run_id=r.run_id) AS retained_freezes,
     (SELECT count(*) FROM public.alpha_hunter_execution_decision_freezes_v01 f
       WHERE f.decision_run_id=r.run_id AND f.strategy_id='S3'
       AND f.direction='LONG') AS retained_s3_long_freezes
  FROM recent_render r
), classified AS (
  SELECT *,
     EXTRACT(EPOCH FROM (child_created_at - created_at))::numeric AS child_delay_seconds,
     CASE
       WHEN child_rows=0 AND symbol_count>0 THEN 'PARENT_ONLY_INCOMPLETE'
       WHEN child_rows<>symbol_count THEN 'CHILD_CARDINALITY_REVIEW'
       WHEN retained_s3_long_freezes>0 THEN 'COMPLETE_WITH_S3_LONG_FREEZE'
       WHEN retained_freezes>0 THEN 'COMPLETE_WITH_OTHER_FREEZE'
       ELSE 'COMPLETE_WITHOUT_RETAINED_FREEZE'
     END AS cohort
  FROM publication
)
SELECT cohort, count(*) AS scans,
       count(*) FILTER(WHERE child_delay_seconds>15) AS delayed_over_15_seconds,
       round(avg(child_delay_seconds),2) AS mean_child_delay_seconds,
       round(min(child_delay_seconds),2) AS min_child_delay_seconds,
       round(max(child_delay_seconds),2) AS max_child_delay_seconds
FROM classified
GROUP BY cohort ORDER BY cohort;

-- CUMULATIVE index statistics; may include many unrelated queries since reset.
-- Dividing index tuples read by index scans does NOT isolate percentile calls.
SELECT indexrelname,idx_scan,idx_tup_read,idx_tup_fetch,
       round(idx_tup_read::numeric/nullif(idx_scan,0),0) AS mean_tuples_per_index_scan,
       pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE relname='alpha_hunter_strategy_forward_outcomes_v01'
ORDER BY idx_scan DESC;

-- Verify only metadata and hashes, without copying privileged function source.
SELECT n.nspname||'.'||p.proname AS function_name,
       md5(pg_get_functiondef(p.oid)) AS function_fingerprint,
       p.prosecdef AS is_security_definer,
       (pg_get_functiondef(p.oid) ILIKE '%percentile_cont%') AS has_percentile_call,
       (pg_get_functiondef(p.oid) ILIKE '%alpha_hunter_strategy_forward_outcomes_v01%') AS reads_forward_outcomes
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='private' AND p.proname='alpha_hunter_capture_payoff_geometry_health_v01';

-- Role timeout exposed to Data API requests; a SQL-editor timeout is not the
-- effective service_role PostgREST timeout.
SELECT rolname,rolconfig
FROM pg_roles WHERE rolname IN ('service_role','authenticator')
ORDER BY rolname;
