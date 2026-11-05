-- Disposable PG16/17 timeout/ambiguous retry contract. NEVER run on production.
\set ON_ERROR_STOP on
DO $$ BEGIN
 IF current_database() <> 'isolated_research' THEN
  RAISE EXCEPTION 'Refusing non-disposable database: %', current_database();
 END IF;
END $$;
CREATE TEMP TABLE timeout_parents(run_id text, symbol text, payload jsonb NOT NULL, PRIMARY KEY(run_id,symbol));
CREATE TEMP TABLE timeout_children(run_id text, symbol text, strategy int, PRIMARY KEY(run_id,symbol,strategy));
CREATE FUNCTION pg_temp.slow_capture() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 PERFORM pg_sleep(0.25);
 INSERT INTO timeout_children(run_id,symbol,strategy)
 SELECT NEW.run_id,NEW.symbol,g FROM generate_series(1,10) g
 ON CONFLICT DO NOTHING;
 RETURN NEW;
END $$;
CREATE TRIGGER timeout_capture AFTER INSERT OR UPDATE OF payload ON timeout_parents
 FOR EACH ROW EXECUTE FUNCTION pg_temp.slow_capture();
-- A real server-side statement timeout must abort the write. Catch at the psql
-- protocol boundary rather than a PL/pgSQL exception handler in the same command.
SET statement_timeout = '100ms';
\set ON_ERROR_STOP off
INSERT INTO timeout_parents VALUES('timeout-case','SYM1','{"attempt":1}'::jsonb);
\set observed_sqlstate :SQLSTATE
\set ON_ERROR_STOP on
RESET statement_timeout;
SELECT (:'observed_sqlstate' = '57014') AS expected_timeout \gset
\if :expected_timeout
\else
 \echo 'Expected PostgreSQL query_canceled SQLSTATE 57014'
 \quit 1
\endif
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM timeout_parents WHERE run_id='timeout-case')
 OR EXISTS(SELECT 1 FROM timeout_children WHERE run_id='timeout-case') THEN
  RAISE EXCEPTION 'Timed-out statement leaked parent/child rows';
 END IF;
END $$;
-- Retrying identical identity after a timed-out statement must produce one
-- parent and ten distinct child observations, not a duplicate or a partial row.
INSERT INTO timeout_parents VALUES('timeout-case','SYM1','{"attempt":2}'::jsonb)
 ON CONFLICT(run_id,symbol) DO UPDATE SET payload=EXCLUDED.payload;
INSERT INTO timeout_parents VALUES('timeout-case','SYM1','{"attempt":2}'::jsonb)
 ON CONFLICT(run_id,symbol) DO UPDATE SET payload=EXCLUDED.payload;
DO $$ BEGIN
 IF (SELECT count(*) FROM timeout_parents WHERE run_id='timeout-case') <> 1
 OR (SELECT count(*) FROM timeout_children WHERE run_id='timeout-case') <> 10
 OR (SELECT payload FROM timeout_parents WHERE run_id='timeout-case' AND symbol='SYM1') <> '{"attempt":2}'::jsonb THEN
  RAISE EXCEPTION 'Retry idempotence/child completeness failed';
 END IF;
END $$;
SELECT 'synthetic_timeout_retry_pass' AS result;
-- Does not model PostgREST network timeout after a successful server commit,
-- the real observation trigger, concurrent clients, or live Supabase.
