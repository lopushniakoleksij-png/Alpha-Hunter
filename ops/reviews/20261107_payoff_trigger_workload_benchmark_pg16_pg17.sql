-- P0 isolated trigger-like payoff benchmark: synthetic data ONLY.
-- Must run ONLY after the 20261102 standalone synthetic benchmark has created
-- its 160,000 explicitly fake episode-N rows and dropped its candidate index.
-- No real trigger definitions, RLS/roles, exchange or production data used.
-- The workload has 61 synthetic symbols * 10 observations = 610 invocations.
\set ON_ERROR_STOP on
\timing on

DO $guard$
BEGIN
 IF current_database() <> 'postgres'
    OR current_user <> 'postgres'
    OR NOT EXISTS (
      SELECT 1 FROM public.alpha_hunter_strategy_forward_outcomes_v01
      WHERE episode_id='episode-1' AND strategy_id='S2'
      AND horizon_hours=24
    )
    OR (SELECT count(*) FROM public.alpha_hunter_strategy_forward_outcomes_v01)
       <> 160000
    OR EXISTS (
      SELECT 1 FROM pg_indexes
      WHERE schemaname='public'
        AND indexname='idx_ah_payoff_health_24h_strategy_dir_eval_v01'
    )
 THEN
   RAISE EXCEPTION 'REFUSE: requires exact disposable synthetic seed and no candidate index';
 END IF;
END $guard$;

CREATE TABLE public.p0_payoff_probe_events (
 run_id text NOT NULL,
 symbol_no integer NOT NULL,
 strategy_no integer NOT NULL
);
CREATE TABLE public.p0_payoff_probe_metrics (
 run_id text NOT NULL,
 eligible integer NOT NULL,
 p50_mae double precision,
 p75_mae double precision,
 p50_mfe double precision,
 p90_mfe double precision
);
CREATE TABLE public.p0_payoff_probe_samples (
 phase text NOT NULL,
 trial integer NOT NULL,
 duration_ms double precision NOT NULL,
 event_count integer NOT NULL
);

CREATE FUNCTION public.p0_payoff_probe_trigger() RETURNS trigger
LANGUAGE plpgsql AS $f$
DECLARE
  v_eligible integer;
  v_p50_mae double precision;
  v_p75_mae double precision;
  v_p50_mfe double precision;
  v_p90_mfe double precision;
BEGIN
  -- This mimics the REPEATED percentile lookup seen inside the real
  -- downstream trigger chain. It does not clone the production graph.
  SELECT count(*)::integer,
    percentile_cont(0.5) WITHIN GROUP(ORDER BY o.max_adverse_excursion_pct),
    percentile_cont(0.75) WITHIN GROUP(ORDER BY o.max_adverse_excursion_pct),
    percentile_cont(0.5) WITHIN GROUP(ORDER BY o.max_favorable_excursion_pct),
    percentile_cont(0.90) WITHIN GROUP(ORDER BY o.max_favorable_excursion_pct)
  INTO v_eligible,v_p50_mae,v_p75_mae,v_p50_mfe,v_p90_mfe
  FROM public.alpha_hunter_strategy_forward_outcomes_v01 o
  WHERE o.horizon_hours=24 AND o.strategy_id='S6' AND o.direction='SHORT'
    AND o.entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
    AND o.path_measurement_quality='COMPLETE_ENOUGH'
    AND o.ordering_ambiguous=false
    AND o.evaluated_at_utc <= TIMESTAMPTZ '2026-11-02 08:23:00+00'
    AND o.max_adverse_excursion_pct IS NOT NULL
    AND o.max_favorable_excursion_pct IS NOT NULL;

  INSERT INTO public.p0_payoff_probe_metrics
   (run_id,eligible,p50_mae,p75_mae,p50_mfe,p90_mfe)
  VALUES
   (NEW.run_id,v_eligible,v_p50_mae,v_p75_mae,v_p50_mfe,v_p90_mfe);
  RETURN NEW;
END $f$;
CREATE TRIGGER p0_payoff_probe_hook
AFTER INSERT ON public.p0_payoff_probe_events FOR EACH ROW
EXECUTE FUNCTION public.p0_payoff_probe_trigger();

CREATE FUNCTION public.p0_payoff_run_scan_batches(
 p_phase text,p_n integer
) RETURNS void
LANGUAGE plpgsql AS $f$
DECLARE
 v_trial integer;
 v_run text;
 v_started timestamptz;
 v_ms double precision;
 v_count integer;
BEGIN
 IF p_phase NOT IN ('baseline','indexed','baseline_warmup','indexed_warmup')
    OR p_n NOT BETWEEN 1 AND 8 THEN
   RAISE EXCEPTION 'invalid synthetic workload sample request';
 END IF;
 FOR v_trial IN 1..p_n LOOP
   v_run := p_phase || '-' || lpad(v_trial::text,2,'0');
   v_started := clock_timestamp();
   INSERT INTO public.p0_payoff_probe_events(run_id,symbol_no,strategy_no)
   SELECT v_run,s,st FROM generate_series(1,61) s
       CROSS JOIN generate_series(1,10) st;
   v_ms := extract(epoch FROM (clock_timestamp()-v_started))*1000;
   SELECT count(*) INTO v_count FROM public.p0_payoff_probe_metrics
      WHERE run_id=v_run;
   IF v_count <> 610 THEN
     RAISE EXCEPTION 'scan trigger observation gap: % expected 610, got %',v_run,v_count;
   END IF;
   INSERT INTO public.p0_payoff_probe_samples(phase,trial,duration_ms,event_count)
    VALUES (p_phase,v_trial,v_ms,v_count);
 END LOOP;
