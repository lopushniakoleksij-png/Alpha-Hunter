-- ALPHA HUNTER P0: EPHEMERAL POSTGRESQL 17 ONLY, synthetic data.
-- Never run against Supabase, production, or a real paper/live order database.
-- Purpose: 61-symbol 57014 failure rollback, safe exact-content replay; and
-- 30-symbol source-error + missing-price source-aware stage cardinalities.
-- 57014 below is an injected SQLSTATE, not a wall-clock timeout measurement.
-- QA triggers are simulated, not production's private transitive trigger graph.
CREATE TABLE public.qa_atomic_scale_fixtures_v01 (
  case_name text primary key,
  parent_rows jsonb not null,
  children_rows jsonb not null,
  signals_rows jsonb not null,
  features_rows jsonb not null,
  readiness_rows jsonb not null
);

-- Independent run IDs to avoid interfering with existing QA_50 and service-role fixtures.
INSERT INTO public.qa_atomic_scale_fixtures_v01
SELECT 'SIXTY_ONE',
 jsonb_build_array(jsonb_build_object(
   'run_id','QA_61_TIMEOUT','collected_at_utc','2026-11-08T10:00:00Z',
   'version','qa-61','product_type','usdt-futures','symbol_count',61,
   'error_count',0,'payload',jsonb_build_object('qa','61-synthetic'))),
 (SELECT jsonb_agg(jsonb_build_object(
   'run_id','QA_61_TIMEOUT','symbol',format('T%sUSDT',lpad(n::text,3,'0')),
   'collected_at_utc','2026-11-08T10:00:00Z','state','WATCH',
   'state_changed',false,'trade_permission',false,
   'payload',jsonb_build_object('qa','61','ordinal',n)) ORDER BY n)
   FROM generate_series(1,61) n),
 (SELECT jsonb_agg(jsonb_build_object(
   'run_id','QA_61_TIMEOUT','symbol',format('T%sUSDT',lpad(n::text,3,'0')),
   'signal_id',format('QA61_SIGNAL_%s',lpad(n::text,3,'0')),
   'detected_at_utc','2026-11-08T10:00:00Z','reference_price',100+n,
   'trade_permission',false,'payload',jsonb_build_object('qa','61')) ORDER BY n)
   FROM generate_series(1,61) n),
 (SELECT jsonb_agg(jsonb_build_object(
   'run_id','QA_61_TIMEOUT','symbol',format('T%sUSDT',lpad(n::text,3,'0')),
   'signal_id',format('QA61_SIGNAL_%s',lpad(n::text,3,'0')),
   'captured_at_utc','2026-11-08T10:00:00Z','trade_permission',false,
   'features','{}'::jsonb,'source_payload',jsonb_build_object('qa','61')) ORDER BY n)
   FROM generate_series(1,61) n),
 (SELECT jsonb_agg(jsonb_build_object(
   'run_id','QA_61_TIMEOUT','symbol',format('T%sUSDT',lpad(n::text,3,'0')),
   'observed_at_utc','2026-11-08T10:00:00Z','trade_permission',false,
   'v7_trade_ready',false) ORDER BY n) FROM generate_series(1,61) n);

-- A synthetic nested failure with the SAME SQLSTATE as production, at the 61st
-- symbol, to prove all earlier effects roll back in one RPC transaction.
CREATE OR REPLACE FUNCTION public.qa_inject_symbol_57014_v01()
RETURNS trigger LANGUAGE plpgsql AS $qa$
BEGIN
  IF NEW.run_id='QA_61_TIMEOUT' AND NEW.symbol='T061USDT' THEN
    RAISE EXCEPTION USING ERRCODE='57014', MESSAGE='QA_INJECTED_SQLSTATE_57014';
  END IF;
  RETURN NEW;
END
$qa$;
CREATE TRIGGER qa_inject_symbol_57014_v01
AFTER INSERT ON public.alpha_hunter_symbol_snapshots
FOR EACH ROW EXECUTE FUNCTION public.qa_inject_symbol_57014_v01();

