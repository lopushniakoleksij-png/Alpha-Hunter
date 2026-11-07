-- P0 disposable integration fixture: 61-symbol atomic RPC + nested payoff work.
-- NEVER execute against live Supabase, a real scanner or any real exchange.
-- Artificial data and trigger only. This is NOT a full production clone.
DO $p0_guard$
BEGIN
  IF current_database() <> 'isolated_research'
     OR to_regclass('public.p0_test_observations') IS NULL
     OR to_regprocedure('public.ah_p0_research_atomic_canonical_v03(jsonb,jsonb,jsonb,jsonb,jsonb)') IS NULL
  THEN
    RAISE EXCEPTION 'P0 REFUSED: not the expected disposable atomic test database';
  END IF;
END $p0_guard$;

CREATE SCHEMA p0_bench;
CREATE TABLE p0_bench.payoff_outcomes (
  episode_id text PRIMARY KEY,
  strategy_id text NOT NULL,
  horizon_hours integer NOT NULL,
  direction text NOT NULL,
  entry_trigger_status text NOT NULL,
  path_measurement_quality text NOT NULL,
  ordering_ambiguous boolean NOT NULL,
  evaluated_at_utc timestamptz NOT NULL,
  max_adverse_excursion_pct double precision,
  max_favorable_excursion_pct double precision
);
CREATE INDEX p0_payoff_existing_strategy
 ON p0_bench.payoff_outcomes(strategy_id, horizon_hours, evaluated_at_utc);

-- Same deliberately skewed, 160,000-row artificial horizon-24 distribution
-- used by prior standalone candidate benchmark. 126 relevant S6/SHORT rows.
INSERT INTO p0_bench.payoff_outcomes
SELECT
  'episode-' || g,
  CASE WHEN g%3=0 THEN 'S6' WHEN g%3=1 THEN 'S2' ELSE 'S4' END,
  24,
  CASE WHEN g%2=0 THEN 'SHORT' ELSE 'LONG' END,
  CASE WHEN g%89=0 THEN 'TRIGGERED_EXECUTE_NOW' ELSE 'NOT_TRIGGERED' END,
  CASE WHEN g%4=0 THEN 'COMPLETE_ENOUGH' ELSE 'INCOMPLETE' END,
  (g%7=0),
  timestamptz '2026-10-01 00:00:00+00' + (g || ' seconds')::interval,
  CASE WHEN g%101=0 THEN NULL ELSE (g%3000)::double precision/1000 END,
  CASE WHEN g%103=0 THEN NULL ELSE (g%7000)::double precision/1000 END
FROM generate_series(1,160000) AS g;
ANALYZE p0_bench.payoff_outcomes;

CREATE TABLE p0_bench.payoff_receipts (
  run_id text NOT NULL,
  symbol text NOT NULL,
  strategy_id integer NOT NULL,
  eligible integer NOT NULL,
  p50_mae double precision,
  p75_mae double precision,
  p50_mfe double precision,
  p90_mfe double precision,
  PRIMARY KEY(run_id,symbol,strategy_id)
);

-- Disposable, explicit fault switch; only this local test database can enable it.
-- Failure occurs AFTER four earlier nested receipts for TEST000USDT.
CREATE TABLE p0_bench.payoff_failure_switch (run_id text PRIMARY KEY);
INSERT INTO p0_bench.payoff_failure_switch VALUES ('bad-payoff-nested-atomic');

-- Deliberately SECURITY INVOKER. The disposable local PostgREST writer is
-- granted only SELECT on the fake market evidence and INSERT on receipts.
GRANT USAGE ON SCHEMA p0_bench TO ah_p0_local_writer;
GRANT SELECT ON p0_bench.payoff_outcomes, p0_bench.payoff_failure_switch TO ah_p0_local_writer;
GRANT INSERT ON p0_bench.payoff_receipts TO ah_p0_local_writer;

CREATE FUNCTION p0_bench.capture_payoff_observation() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER
SET search_path = pg_catalog, p0_bench
AS $p0_trigger$
DECLARE
  v_n integer;
  v_mae50 double precision;
  v_mae75 double precision;
  v_mfe50 double precision;
  v_mfe90 double precision;
BEGIN
  SELECT count(*)::integer,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct),
         percentile_cont(0.75) WITHIN GROUP (ORDER BY o.max_adverse_excursion_pct),
         percentile_cont(0.5) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct),
         percentile_cont(0.90) WITHIN GROUP (ORDER BY o.max_favorable_excursion_pct)
  INTO v_n,v_mae50,v_mae75,v_mfe50,v_mfe90
  FROM p0_bench.payoff_outcomes o
  WHERE o.horizon_hours = 24
    AND o.strategy_id = 'S6'
    AND o.direction = 'SHORT'
    AND o.entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
    AND o.path_measurement_quality = 'COMPLETE_ENOUGH'
    AND o.ordering_ambiguous = false
    AND o.evaluated_at_utc <= timestamptz '2026-11-02 08:23:00+00'
    AND o.max_adverse_excursion_pct IS NOT NULL
    AND o.max_favorable_excursion_pct IS NOT NULL;

  INSERT INTO p0_bench.payoff_receipts
   (run_id,symbol,strategy_id,eligible,p50_mae,p75_mae,p50_mfe,p90_mfe)
  VALUES
   (NEW.run_id,NEW.symbol,NEW.strategy_id,
    v_n,v_mae50,v_mae75,v_mfe50,v_mfe90);
  IF NEW.symbol = 'TEST000USDT' AND NEW.strategy_id = 5
     AND EXISTS (SELECT 1 FROM p0_bench.payoff_failure_switch
                 WHERE run_id = NEW.run_id)
  THEN
    RAISE EXCEPTION 'synthetic nested payoff trigger cancellation'
      USING ERRCODE = '57014';
  END IF;
  RETURN NEW;
END $p0_trigger$;

CREATE TRIGGER p0_nested_payoff_probe
AFTER INSERT ON public.p0_test_observations
FOR EACH ROW EXECUTE FUNCTION p0_bench.capture_payoff_observation();
