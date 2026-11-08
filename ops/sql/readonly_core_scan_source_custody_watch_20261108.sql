-- ALPHA HUNTER P0: SOURCE-AWARE READ-ONLY CORE PERSISTENCE WATCH
-- Validated against production on 2026-11-08. NO writes, scanner calls, or orders.
-- Parent publication can precede child publication during PostgREST retries.
-- STALE is an alert condition, not a claim that later recovery is impossible.
-- Child evidence cardinality can vary when source data has errors/missing prices;
-- row counts alone do not certify science or downstream paper lifecycle evidence.
WITH recent AS (
  SELECT run_id, collected_at_utc, created_at, symbol_count, error_count,
         coalesce(payload->'validation_identity'->>'run_source','UNKNOWN') AS run_source,
         coalesce(payload->'validation_identity'->>'runtime_role','UNKNOWN') AS runtime_role,
         left(coalesce(payload->'validation_identity'->>'git_commit','UNKNOWN'),12) AS writer_commit
  FROM public.alpha_hunter_snapshots
  ORDER BY collected_at_utc DESC
  LIMIT 24
), counts AS (
  SELECT r.*,
    (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots s WHERE s.run_id=r.run_id) AS symbol_rows,
    (SELECT count(*) FROM public.alpha_hunter_signals s WHERE s.run_id=r.run_id) AS signal_rows,
    (SELECT count(*) FROM public.alpha_hunter_signal_features f WHERE f.run_id=r.run_id) AS feature_rows,
    (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 o WHERE o.run_id=r.run_id) AS readiness_rows
  FROM recent r
)
SELECT collected_at_utc, run_id, run_source, runtime_role, writer_commit,
       symbol_count, error_count, symbol_rows, signal_rows, feature_rows, readiness_rows,
  CASE
    WHEN symbol_count>0 AND symbol_rows=0 AND now()-created_at <= interval '3 minutes'
      THEN 'PARENT_ONLY_PUBLISHING'
    WHEN symbol_count>0 AND symbol_rows=0
      THEN 'PARENT_ONLY_STALE_ESCALATE'
    WHEN symbol_rows<>symbol_count
      THEN 'SYMBOL_COUNT_MISMATCH'
    WHEN signal_rows>symbol_rows OR feature_rows>symbol_rows OR readiness_rows>symbol_rows
      OR signal_rows<>feature_rows
      THEN 'STAGE_COUNT_ANOMALY'
    WHEN symbol_rows=signal_rows AND symbol_rows=feature_rows
      AND symbol_rows=readiness_rows AND error_count=0
      THEN 'FIVE_FAMILY_ROW_COUNTS_MATCH_NOT_FULL_CERTIFICATION'
    ELSE 'SOURCE_AWARE_STAGE_REVIEW'
  END AS persistence_watch_status
FROM counts
ORDER BY collected_at_utc DESC;