END $f$;

\echo === WARM BASELINE (1 synthetic 61-symbol scan / 610 trigger invocations) ===
SELECT public.p0_payoff_run_scan_batches('baseline_warmup',1);
\echo === MEASURE BASELINE (8 scans, 4,880 trigger invocations) ===
SELECT public.p0_payoff_run_scan_batches('baseline',8);

\echo === CREATE CANDIDATE INDEX ON DISPOSABLE DATA ONLY ===
CREATE INDEX CONCURRENTLY idx_ah_payoff_health_24h_strategy_dir_eval_v01
ON public.alpha_hunter_strategy_forward_outcomes_v01
 (strategy_id,direction,evaluated_at_utc)
INCLUDE (max_adverse_excursion_pct,max_favorable_excursion_pct)
WHERE horizon_hours=24
 AND entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
 AND path_measurement_quality='COMPLETE_ENOUGH'
 AND ordering_ambiguous=false
 AND max_adverse_excursion_pct IS NOT NULL
 AND max_favorable_excursion_pct IS NOT NULL;
ANALYZE public.alpha_hunter_strategy_forward_outcomes_v01;
SELECT pg_size_pretty(pg_relation_size('public.idx_ah_payoff_health_24h_strategy_dir_eval_v01'::regclass))
 AS synthetic_candidate_index_size;

\echo === WARM INDEXED (1 synthetic 61-symbol scan / 610 trigger invocations) ===
SELECT public.p0_payoff_run_scan_batches('indexed_warmup',1);
\echo === MEASURE INDEXED (8 scans, 4,880 trigger invocations) ===
SELECT public.p0_payoff_run_scan_batches('indexed',8);

DO $verify$
DECLARE
 a record;
 b record;
BEGIN
 IF (SELECT count(*) FROM public.p0_payoff_probe_samples WHERE phase='baseline')<>8
 OR (SELECT count(*) FROM public.p0_payoff_probe_samples WHERE phase='indexed')<>8
 OR (SELECT sum(event_count) FROM public.p0_payoff_probe_samples
      WHERE phase IN ('baseline','indexed'))<>9760
 THEN RAISE EXCEPTION 'incomplete repeated synthetic scan samples'; END IF;
 SELECT DISTINCT eligible,p50_mae,p75_mae,p50_mfe,p90_mfe INTO a
 FROM public.p0_payoff_probe_metrics WHERE run_id='baseline-01';
 SELECT DISTINCT eligible,p50_mae,p75_mae,p50_mfe,p90_mfe INTO b
 FROM public.p0_payoff_probe_metrics WHERE run_id='indexed-01';
 IF a IS DISTINCT FROM b OR a.eligible <> 126 THEN
   RAISE EXCEPTION 'payoff values changed after synthetic candidate index';
 END IF;
 IF EXISTS (
   SELECT 1 FROM public.p0_payoff_probe_metrics
   WHERE eligible<>a.eligible OR p50_mae IS DISTINCT FROM a.p50_mae
      OR p75_mae IS DISTINCT FROM a.p75_mae
      OR p50_mfe IS DISTINCT FROM a.p50_mfe
      OR p90_mfe IS DISTINCT FROM a.p90_mfe
 ) THEN
   RAISE EXCEPTION 'nested observation aggregate evidence inconsistent';
 END IF;
 RAISE NOTICE 'PASS exact synthetic parity and 9,760 trigger invocations across measured scans';
END $verify$;

\echo === TRIGGER-STYLE SCAN LATENCY DISTRIBUTIONS: isolated, not production ===
SELECT phase,count(*) AS scan_samples,
 round((percentile_cont(0.5) WITHIN GROUP(ORDER BY duration_ms))::numeric,3) AS p50_ms,
 round((percentile_cont(0.95) WITHIN GROUP(ORDER BY duration_ms))::numeric,3) AS p95_ms,
 round((percentile_cont(0.99) WITHIN GROUP(ORDER BY duration_ms))::numeric,3) AS p99_ms,
 round(max(duration_ms)::numeric,3) AS max_ms,
 sum(event_count) AS trigger_invocations
FROM public.p0_payoff_probe_samples
WHERE phase IN ('baseline','indexed')
GROUP BY phase ORDER BY phase;

\echo === PROVE CANDIDATE INDEX ROLLBACK ON DISPOSABLE DATABASE ===
DROP INDEX CONCURRENTLY public.idx_ah_payoff_health_24h_strategy_dir_eval_v01;
DO $verify$
BEGIN
 IF EXISTS(SELECT 1 FROM pg_indexes
  WHERE schemaname='public'
   AND indexname='idx_ah_payoff_health_24h_strategy_dir_eval_v01')
 THEN RAISE EXCEPTION 'synthetic index rollback not completed'; END IF;
 RAISE NOTICE 'PASS index removed; NO production database access';
END $verify$;