DO $qa$
DECLARE f public.qa_atomic_scale_fixtures_v01%ROWTYPE;
BEGIN
 SELECT * INTO STRICT f FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='SIXTY_ONE';
 BEGIN
   PERFORM public.alpha_hunter_commit_core_scan_v01(
     f.parent_rows,f.children_rows,f.signals_rows,f.features_rows,f.readiness_rows);
   RAISE EXCEPTION 'QA61_UNEXPECTED_COMMIT_WITH_57014_INJECTED';
 EXCEPTION WHEN SQLSTATE '57014' THEN
   RAISE NOTICE 'PASS: injected SQLSTATE 57014 stopped 61-symbol atomic request';
 END;
 IF EXISTS(SELECT 1 FROM public.alpha_hunter_snapshots WHERE run_id='QA_61_TIMEOUT')
    OR EXISTS(SELECT 1 FROM public.alpha_hunter_symbol_snapshots WHERE run_id='QA_61_TIMEOUT')
    OR EXISTS(SELECT 1 FROM public.alpha_hunter_signals WHERE run_id='QA_61_TIMEOUT')
    OR EXISTS(SELECT 1 FROM public.alpha_hunter_signal_features WHERE run_id='QA_61_TIMEOUT')
    OR EXISTS(SELECT 1 FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id='QA_61_TIMEOUT')
    OR EXISTS(SELECT 1 FROM public.qa_atomic_trigger_events WHERE run_id='QA_61_TIMEOUT')
 THEN
   RAISE EXCEPTION 'QA61_57014_LEFT_PARTIAL_EVIDENCE_OR_TRIGGER_SIDE_EFFECTS';
 END IF;
 RAISE NOTICE 'PASS: 61-symbol 57014 rolled back all five core families and synthetic side effects';
END
$qa$;
DROP TRIGGER qa_inject_symbol_57014_v01 ON public.alpha_hunter_symbol_snapshots;
DROP FUNCTION public.qa_inject_symbol_57014_v01();

DO $qa$
DECLARE f public.qa_atomic_scale_fixtures_v01%ROWTYPE;
        receipt jsonb;
        before_count bigint;
BEGIN
 SELECT * INTO STRICT f FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='SIXTY_ONE';
 receipt := public.alpha_hunter_commit_core_scan_v01(
   f.parent_rows,f.children_rows,f.signals_rows,f.features_rows,f.readiness_rows);
 IF receipt->>'committed'<>'true' OR receipt->>'run_id'<>'QA_61_TIMEOUT'
    OR receipt->>'parent_count'<>'1' OR receipt->>'symbol_count'<>'61'
    OR receipt->>'signal_count'<>'61' OR receipt->>'feature_count'<>'61'
    OR receipt->>'readiness_count'<>'61'
 THEN RAISE EXCEPTION 'QA61_COMMIT_RECEIPT_MISMATCH %',receipt; END IF;
 IF (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id='QA_61_TIMEOUT')<>1
    OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id='QA_61_TIMEOUT')<>61
    OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id='QA_61_TIMEOUT')<>61
    OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id='QA_61_TIMEOUT')<>61
    OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id='QA_61_TIMEOUT')<>61
    OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id='QA_61_TIMEOUT')<>306
 THEN RAISE EXCEPTION 'QA61_COMMIT_INCOMPLETE_OR_BAD_SIDE_EFFECT_COUNT'; END IF;
 SELECT count(*) INTO before_count FROM public.qa_atomic_trigger_events WHERE run_id='QA_61_TIMEOUT';
 receipt := public.alpha_hunter_commit_core_scan_v01(
   f.parent_rows,f.children_rows,f.signals_rows,f.features_rows,f.readiness_rows);
 IF receipt->>'symbol_count'<>'61'
    OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id='QA_61_TIMEOUT')<>before_count
 THEN RAISE EXCEPTION 'QA61_REPLAY_DUPLICATED_SIDE_EFFECTS'; END IF;
 RAISE NOTICE 'PASS: 61-symbol 57014 retry committed exactly once with zero repeated trigger effects';
END
$qa$;

