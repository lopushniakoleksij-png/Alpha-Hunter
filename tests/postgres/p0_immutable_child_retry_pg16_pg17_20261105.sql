-- Alpha Hunter P0: disposable PostgreSQL 16/17 retry semantics for immutable
-- canonical child batches. Synthetic data ONLY; never a production migration.
\set ON_ERROR_STOP on
DO $$ BEGIN
  IF current_database() <> 'isolated_research' THEN
    RAISE EXCEPTION 'Refusing to run outside isolated_research';
  END IF;
END $$;

CREATE TEMP TABLE parent_snapshots (
  run_id text PRIMARY KEY,
  declared_count integer NOT NULL,
  state text NOT NULL
);
CREATE TEMP TABLE symbol_snapshots (
  run_id text NOT NULL REFERENCES parent_snapshots(run_id),
  symbol text NOT NULL,
  collected_at_utc timestamptz NOT NULL,
  state text NOT NULL,
  trade_permission boolean NOT NULL DEFAULT false,
  payload jsonb NOT NULL,
  PRIMARY KEY(run_id,symbol)
);
CREATE TEMP TABLE synthetic_strategy_observations (
  run_id text NOT NULL,
  symbol text NOT NULL,
  strategy_id integer NOT NULL,
  PRIMARY KEY(run_id,symbol,strategy_id)
);
CREATE TEMP TABLE trigger_fires (
  run_id text NOT NULL,
  symbol text NOT NULL,
  PRIMARY KEY(run_id,symbol)
);
CREATE TEMP TABLE batch_timings (batch_number integer NOT NULL, elapsed_ms double precision NOT NULL);

CREATE FUNCTION pg_temp.capture_strategy_observations() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.run_id = 'failing-run' AND NEW.symbol = 'SYM011' THEN
    RAISE EXCEPTION 'synthetic injected child trigger fault';
  END IF;
  INSERT INTO trigger_fires VALUES (NEW.run_id,NEW.symbol)
  ON CONFLICT(run_id,symbol) DO NOTHING;
  INSERT INTO synthetic_strategy_observations(run_id,symbol,strategy_id)
    SELECT NEW.run_id,NEW.symbol,s FROM generate_series(1,10) AS s
  ON CONFLICT(run_id,symbol,strategy_id) DO NOTHING;
  RETURN NEW;
END $$;

CREATE TRIGGER capture AFTER INSERT OR UPDATE OF payload ON symbol_snapshots
FOR EACH ROW EXECUTE FUNCTION pg_temp.capture_strategy_observations();

INSERT INTO parent_snapshots VALUES ('success-run',61,'PENDING');
DO $$
DECLARE
  offset_num integer;
  batch_count integer;
  tick timestamptz;
BEGIN
  FOR offset_num IN 0..60 BY 8 LOOP
    tick := clock_timestamp();
    INSERT INTO symbol_snapshots(run_id,symbol,collected_at_utc,state,trade_permission,payload)
      SELECT 'success-run', 'SYM'||lpad(g::text,3,'0'),
             timestamptz '2026-11-05 03:00:00+00', 'WATCH', false,
             jsonb_build_object('symbol','SYM'||lpad(g::text,3,'0'))
      FROM generate_series(offset_num+1, least(offset_num+8,61)) AS g
    ON CONFLICT(run_id,symbol) DO NOTHING;
    INSERT INTO batch_timings VALUES (offset_num/8 + 1,
      extract(epoch from clock_timestamp() - tick) * 1000);
    SELECT count(*) INTO batch_count FROM symbol_snapshots
      WHERE run_id='success-run';
    IF batch_count <> least(offset_num+8,61) THEN
      RAISE EXCEPTION 'Incomplete synthetic batch %, observed %',offset_num,batch_count;
    END IF;
  END LOOP;
  IF (SELECT count(*) FROM symbol_snapshots WHERE run_id='success-run') <> 61 THEN
    RAISE EXCEPTION 'Missing synthetic child rows after eight batches';
  END IF;
  IF (SELECT count(*) FROM synthetic_strategy_observations WHERE run_id='success-run') <> 610 THEN
    RAISE EXCEPTION 'Missing synthetic per-symbol strategy rows';
  END IF;
