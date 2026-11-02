-- ALPHA HUNTER / 2026-11-02 / ISOLATED DBA REVIEW CANDIDATE ONLY.
-- NO PRODUCTION EXECUTION; requires PG16/17 benchmarks and independent signoff.
-- 08:23 UTC RENDER_CRON snapshot: 61 expected symbols, 0 persisted.
-- PostgREST 57014 symbol upsert trigger reaches payoff geometry percentile query.
-- Baseline EXPLAIN indexes (strategy_id,horizon_hours,evaluated_at_utc)
-- then filters direction, statuses, data quality, ambiguity and non-null values.
-- 1127 / 113138 24h outcomes met the whole quality predicate.
-- This is not a validated performance repair. DB load may have other bottlenecks.
-- IMPORTANT: CONCURRENTLY must execute outside a transaction. Do not put this
-- file in an auto-run migration path; separate authorized deployment only.
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_ah_payoff_health_24h_strategy_dir_eval_v01
ON public.alpha_hunter_strategy_forward_outcomes_v01
  (strategy_id, direction, evaluated_at_utc)
INCLUDE (max_adverse_excursion_pct, max_favorable_excursion_pct)
WHERE horizon_hours = 24
  AND entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW', 'TRIGGERED_LIMIT')
  AND path_measurement_quality = 'COMPLETE_ENOUGH'
  AND ordering_ambiguous = false
  AND max_adverse_excursion_pct IS NOT NULL
  AND max_favorable_excursion_pct IS NOT NULL;
