-- Harada E6: verify durable effects after two genuinely overlapping RPC requests
-- to the same run identity (one identical and one conflicting), PG17 ephemeral only.
DO $qa$
DECLARE
  v_run_id text;
  v_case text;
  f public.qa_atomic_scale_fixtures_v01%ROWTYPE;
  receipt jsonb;
  prior_events bigint;
BEGIN
  IF current_database()<>'isolated_atomic_scan_qa' OR current_user<>'postgres' THEN
    RAISE EXCEPTION 'QA_ONLY_WRONG_DATABASE_OR_ROLE';
  END IF;
  FOREACH v_case IN ARRAY ARRAY['SIXTY_ONE_CONCURRENT','SIXTY_ONE_CONFLICT']
  LOOP
    SELECT * INTO STRICT f FROM public.qa_atomic_scale_fixtures_v01
    WHERE case_name=v_case;
    v_run_id:=f.parent_rows->0->>'run_id';
    IF (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id=v_run_id)<>1
      OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=v_run_id)<>61
      OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id=v_run_id)<>61
      OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id=v_run_id)<>61
      OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id=v_run_id)<>61
      OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id=v_run_id)<>306
    THEN RAISE EXCEPTION 'QA_CONCURRENT_DUPLICATE_OR_PARTIAL_EVIDENCE_FOR_%',v_case; END IF;
    IF (SELECT version FROM public.alpha_hunter_snapshots WHERE run_id=v_run_id)
       <> (f.parent_rows->0->>'version')
    THEN RAISE EXCEPTION 'QA_CONCURRENT_ORIGINAL_PARENT_OVERWRITTEN_%',v_case; END IF;
    SELECT count(*) INTO prior_events FROM public.qa_atomic_trigger_events WHERE run_id=v_run_id;
    receipt:=public.alpha_hunter_commit_core_scan_v01(
      f.parent_rows,f.children_rows,f.signals_rows,f.features_rows,f.readiness_rows);
    IF receipt->>'committed'<>'true'
      OR receipt->>'run_id'<>v_run_id
      OR receipt->>'parent_count'<>'1'
      OR receipt->>'symbol_count'<>'61'
      OR receipt->>'signal_count'<>'61'
      OR receipt->>'feature_count'<>'61'
      OR receipt->>'readiness_count'<>'61'
      OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id=v_run_id)<>prior_events
    THEN RAISE EXCEPTION 'QA_CONCURRENT_REPLAY_FAILED_FOR_%',v_case; END IF;
  END LOOP;
  RAISE NOTICE 'PASS: overlapping identical writers and conflicting writer serialized; 61 core rows per family, 306 trigger events each, no overwrite or replay side effects';
END $qa$;
DROP TRIGGER qa_concurrent_nested_delay_v01 ON public.alpha_hunter_symbol_snapshots;
DROP FUNCTION public.qa_concurrent_nested_delay_v01();