END $$;

-- Replay a batch as if an HTTP client lost the response AFTER COMMIT:
-- ON CONFLICT DO NOTHING must not fire update triggers or rewrite outcomes.
INSERT INTO symbol_snapshots(run_id,symbol,collected_at_utc,state,trade_permission,payload)
  SELECT 'success-run','SYM'||lpad(g::text,3,'0'),
    timestamptz '2026-11-05 03:00:00+00','CHANGED_IF_REWRITTEN',true,
    jsonb_build_object('symbol','SYM'||lpad(g::text,3,'0'),'wrong',true)
  FROM generate_series(1,8) AS g
ON CONFLICT(run_id,symbol) DO NOTHING;

DO $$
BEGIN
  IF (SELECT count(*) FROM symbol_snapshots WHERE run_id='success-run') <> 61
     OR (SELECT count(*) FROM trigger_fires WHERE run_id='success-run') <> 61
     OR (SELECT count(*) FROM synthetic_strategy_observations WHERE run_id='success-run') <> 610
  THEN
    RAISE EXCEPTION 'Ambiguous HTTP replay duplicated child/strategy evidence';
  END IF;
  IF EXISTS (
    SELECT 1 FROM symbol_snapshots
      WHERE run_id='success-run' AND
      (state <> 'WATCH' OR trade_permission OR payload ? 'wrong')
  ) THEN
    RAISE EXCEPTION 'Ambiguous retry rewrote immutable child evidence';
  END IF;
END $$;

-- A failed statement's per-row inserts/trigger effects must roll back together
-- on a disposable database; no partial test run may be marked complete.
INSERT INTO parent_snapshots VALUES ('failing-run',61,'PENDING');
DO $$
BEGIN
  BEGIN
    INSERT INTO symbol_snapshots(run_id,symbol,collected_at_utc,state,trade_permission,payload)
      SELECT 'failing-run','SYM'||lpad(g::text,3,'0'),
        timestamptz '2026-11-05 03:20:00+00','WATCH',false,
        jsonb_build_object('symbol','SYM'||lpad(g::text,3,'0'))
      FROM generate_series(1,16) AS g
    ON CONFLICT(run_id,symbol) DO NOTHING;
    RAISE EXCEPTION 'Fault injection did not execute';
  EXCEPTION WHEN raise_exception THEN
    IF SQLERRM <> 'synthetic injected child trigger fault' THEN RAISE; END IF;
  END;
  IF EXISTS(SELECT 1 FROM symbol_snapshots WHERE run_id='failing-run')
    OR EXISTS(SELECT 1 FROM trigger_fires WHERE run_id='failing-run')
    OR EXISTS(SELECT 1 FROM synthetic_strategy_observations WHERE run_id='failing-run')
  THEN
    RAISE EXCEPTION 'Failed write leaked partial transaction records';
  END IF;
  IF (SELECT state FROM parent_snapshots WHERE run_id='failing-run') <> 'PENDING' THEN
    RAISE EXCEPTION 'Failed canonical parent incorrectly marked verified';
  END IF;
END $$;

SELECT count(*) AS verified_batches,
  round(percentile_cont(0.5) WITHIN GROUP(ORDER BY elapsed_ms)::numeric,3) AS p50_ms,
  round(percentile_cont(0.95) WITHIN GROUP(ORDER BY elapsed_ms)::numeric,3) AS p95_ms,
  round(percentile_cont(0.99) WITHIN GROUP(ORDER BY elapsed_ms)::numeric,3) AS p99_ms
FROM batch_timings;
-- Synthetic PG trigger measurements exclude PostgREST, production data and load.
