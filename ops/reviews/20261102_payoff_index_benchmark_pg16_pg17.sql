-- Synthetic, isolated, reproducible PostgreSQL 16/17 index benchmark.
-- No production data, no real credentials, no server connection.
\set ON_ERROR_STOP on
\timing on

CREATE TABLE alpha_hunter_strategy_forward_outcomes_v01 (
  episode_id text NOT NULL,
  horizon_hours integer NOT NULL,
  strategy_id text NOT NULL,
  direction text NOT NULL,
  entry_trigger_status text NOT NULL,
  path_measurement_quality text NOT NULL,
  ordering_ambiguous boolean NOT NULL,
  evaluated_at_utc timestamptz NOT NULL,
  max_adverse_excursion_pct double precision,
  max_favorable_excursion_pct double precision,
  PRIMARY KEY (episode_id,horizon_hours)
);
CREATE INDEX idx_ah_strategy_forward_outcome_strategy_v01
 ON alpha_hunter_strategy_forward_outcomes_v01(strategy_id,horizon_hours,evaluated_at_utc);

-- Synthetic dataset: 160,000 historical 24h outcomes. Under 2% are
-- eligible for the nested percentile aggregation; other rows are excluded.
INSERT INTO alpha_hunter_strategy_forward_outcomes_v01
SELECT
  'episode-' || g,
  24,
  CASE WHEN g%3=0 THEN 'S6' WHEN g%3=1 THEN 'S2' ELSE 'S4' END,
  CASE WHEN g%2=0 THEN 'SHORT' ELSE 'LONG' END,
  CASE WHEN g%89=0 THEN 'TRIGGERED_EXECUTE_NOW' ELSE 'NOT_TRIGGERED' END,
  CASE WHEN g%4=0 THEN 'COMPLETE_ENOUGH' ELSE 'INCOMPLETE' END,
  (g%7=0),
  timestamptz '2026-10-01 00:00:00+00' + (g || ' seconds')::interval,
  CASE WHEN g%101=0 THEN NULL ELSE (g%3000)::double precision/1000 END,
  CASE WHEN g%103=0 THEN NULL ELSE (g%7000)::double precision/1000 END
FROM generate_series(1,160000) AS g;
VACUUM ANALYZE alpha_hunter_strategy_forward_outcomes_v01;

CREATE TEMP TABLE baseline AS
SELECT count(*)::integer AS n,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct) AS p50_mae,
 percentile_cont(0.75) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct) AS p75_mae,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct) AS p50_mfe,
 percentile_cont(0.90) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct) AS p90_mfe
FROM alpha_hunter_strategy_forward_outcomes_v01 o
WHERE o.horizon_hours=24 AND o.strategy_id='S6' AND o.direction='SHORT'
 AND o.entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
 AND o.path_measurement_quality='COMPLETE_ENOUGH' AND o.ordering_ambiguous=false
 AND o.evaluated_at_utc <= timestamptz '2026-11-02 08:23:00+00'
 AND o.max_adverse_excursion_pct IS NOT NULL
 AND o.max_favorable_excursion_pct IS NOT NULL;
\echo === BASELINE PLAN, INDEX BEFORE ===
EXPLAIN (ANALYZE,BUFFERS)
SELECT count(*)::integer,percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct),
 percentile_cont(0.75) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct),
 percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct),
 percentile_cont(0.90) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct)
FROM alpha_hunter_strategy_forward_outcomes_v01 o
WHERE o.horizon_hours=24 AND o.strategy_id='S6' AND o.direction='SHORT'
 AND o.entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
 AND o.path_measurement_quality='COMPLETE_ENOUGH' AND o.ordering_ambiguous=false
 AND o.evaluated_at_utc <= timestamptz '2026-11-02 08:23:00+00'
 AND o.max_adverse_excursion_pct IS NOT NULL
 AND o.max_favorable_excursion_pct IS NOT NULL;

-- Candidate index: reproduce the exact SQL in the separate DBA review file.
CREATE INDEX CONCURRENTLY idx_ah_payoff_health_24h_strategy_dir_eval_v01
ON alpha_hunter_strategy_forward_outcomes_v01
 (strategy_id,direction,evaluated_at_utc)
INCLUDE (max_adverse_excursion_pct,max_favorable_excursion_pct)
WHERE horizon_hours=24
 AND entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
 AND path_measurement_quality='COMPLETE_ENOUGH'
 AND ordering_ambiguous=false
 AND max_adverse_excursion_pct IS NOT NULL
 AND max_favorable_excursion_pct IS NOT NULL;
ANALYZE alpha_hunter_strategy_forward_outcomes_v01;

CREATE TEMP TABLE optimized AS
SELECT count(*)::integer AS n,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct) AS p50_mae,
 percentile_cont(0.75) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct) AS p75_mae,
 percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct) AS p50_mfe,
 percentile_cont(0.90) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct) AS p90_mfe
FROM alpha_hunter_strategy_forward_outcomes_v01 o
WHERE o.horizon_hours=24 AND o.strategy_id='S6' AND o.direction='SHORT'
 AND o.entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
 AND o.path_measurement_quality='COMPLETE_ENOUGH' AND o.ordering_ambiguous=false
 AND o.evaluated_at_utc <= timestamptz '2026-11-02 08:23:00+00'
 AND o.max_adverse_excursion_pct IS NOT NULL
 AND o.max_favorable_excursion_pct IS NOT NULL;
\echo === OPTIMIZED PLAN, INDEX AFTER ===
EXPLAIN (ANALYZE,BUFFERS)
SELECT count(*)::integer,percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct),
 percentile_cont(0.75) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct),
 percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct),
 percentile_cont(0.90) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct)
FROM alpha_hunter_strategy_forward_outcomes_v01 o
WHERE o.horizon_hours=24 AND o.strategy_id='S6' AND o.direction='SHORT'
 AND o.entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
 AND o.path_measurement_quality='COMPLETE_ENOUGH' AND o.ordering_ambiguous=false
 AND o.evaluated_at_utc <= timestamptz '2026-11-02 08:23:00+00'
 AND o.max_adverse_excursion_pct IS NOT NULL
 AND o.max_favorable_excursion_pct IS NOT NULL;

DO $$
BEGIN
 IF (SELECT row_to_json(b)::text FROM baseline b) IS DISTINCT FROM
    (SELECT row_to_json(o)::text FROM optimized o) THEN
   RAISE EXCEPTION 'FAIL: partial index changed payoff statistics';
 END IF;
 IF (SELECT n FROM baseline) = 0 THEN
   RAISE EXCEPTION 'FAIL: no eligible test rows';
 END IF;
 RAISE NOTICE 'PASS: 5 aggregate results unchanged; eligible rows=%', (SELECT n FROM baseline);
END $$;
\echo === ROLLBACK ===
DROP INDEX CONCURRENTLY idx_ah_payoff_health_24h_strategy_dir_eval_v01;
SELECT count(*) AS remaining_candidate_indexes FROM pg_indexes
 WHERE tablename='alpha_hunter_strategy_forward_outcomes_v01'
 AND indexname='idx_ah_payoff_health_24h_strategy_dir_eval_v01';
