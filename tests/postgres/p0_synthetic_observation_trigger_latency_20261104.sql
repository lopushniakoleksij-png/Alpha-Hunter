-- Disposable synthetic PG16/17 ONLY. Not a production migration or trigger replacement.
\set ON_ERROR_STOP on
DO $$ BEGIN
 IF current_database() <> 'isolated_research' THEN
   RAISE EXCEPTION 'Refusing non-disposable database: %',current_database();
 END IF;
END $$;
CREATE TEMP TABLE symbols (run_id text NOT NULL, symbol text NOT NULL, payload jsonb NOT NULL, PRIMARY KEY(run_id,symbol));
CREATE TEMP TABLE observations (run_id text NOT NULL, symbol text NOT NULL, strategy text NOT NULL, PRIMARY KEY(run_id,symbol,strategy));
CREATE TEMP TABLE timings (mode text NOT NULL, iteration int NOT NULL, elapsed_ms double precision NOT NULL);
CREATE FUNCTION pg_temp.capture_observations() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO observations(run_id,symbol,strategy)
 SELECT NEW.run_id,NEW.symbol,'strategy-'||s FROM generate_series(1,10) s
 ON CONFLICT (run_id,symbol,strategy) DO NOTHING;
 RETURN NEW;
END $$;
-- 5 paired batches; distinct run ids ensure no collision, each 61-symbol upsert.
DO $$
DECLARE mode text; iteration int; t timestamptz; n int;
BEGIN
 FOR iteration IN 1..5 LOOP
  FOREACH mode IN ARRAY ARRAY['baseline','capture'] LOOP
   IF mode='capture' THEN
     EXECUTE 'CREATE TRIGGER capture AFTER INSERT OR UPDATE OF payload ON symbols FOR EACH ROW EXECUTE FUNCTION pg_temp.capture_observations()';
   END IF;
   t:=clock_timestamp();
   INSERT INTO symbols(run_id,symbol,payload)
     SELECT mode||'-'||iteration, 'SYM'||g, jsonb_build_object('symbol','SYM'||g,'strategy_count',10)
     FROM generate_series(1,61) g
   ON CONFLICT(run_id,symbol) DO UPDATE SET payload=EXCLUDED.payload;
   INSERT INTO timings VALUES(mode,iteration,extract(epoch from clock_timestamp()-t)*1000);
   IF mode='capture' THEN EXECUTE 'DROP TRIGGER capture ON symbols'; END IF;
   SELECT count(*) INTO n FROM observations WHERE run_id=mode||'-'||iteration;
   IF n <> (CASE WHEN mode='capture' THEN 610 ELSE 0 END) THEN
     RAISE EXCEPTION 'Observation count mismatch: mode %, got %',mode,n;
   END IF;
  END LOOP;
 END LOOP;
END $$;
-- Exercise idempotent same-run UPDATE: trigger may fire, but no duplicate observations.
CREATE TRIGGER capture AFTER INSERT OR UPDATE OF payload ON symbols
 FOR EACH ROW EXECUTE FUNCTION pg_temp.capture_observations();
UPDATE symbols SET payload=payload||'{"retry":true}'::jsonb WHERE run_id='capture-1';
DO $$ BEGIN
 IF (SELECT count(*) FROM observations WHERE run_id='capture-1') <> 610 THEN
  RAISE EXCEPTION 'Retry generated duplicate observations';
 END IF;
 IF (SELECT count(*) FROM observations) <> 3050 THEN
  RAISE EXCEPTION 'Expected 3050 synthetic observations';
 END IF;
END $$;
SELECT mode,count(*) AS batches,
 round(percentile_cont(0.5) WITHIN GROUP (ORDER BY elapsed_ms)::numeric,3) AS p50_ms,
 round(percentile_cont(0.95) WITHIN GROUP (ORDER BY elapsed_ms)::numeric,3) AS p95_ms,
 round(percentile_cont(0.99) WITHIN GROUP (ORDER BY elapsed_ms)::numeric,3) AS p99_ms
 FROM timings GROUP BY mode ORDER BY mode;
-- Synthetic measurement only: not actual production trigger, PostgREST, RLS or concurrency.

-- Failure-injection contract: an AFTER trigger exception must atomically roll back
-- the parent write and its child observations. Entirely disposable local SQL.
DROP TRIGGER capture ON symbols;
CREATE FUNCTION pg_temp.capture_then_fail() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO observations(run_id,symbol,strategy)
 VALUES(NEW.run_id,NEW.symbol,'injected-before-failure')
 ON CONFLICT DO NOTHING;
 RAISE EXCEPTION 'synthetic observation persistence failure' USING ERRCODE='P0001';
END $$;
CREATE TRIGGER capture_fail AFTER INSERT OR UPDATE OF payload ON symbols
 FOR EACH ROW EXECUTE FUNCTION pg_temp.capture_then_fail();
DO $$
DECLARE caught boolean := false;
BEGIN
 BEGIN
  INSERT INTO symbols(run_id,symbol,payload)
  VALUES('fault-insert','SYM1','{"value":"uncommitted"}'::jsonb);
 EXCEPTION WHEN SQLSTATE 'P0001' THEN
  caught := true;
 END;
 IF NOT caught THEN RAISE EXCEPTION 'Fault-insert trigger did not fail'; END IF;
 IF EXISTS(SELECT 1 FROM symbols WHERE run_id='fault-insert')
    OR EXISTS(SELECT 1 FROM observations WHERE run_id='fault-insert') THEN
  RAISE EXCEPTION 'Fault-insert leaked parent or child records';
 END IF;
END $$;
DROP TRIGGER capture_fail ON symbols;
INSERT INTO symbols(run_id,symbol,payload)
 VALUES('fault-update','SYM1','{"value":"original"}'::jsonb);
CREATE TRIGGER capture_fail AFTER INSERT OR UPDATE OF payload ON symbols
 FOR EACH ROW EXECUTE FUNCTION pg_temp.capture_then_fail();
DO $$
DECLARE caught boolean := false;
BEGIN
 BEGIN
  UPDATE symbols SET payload='{"value":"mutated"}'::jsonb
  WHERE run_id='fault-update' AND symbol='SYM1';
 EXCEPTION WHEN SQLSTATE 'P0001' THEN
  caught := true;
 END;
 IF NOT caught THEN RAISE EXCEPTION 'Fault-update trigger did not fail'; END IF;
 IF (SELECT payload FROM symbols WHERE run_id='fault-update' AND symbol='SYM1')
      IS DISTINCT FROM '{"value":"original"}'::jsonb
    OR EXISTS(SELECT 1 FROM observations WHERE run_id='fault-update') THEN
  RAISE EXCEPTION 'Fault-update leaked mutated parent or child records';
 END IF;
END $$;
DROP TRIGGER capture_fail ON symbols;
-- This checks PostgreSQL statement atomicity, NOT PostgREST timeout/commit ambiguity.