-- 30 symbols: one upstream error omits readiness, and one missing price omits
-- signal+feature but retains readiness; this is source-aware, not 30/30/30/30.
INSERT INTO public.qa_atomic_scale_fixtures_v01
SELECT 'THIRTY_MIXED',
 jsonb_build_array(jsonb_build_object(
   'run_id','QA_30_PARTIAL_SOURCE','collected_at_utc','2026-11-08T10:10:00Z',
   'version','qa-30','product_type','usdt-futures','symbol_count',30,
   'error_count',1,'payload',jsonb_build_object('qa','30-mixed-synthetic'))),
 (SELECT jsonb_agg(jsonb_build_object(
   'run_id','QA_30_PARTIAL_SOURCE','symbol',format('M%sUSDT',lpad(n::text,3,'0')),
   'collected_at_utc','2026-11-08T10:10:00Z','state','WATCH',
   'state_changed',false,'trade_permission',false,
   'last_price',CASE WHEN n=2 THEN NULL ELSE (100+n)::float8 END,
   'error',CASE WHEN n=1 THEN 'UPSTREAM_SOURCE_ERROR' ELSE NULL END,
   'payload',jsonb_build_object('qa','30-mixed','ordinal',n)) ORDER BY n)
   FROM generate_series(1,30) n),
 (SELECT jsonb_agg(jsonb_build_object(
   'run_id','QA_30_PARTIAL_SOURCE','symbol',format('M%sUSDT',lpad(n::text,3,'0')),
   'signal_id',format('QA30_SIGNAL_%s',lpad(n::text,3,'0')),
   'detected_at_utc','2026-11-08T10:10:00Z','reference_price',100+n,
   'trade_permission',false,'payload',jsonb_build_object('qa','30-mixed')) ORDER BY n)
   FROM generate_series(3,30) n),
 (SELECT jsonb_agg(jsonb_build_object(
   'run_id','QA_30_PARTIAL_SOURCE','symbol',format('M%sUSDT',lpad(n::text,3,'0')),
   'signal_id',format('QA30_SIGNAL_%s',lpad(n::text,3,'0')),
   'captured_at_utc','2026-11-08T10:10:00Z','trade_permission',false,
   'features','{}'::jsonb,'source_payload',jsonb_build_object('qa','30-mixed')) ORDER BY n)
   FROM generate_series(3,30) n),
 (SELECT jsonb_agg(jsonb_build_object(
   'run_id','QA_30_PARTIAL_SOURCE','symbol',format('M%sUSDT',lpad(n::text,3,'0')),
   'observed_at_utc','2026-11-08T10:10:00Z','trade_permission',false,
   'v7_trade_ready',false) ORDER BY n) FROM generate_series(2,30) n);

DO $qa$
DECLARE f public.qa_atomic_scale_fixtures_v01%ROWTYPE;
        receipt jsonb;
        n_before bigint;
BEGIN
 SELECT * INTO STRICT f FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='THIRTY_MIXED';
 receipt := public.alpha_hunter_commit_core_scan_v01(
   f.parent_rows,f.children_rows,f.signals_rows,f.features_rows,f.readiness_rows);
 IF receipt->>'committed'<>'true' OR receipt->>'run_id'<>'QA_30_PARTIAL_SOURCE'
    OR receipt->>'parent_count'<>'1' OR receipt->>'symbol_count'<>'30'
    OR receipt->>'signal_count'<>'28' OR receipt->>'feature_count'<>'28'
    OR receipt->>'readiness_count'<>'29'
 THEN RAISE EXCEPTION 'QA30_SOURCE_AWARE_RECEIPT_INCORRECT %',receipt; END IF;
 IF (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id='QA_30_PARTIAL_SOURCE')<>1
    OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id='QA_30_PARTIAL_SOURCE')<>30
    OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id='QA_30_PARTIAL_SOURCE')<>28
    OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id='QA_30_PARTIAL_SOURCE')<>28
    OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id='QA_30_PARTIAL_SOURCE')<>29
    OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id='QA_30_PARTIAL_SOURCE')<>144
 THEN RAISE EXCEPTION 'QA30_SOURCE_AWARE_STAGE_COUNTS_INCORRECT'; END IF;
 SELECT count(*) INTO n_before FROM public.qa_atomic_trigger_events WHERE run_id='QA_30_PARTIAL_SOURCE';
 receipt := public.alpha_hunter_commit_core_scan_v01(
   f.parent_rows,f.children_rows,f.signals_rows,f.features_rows,f.readiness_rows);
 IF receipt->>'symbol_count'<>'30' OR
    (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id='QA_30_PARTIAL_SOURCE')<>n_before
 THEN RAISE EXCEPTION 'QA30_REPLAY_CAUSED_DUPLICATE_EFFECTS'; END IF;
 RAISE NOTICE 'PASS: 30 symbols/1 source error/1 missing price: 30 symbols, 28 signals, 28 features, 29 readiness, replay idempotent';
END
$qa$;
