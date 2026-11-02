-- P0/successor independent last-24h monitoring-cycle audit. SELECT ONLY.
-- Immutable parent scan count is NOT equivalent to completed per-symbol/position work.
-- Exit attempts alone do NOT prove all as-of-run positions were monitored.
-- No historical as-of position inventory is available from this query: UNKNOWN, not PASS.
WITH canonical AS (
 SELECT s.run_id,s.collected_at_utc,s.symbol_count,s.error_count,
        s.payload->'validation_identity'->>'scientific_fingerprint_sha256' fingerprint
 FROM public.alpha_hunter_snapshots s
 WHERE s.collected_at_utc >= now()-interval '24 hours'
 AND s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
 AND s.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
), child_counts AS (
 SELECT c.run_id,COUNT(ch.*) child_rows,COUNT(DISTINCT ch.symbol) distinct_child_symbols
 FROM canonical c LEFT JOIN public.alpha_hunter_symbol_snapshots ch
 ON ch.run_id=c.run_id GROUP BY c.run_id
), attempts AS (
 SELECT c.run_id,COUNT(a.*) exit_attempt_rows,COUNT(DISTINCT a.entry_order_id) exit_positions_seen
 FROM canonical c LEFT JOIN public.alpha_hunter_paper_exit_attempts_v04 a
 ON a.source_run_id=c.run_id GROUP BY c.run_id
), evaluated AS (
 SELECT c.*,ch.child_rows,ch.distinct_child_symbols,
 a.exit_attempt_rows,a.exit_positions_seen,
 CASE WHEN c.symbol_count>0 AND ch.child_rows=c.symbol_count
            AND ch.distinct_child_symbols=c.symbol_count THEN TRUE
      ELSE FALSE END child_stage_complete,
 CASE WHEN c.symbol_count IS NULL OR c.symbol_count<=0 THEN 'PARENT_SYMBOL_COUNT_INVALID_OR_EMPTY'
      WHEN ch.child_rows<>c.symbol_count OR ch.distinct_child_symbols<>c.symbol_count
      THEN 'PARENT_PERSISTED_CHILD_STAGE_INCOMPLETE'
      WHEN a.exit_attempt_rows=0 THEN 'CHILD_STAGE_COMPLETE_EXIT_MONITORING_UNATTESTED'
      ELSE 'CHILD_AND_SOME_ATTEMPTS_PRESENT_ASOF_POSITION_INVENTORY_REQUIRED'
 END stage_verdict
 FROM canonical c JOIN child_counts ch USING(run_id) JOIN attempts a USING(run_id)
), completed_intervals AS (
 SELECT e.run_id,e.collected_at_utc,
 LAG(e.collected_at_utc) OVER (ORDER BY e.collected_at_utc,e.run_id) prev_complete_at_utc
 FROM evaluated e WHERE e.child_stage_complete
)
SELECT (SELECT COUNT(*) FROM evaluated) canonical_parent_runs,
 COUNT(*) FILTER(WHERE child_stage_complete) child_complete_runs,
 COUNT(*) FILTER(WHERE NOT child_stage_complete) child_incomplete_runs,
 COUNT(*) FILTER(WHERE stage_verdict='PARENT_PERSISTED_CHILD_STAGE_INCOMPLETE') parent_only_or_truncated_runs,
 COUNT(*) FILTER(WHERE stage_verdict='CHILD_STAGE_COMPLETE_EXIT_MONITORING_UNATTESTED') child_complete_no_exit_attempt_runs,
 COUNT(*) FILTER(WHERE stage_verdict='CHILD_AND_SOME_ATTEMPTS_PRESENT_ASOF_POSITION_INVENTORY_REQUIRED') child_complete_some_exit_attempt_runs,
 MAX(ci.collected_at_utc-ci.prev_complete_at_utc) max_completed_cycle_gap,
 COUNT(*) FILTER(WHERE ci.collected_at_utc-ci.prev_complete_at_utc>interval '35 minutes') completed_cycle_gaps_over_35m,
 'ASOF_POSITION_COVERAGE_UNKNOWN_WITHOUT_IMMUTABLE_INVENTORY'::text paper_monitoring_verdict
FROM evaluated e LEFT JOIN completed_intervals ci ON ci.run_id=e.run_id;
