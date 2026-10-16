-- P0 per-scan detail; SELECT ONLY, no backfill or test reset.
WITH canonical AS (
 SELECT s.run_id,s.collected_at_utc,s.symbol_count,s.error_count
 FROM public.alpha_hunter_snapshots s
 WHERE s.collected_at_utc>=now()-interval '24 hours'
 AND s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
 AND s.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
), per_run AS (
 SELECT c.run_id,c.collected_at_utc,c.symbol_count,c.error_count,
 (SELECT COUNT(*) FROM public.alpha_hunter_symbol_snapshots ch WHERE ch.run_id=c.run_id) child_rows,
 (SELECT COUNT(*) FROM public.alpha_hunter_paper_exit_attempts_v04 a WHERE a.source_run_id=c.run_id) exit_attempt_rows,
 (SELECT COUNT(*) FROM public.alpha_hunter_paper_reconciliation_attempts_v03 a WHERE a.source_run_id=c.run_id) entry_attempt_rows
 FROM canonical c
)
SELECT *, 'INCOMPLETE_MONITORING_CYCLE'::text verdict FROM per_run
WHERE child_rows<>symbol_count OR symbol_count IS NULL OR symbol_count<=0
ORDER BY collected_at_utc,run_id;
