-- E3: first committed RPC receipt was intentionally discarded by client.
-- This validates replay after a simulated lost acknowledgement, not a real network partition.
DO $qa$
DECLARE f public.qa_atomic_scale_fixtures_v01%ROWTYPE;
 receipt jsonb; before_events bigint;
BEGIN
 IF current_database()<>'isolated_atomic_scan_qa' OR current_user<>'postgres' THEN
  RAISE EXCEPTION 'QA_ONLY_WRONG_DATABASE_OR_ROLE';
 END IF;
 SELECT * INTO STRICT f FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='SIXTY_ONE_LOST_ACK';
 SELECT count(*) INTO before_events FROM public.qa_atomic_trigger_events WHERE run_id='QA_61_LOST_ACK';
 IF before_events<>306
 OR (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id='QA_61_LOST_ACK')<>1
 OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id='QA_61_LOST_ACK')<>61
 OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id='QA_61_LOST_ACK')<>61
 OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id='QA_61_LOST_ACK')<>61
 OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id='QA_61_LOST_ACK')<>61 THEN
 RAISE EXCEPTION 'QA_LOST_ACK_FIRST_COMMIT_INCOMPLETE';
 END IF;
 receipt:=public.alpha_hunter_commit_core_scan_v01(f.parent_rows,f.children_rows,f.signals_rows,f.features_rows,f.readiness_rows);
 IF receipt->>'committed'<>'true' OR receipt->>'run_id'<>'QA_61_LOST_ACK'
 OR receipt->>'symbol_count'<>'61' OR receipt->>'signal_count'<>'61'
 OR receipt->>'feature_count'<>'61' OR receipt->>'readiness_count'<>'61'
 OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id='QA_61_LOST_ACK')<>before_events THEN
 RAISE EXCEPTION 'QA_LOST_ACK_REPLAY_NOT_IDEMPOTENT %',receipt;
 END IF;
 RAISE NOTICE 'PASS: simulated lost receipt after commit, retry preserved 61 complete children and 306 trigger effects';
END $qa$;
