-- EPHEMERAL PostgreSQL only. No production connections.
-- Exercise a 50-symbol scan (normal observed production cohort size).
-- Does not replace full production trigger-graph / qualified review.
DO $qa_50$
DECLARE
  v_run_id text := 'QA_FIFTY_SYMBOLS_PRIVATE';
  p_parent jsonb;
  p_children jsonb;
  p_signals jsonb;
  p_features jsonb;
  p_readiness jsonb;
  receipt jsonb;
  events_before bigint;
  expected_event_count bigint := 251;
BEGIN
  p_parent := jsonb_build_array(jsonb_build_object(
    'run_id', v_run_id,
    'collected_at_utc','2026-11-07T08:00:00Z',
    'version','fifty-symbol-qa',
    'product_type','usdt-futures',
    'symbol_count',50,
    'error_count',0,
    'payload',jsonb_build_object('qa','isolated-only')
  ));

  SELECT jsonb_agg(jsonb_build_object(
    'run_id',v_run_id,'symbol',format('S%sUSDT',lpad(n::text,3,'0')),
    'collected_at_utc','2026-11-07T08:00:00Z',
    'trade_permission',false,'state_changed',false,'state','WATCH',
    'payload',jsonb_build_object('source','synthetic','ordinal',n)
  ) ORDER BY n)
  INTO p_children
  FROM generate_series(1,50) AS n;

  SELECT jsonb_agg(jsonb_build_object(
    'run_id',v_run_id,'signal_id',format('QA_SIGNAL_%s',lpad(n::text,3,'0')),
    'symbol',format('S%sUSDT',lpad(n::text,3,'0')),
    'detected_at_utc','2026-11-07T08:00:00Z',
    'reference_price',100 + n,
    'state','WATCH','trade_permission',false,
    'payload',jsonb_build_object('source','synthetic')
  ) ORDER BY n)
  INTO p_signals
  FROM generate_series(1,50) AS n;

  SELECT jsonb_agg(jsonb_build_object(
    'run_id',v_run_id,'signal_id',format('QA_SIGNAL_%s',lpad(n::text,3,'0')),
    'symbol',format('S%sUSDT',lpad(n::text,3,'0')),
    'captured_at_utc','2026-11-07T08:00:00Z',
    'trade_permission',false,'features',jsonb_build_object(),
    'source_payload',jsonb_build_object('source','synthetic')
  ) ORDER BY n)
  INTO p_features
  FROM generate_series(1,50) AS n;

  SELECT jsonb_agg(jsonb_build_object(
    'run_id',v_run_id,'symbol',format('S%sUSDT',lpad(n::text,3,'0')),
    'observed_at_utc','2026-11-07T08:00:00Z',
    'state','WATCH','trade_permission',false,'v7_trade_ready',false
  ) ORDER BY n)
  INTO p_readiness
  FROM generate_series(1,50) AS n;

  -- Fail closed before any write when exactly one required feature is absent.
  BEGIN
    PERFORM public.alpha_hunter_commit_core_scan_v01(
      p_parent,p_children,p_signals,p_features - 0,p_readiness
    );
    RAISE EXCEPTION 'QA_EXPECTED_MISSING_FEATURE_FAILURE_ABSENT';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%identity coverage invalid%' THEN RAISE; END IF;
  END;

  -- Same number of features but one references a different signal ID.
  BEGIN
    PERFORM public.alpha_hunter_commit_core_scan_v01(
      p_parent,p_children,p_signals,
      jsonb_set(p_features,'{0,signal_id}','"QA_MISSING_SIGNAL"'::jsonb),
      p_readiness
    );
    RAISE EXCEPTION 'QA_EXPECTED_ORPHAN_FEATURE_FAILURE_ABSENT';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%identity coverage invalid%' THEN RAISE; END IF;
  END;

  -- Readiness cannot refer to a symbol absent from this scan's children.
  BEGIN
    PERFORM public.alpha_hunter_commit_core_scan_v01(
      p_parent,p_children,p_signals,p_features,
      jsonb_set(p_readiness,'{0,symbol}','"QA_UNKNOWN_SYMBOL"'::jsonb)
    );
    RAISE EXCEPTION 'QA_EXPECTED_ORPHAN_READINESS_FAILURE_ABSENT';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%identity coverage invalid%' THEN RAISE; END IF;
  END;
  IF (SELECT count(*) FROM public.alpha_hunter_snapshots x WHERE x.run_id=v_run_id) <> 0 THEN
    RAISE EXCEPTION 'QA_EVIDENCE_VALIDATION_WROTE_BEFORE_REJECTING_PAYLOAD';
  END IF;
  RAISE NOTICE 'PASS: incomplete/misidentified features and readiness rejected before persistence';

  -- A downstream trigger fails after 50 parent/child/signal writes.
  PERFORM set_config('qa.fail_feature','on',true);
  BEGIN
    PERFORM public.alpha_hunter_commit_core_scan_v01(
      p_parent,p_children,p_signals,p_features,p_readiness
    );
    RAISE EXCEPTION 'QA_EXPECTED_FEATURE_FAILURE_ABSENT';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM NOT LIKE '%INJECTED_FEATURE_TRIGGER_FAILURE%' THEN RAISE; END IF;
  END;
  PERFORM set_config('qa.fail_feature','off',true);

  IF (SELECT count(*) FROM public.alpha_hunter_snapshots x WHERE x.run_id=v_run_id)<>0
      OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots x WHERE x.run_id=v_run_id)<>0
      OR (SELECT count(*) FROM public.alpha_hunter_signals x WHERE x.run_id=v_run_id)<>0
      OR (SELECT count(*) FROM public.alpha_hunter_signal_features x WHERE x.run_id=v_run_id)<>0
      OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 x WHERE x.run_id=v_run_id)<>0
      OR (SELECT count(*) FROM public.qa_atomic_trigger_events x WHERE x.run_id=v_run_id)<>0 THEN
    RAISE EXCEPTION 'QA_50_CHILD_ROLLBACK_INCOMPLETE';
  END IF;
  RAISE NOTICE 'PASS: 50-symbol downstream trigger failure rolled back every core family and side effect';

  receipt := public.alpha_hunter_commit_core_scan_v01(
    p_parent,p_children,p_signals,p_features,p_readiness
  );
  IF receipt->>'committed' <> 'true'
     OR receipt->>'parent_count' <> '1'
     OR receipt->>'symbol_count' <> '50'
     OR receipt->>'signal_count' <> '50'
     OR receipt->>'feature_count' <> '50'
     OR receipt->>'readiness_count' <> '50' THEN
    RAISE EXCEPTION 'QA_50_BAD_RECEIPT: %',receipt;
  END IF;
  IF (SELECT count(*) FROM public.alpha_hunter_snapshots x WHERE x.run_id=v_run_id)<>1
     OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots x WHERE x.run_id=v_run_id)<>50
     OR (SELECT count(*) FROM public.alpha_hunter_signals x WHERE x.run_id=v_run_id)<>50
     OR (SELECT count(*) FROM public.alpha_hunter_signal_features x WHERE x.run_id=v_run_id)<>50
     OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 x WHERE x.run_id=v_run_id)<>50
     OR (SELECT count(*) FROM public.qa_atomic_trigger_events x WHERE x.run_id=v_run_id)<>expected_event_count THEN
    RAISE EXCEPTION 'QA_50_PERSISTENCE_NOT_COMPLETE';
  END IF;
  RAISE NOTICE 'PASS: 50-symbol scan saved parent, 50 symbols, 50 signals, 50 features and 50 readiness rows';

  SELECT count(*) INTO events_before FROM public.qa_atomic_trigger_events x WHERE x.run_id=v_run_id;
  receipt := public.alpha_hunter_commit_core_scan_v01(
    p_parent,p_children,p_signals,p_features,p_readiness
  );
  IF (SELECT count(*) FROM public.qa_atomic_trigger_events x WHERE x.run_id=v_run_id) <> events_before
      OR receipt->>'symbol_count'<>'50' THEN
    RAISE EXCEPTION 'QA_50_DUPLICATE_TRIGGER_EVENTS_ON_RETRY';
  END IF;
  RAISE NOTICE 'PASS: 50-symbol committed replay produced zero additional BEFORE/AFTER trigger effects';
END
$qa_50$;
