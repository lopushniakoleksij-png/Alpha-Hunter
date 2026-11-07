-- Alpha Hunter / isolated DBA candidate — NOT APPROVED FOR PRODUCTION.
-- Evidence: 2026-11-07 05:22 UTC symbol-snapshot POST timed out repeatedly.
-- PostgreSQL error context: private.alpha_hunter_capture_payoff_geometry_health_v01()
-- performed four percentile aggregates against alpha_hunter_strategy_forward_outcomes_v01.
-- 2026-11-07 read-only EXPLAIN selected a large scan through
-- idx_ah_strategy_outcome_24h_time_episode_v02 and filtered strategy/direction afterwards.
--
-- Hypothesis: a predicate-matched index can reduce the nested per-symbol trigger cost.
-- BEFORE ANY DEPLOYMENT: reproduce full trigger graph on an isolated Postgres copy,
-- compare EXPLAIN (ANALYZE, BUFFERS), inspect index build/storage, verify ALL
-- trigger side effects, and obtain independent DBA and security sign-off.
-- CONCURRENTLY must run outside a transaction.
-- This branch must remain isolated. No database has been modified by this file.

CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_ah_payoff_geometry_percentiles_candidate_v01
ON public.alpha_hunter_strategy_forward_outcomes_v01
  (strategy_id, direction, evaluated_at_utc)
INCLUDE (max_adverse_excursion_pct, max_favorable_excursion_pct)
WHERE horizon_hours = 24
  AND entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW', 'TRIGGERED_LIMIT')
  AND path_measurement_quality = 'COMPLETE_ENOUGH'
  AND ordering_ambiguous = false
  AND max_adverse_excursion_pct IS NOT NULL
  AND max_favorable_excursion_pct IS NOT NULL;
