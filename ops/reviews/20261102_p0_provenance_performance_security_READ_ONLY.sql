-- P0 independent DBA/security review evidence — SELECT and EXPLAIN ONLY.
-- 2 Nov 2026. Never run DDL, ALTER ROLE, update historic positions, etc.
-- All queries require independently approved READ privileges.
--
-- A. Recent canonical parent/child/receipt consistency: failures remain visible.
SELECT s.run_id,s.collected_at_utc,s.symbol_count AS advertised,
  (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots c WHERE c.run_id=s.run_id) persisted_children,
  (SELECT count(*) FROM public.alpha_hunter_paper_exit_attempts_v04 a WHERE a.source_run_id=s.run_id) exit_receipts,
  s.payload->>'_canonical_publication_state' AS publication_state
FROM public.alpha_hunter_snapshots s
WHERE s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
ORDER BY s.collected_at_utc DESC
LIMIT 12;

-- B. Previous-run source and publication marker coverage. LEGACY UNMARKED != VERIFIED.
SELECT count(*) AS attempts,
 count(*) FILTER(WHERE p.run_id IS NULL) AS absent_parents,
 count(*) FILTER(WHERE p.payload->>'_canonical_publication_state'='VERIFIED') AS verified_parents,
 count(*) FILTER(WHERE p.payload->>'_canonical_publication_state' IS NULL) AS unmarked_parents,
 count(*) FILTER(WHERE p.payload->'validation_identity'->>'run_source'='RENDER_CRON') AS matching_run_source
FROM public.alpha_hunter_paper_exit_attempts_v04 a
LEFT JOIN public.alpha_hunter_snapshots p ON p.run_id=a.source_run_id
WHERE a.observed_at_utc >= timestamptz '2026-11-01 00:00:00+00';

-- C. First-entry paper baseline: no inference from synthetic protective IDs.
SELECT entry_order_id,symbol,entry_completed_source_run_id,entry_completed_at_utc,
 protection_count,previous_exit_observed_at_utc,
 horizon_integrity_failed,unresolved_protective_evidence
FROM public.alpha_hunter_paper_protection_horizon_open_v09
ORDER BY entry_completed_at_utc LIMIT 100;

-- D. RLS metadata: explicit policy review, not effective-role simulation.
SELECT c.relname,c.relrowsecurity AS rls_enabled,
 has_table_privilege('anon',c.oid,'SELECT') AS anon_has_sql_grant_select,
 has_table_privilege('authenticated',c.oid,'INSERT') AS auth_has_sql_grant_insert,
 COUNT(p.policyname) AS policy_count
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_policies p ON p.schemaname=n.nspname AND p.tablename=c.relname
WHERE n.nspname='public'
 AND c.relname IN (
   'alpha_hunter_snapshots',
   'alpha_hunter_symbol_snapshots',
   'alpha_hunter_paper_exit_attempts_v04'
 )
GROUP BY c.relname,c.oid
ORDER BY c.relname;

-- E. Storage sizes and estimated tuple pressure; values are approximate.
SELECT st.relname,pg_size_pretty(pg_total_relation_size(st.relid)) total_bytes,
 st.n_live_tup estimated_live,st.n_dead_tup estimated_dead
FROM pg_stat_user_tables st
WHERE st.schemaname='public'
 AND st.relname IN (
   'alpha_hunter_symbol_snapshots',
   'alpha_hunter_strategy_observations_v01',
   'alpha_hunter_strategy_forward_outcomes_v01',
   'alpha_hunter_paper_exit_attempts_v04'
 )
ORDER BY st.relname;

-- F. Historical child-upsert accumulated timing; no active workload triggered.
SELECT queryid,calls,
 round(mean_exec_time::numeric,1) mean_ms,
 round(max_exec_time::numeric,1) max_ms,
 round(total_exec_time::numeric,1) cumulative_ms
FROM pg_stat_statements
WHERE query ILIKE '%alpha_hunter_symbol_snapshots%'
  AND query ILIKE '%INSERT%'
ORDER BY total_exec_time DESC LIMIT 5;

-- G. Cost-only explain of previous receipt time-window lookup. NEVER ANALYZE production write.
EXPLAIN (COSTS)
SELECT a.entry_order_id,a.source_run_id,a.observed_at_utc
FROM public.alpha_hunter_paper_exit_attempts_v04 a
WHERE a.source_run_id<>'REVIEW_ONLY_SYNTHETIC'
  AND a.observed_at_utc >= timestamptz '2026-11-02 08:00:00+00'
  AND a.observed_at_utc < timestamptz '2026-11-02 10:00:00+00'
ORDER BY a.observed_at_utc DESC LIMIT 2000;
