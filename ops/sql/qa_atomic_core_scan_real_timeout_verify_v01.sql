-- P0 Harada D7 / E1: inspect rollback after real PG statement_timeout,
-- remove only the disposable QA trigger, then verify exact replay semantics.
-- EPHEMERAL isolated_atomic_scan_qa only. No production credentials or data.
DO $qa$
BEGIN
  IF current_database() <> 'isolated_atomic_scan_qa'
     OR current_user <> 'postgres' THEN
    RAISE EXCEPTION 'QA_ONLY_WRONG_DATABASE_OR_ROLE';
  END IF;
  IF EXISTS (SELECT 1 FROM public.alpha_hunter_snapshots
             WHERE run_id='QA_61_REAL_TIMEOUT')
   OR EXISTS (SELECT 1 FROM public.alpha_hunter_symbol_snapshots
              WHERE run_id='QA_61_REAL_TIMEOUT')
   OR EXISTS (SELECT 1 FROM public.alpha_hunter_signals
              WHERE run_id='QA_61_REAL_TIMEOUT')
   OR EXISTS (SELECT 1 FROM public.alpha_hunter_signal_features
              WHERE run_id='QA_61_REAL_TIMEOUT')
   OR EXISTS (SELECT 1 FROM public.alpha_hunter_readiness_observations_v01
              WHERE run_id='QA_61_REAL_TIMEOUT')
   OR EXISTS (SELECT 1 FROM public.qa_atomic_trigger_events
              WHERE run_id='QA_61_REAL_TIMEOUT')
  THEN
    RAISE EXCEPTION 'QA_REAL_TIMEOUT_LEFT_PARTIAL_ROWS_OR_TRIGGER_SIDE_EFFECTS';
  END IF;
  RAISE NOTICE 'PASS: PostgreSQL-enforced nested 57014 rolled back every core table and synthetic side effect';
END
$qa$;
DROP TRIGGER qa_nested_real_timeout_v01 ON public.alpha_hunter_symbol_snapshots;
DROP FUNCTION public.qa_nested_real_timeout_v01();

DO $qa$
DECLARE
  f public.qa_atomic_scale_fixtures_v01%ROWTYPE;
  receipt jsonb;
  events_before bigint;
BEGIN
  SELECT * INTO STRICT f FROM public.qa_atomic_scale_fixtures_v01
  WHERE case_name='SIXTY_ONE_REAL_TIMEOUT';

  receipt := public.alpha_hunter_commit_core_scan_v01(
    f.parent_rows,f.children_rows,f.signals_rows,f.features_rows,f.readiness_rows);
  IF receipt->>'committed'<>'true'
     OR receipt->>'run_id'<>'QA_61_REAL_TIMEOUT'
     OR receipt->>'parent_count'<>'1'
     OR receipt->>'symbol_count'<>'61'
     OR receipt->>'signal_count'<>'61'
     OR receipt->>'feature_count'<>'61'
     OR receipt->>'readiness_count'<>'61' THEN
    RAISE EXCEPTION 'QA_REAL_TIMEOUT_RETRY_BAD_RECEIPT %',receipt;
  END IF;

  IF (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id='QA_61_REAL_TIMEOUT')<>1
     OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id='QA_61_REAL_TIMEOUT')<>61
     OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id='QA_61_REAL_TIMEOUT')<>61
     OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id='QA_61_REAL_TIMEOUT')<>61
     OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id='QA_61_REAL_TIMEOUT')<>61
     OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id='QA_61_REAL_TIMEOUT')<>306 THEN
    RAISE EXCEPTION 'QA_REAL_TIMEOUT_RETRY_INCOMPLETE_PERSISTENCE';
  END IF;

  SELECT count(*) INTO events_before FROM public.qa_atomic_trigger_events
    WHERE run_id='QA_61_REAL_TIMEOUT';
  receipt := public.alpha_hunter_commit_core_scan_v01(
    f.parent_rows,f.children_rows,f.signals_rows,f.features_rows,f.readiness_rows);
  IF receipt->>'committed'<>'true'
     OR receipt->>'symbol_count'<>'61'
     OR (SELECT count(*) FROM public.qa_atomic_trigger_events
         WHERE run_id='QA_61_REAL_TIMEOUT')<>events_before THEN
    RAISE EXCEPTION 'QA_REAL_TIMEOUT_REPLAY_DUPLICATED_TRIGGER_SIDE_EFFECTS';
  END IF;
  RAISE NOTICE 'PASS: 61-symbol retry after real PG 57014 commits once, duplicate replay has zero new trigger effects';
END
$qa$;
