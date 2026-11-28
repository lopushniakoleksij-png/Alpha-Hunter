-- P0 E1/E6: reproduce the two CONFIRMED legacy persistence failure shapes.
-- DISPOSABLE postgres:17 GitHub Actions fixture ONLY, not production-equivalent.
-- The SQLSTATE 57014 below is INJECTED by a QA trigger, NOT a timed
-- PostgreSQL statement_timeout. Real timeout tests are separate.
-- Tests 30/50/61 symbol payloads; no real scan data, trading, or secrets.
DO $guard$
BEGIN
  IF current_database() <> 'isolated_atomic_scan_qa'
     OR current_user <> 'postgres'
     OR to_regclass('public.qa_atomic_trigger_events') IS NULL
     OR to_regprocedure('public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)') IS NULL THEN
    RAISE EXCEPTION 'QA_P0_WRONG_DISPOSABLE_ENVIRONMENT';
  END IF;
END
$guard$;

CREATE OR REPLACE FUNCTION public.qa_p0_inject_failure_shape_v01()
RETURNS trigger LANGUAGE plpgsql AS $trigger$
BEGIN
  IF tg_table_name='alpha_hunter_snapshots'
     AND current_setting('qa.p0_no_parent',true)='on'
     AND new.run_id LIKE 'QA_P0_NOPARENT_%' THEN
    RAISE EXCEPTION USING ERRCODE='57014',
      MESSAGE='QA_P0_INJECT_BEFORE_PARENT_57014';
  END IF;
  IF tg_table_name='alpha_hunter_symbol_snapshots'
     AND current_setting('qa.p0_child_failure',true)='on'
     AND new.run_id LIKE 'QA_P0_PARENT_ONLY_%' THEN
    RAISE EXCEPTION USING ERRCODE='57014',
      MESSAGE='QA_P0_INJECT_CHILD_AFTER_DURABLE_PARENT_57014';
  END IF;
  IF tg_table_name='alpha_hunter_symbol_snapshots'
     AND current_setting('qa.p0_atomic_child_failure',true)='on'
     AND new.run_id LIKE 'QA_P0_ATOMIC_%' THEN
    RAISE EXCEPTION USING ERRCODE='57014',
      MESSAGE='QA_P0_INJECT_ATOMIC_CHILD_57014';
  END IF;
  RETURN new;
END
$trigger$;

CREATE TRIGGER qa_p0_no_parent_before_v01
BEFORE INSERT ON public.alpha_hunter_snapshots
FOR EACH ROW EXECUTE FUNCTION public.qa_p0_inject_failure_shape_v01();
CREATE TRIGGER qa_p0_child_before_v01
BEFORE INSERT ON public.alpha_hunter_symbol_snapshots
FOR EACH ROW EXECUTE FUNCTION public.qa_p0_inject_failure_shape_v01();

-- Failure class A: request fails BEFORE the parent write; nothing persists.
DO $no_parent$
DECLARE n int; rid text;
BEGIN
  PERFORM set_config('qa.p0_no_parent','on',true);
  FOREACH n IN ARRAY ARRAY[30,50,61] LOOP
    rid := 'QA_P0_NOPARENT_' || n::text;
    BEGIN
      INSERT INTO public.alpha_hunter_snapshots
        (run_id,collected_at_utc,version,product_type,symbol_count,error_count,payload)
      VALUES (rid,'2026-11-20T16:00:00Z','qa','usdt-futures',n,0,
              jsonb_build_object('qa','disposable-only'));
      RAISE EXCEPTION 'QA_P0_EXPECTED_NO_PARENT_57014_MISSING';
    EXCEPTION WHEN SQLSTATE '57014' THEN
      NULL;
    END;
    IF EXISTS (SELECT 1 FROM public.alpha_hunter_snapshots WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_symbol_snapshots WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_signals WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_signal_features WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.qa_atomic_trigger_events WHERE run_id=rid) THEN
      RAISE EXCEPTION 'QA_P0_NO_PARENT_FAILURE_LEFT_EVIDENCE';
    END IF;
  END LOOP;
  PERFORM set_config('qa.p0_no_parent','off',true);
  RAISE NOTICE 'PASS: 30/50/61 early failures leave no parent, child or trigger effects';
END
$no_parent$;

-- Legacy split-write class B: parent is durably committed in THIS SQL
-- statement before a distinct SQL statement attempts any child write.
DO $legacy_parent_commit$
DECLARE n int; rid text;
BEGIN
  FOREACH n IN ARRAY ARRAY[30,50,61] LOOP
    rid := 'QA_P0_PARENT_ONLY_' || n::text;
    INSERT INTO public.alpha_hunter_snapshots
      (run_id,collected_at_utc,version,product_type,symbol_count,error_count,payload)
    VALUES (rid,'2026-11-20T16:00:00Z','qa','usdt-futures',n,0,
            jsonb_build_object('qa','disposable-only'));
  END LOOP;
END
$legacy_parent_commit$;

-- New top-level DO statement => preceding parent INSERTs were committed.
-- The child INSERT now fails with injected 57014; no child transaction commits.
DO $legacy_child_failure$
DECLARE n int; rid text;
BEGIN
  PERFORM set_config('qa.p0_child_failure','on',true);
  FOREACH n IN ARRAY ARRAY[30,50,61] LOOP
    rid := 'QA_P0_PARENT_ONLY_' || n::text;
    BEGIN
      INSERT INTO public.alpha_hunter_symbol_snapshots
        (run_id,symbol,collected_at_utc,state,trade_permission,payload)
      SELECT rid, format('L%sUSDT',lpad(k::text,3,'0')),
             '2026-11-20T16:00:00Z','WATCH',false,
             jsonb_build_object('qa','disposable-only')
      FROM generate_series(1,n) k;
      RAISE EXCEPTION 'QA_P0_EXPECTED_CHILD_57014_MISSING';
    EXCEPTION WHEN SQLSTATE '57014' THEN
      NULL;
    END;
    IF (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id=rid)<>1
       OR (SELECT symbol_count FROM public.alpha_hunter_snapshots WHERE run_id=rid)<>n
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_symbol_snapshots WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_signals WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_signal_features WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id=rid)
       OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id=rid)<>1 THEN
      RAISE EXCEPTION 'QA_P0_LEGACY_PARENT_ONLY_NOT_REPRODUCED';
    END IF;
  END LOOP;
  PERFORM set_config('qa.p0_child_failure','off',true);
  RAISE NOTICE 'PASS: 30/50/61 split writes reproduce durable parent-only after child 57014';
END
$legacy_child_failure$;

-- For each size, inject an identical child failure INSIDE one atomic RPC.
-- Unlike the legacy split writer, the parent and all nested side effects must
-- roll back. A subsequent clean commit and replay must be complete/once-only.
DO $atomic$
DECLARE
  n int;
  rid text;
  p_parent jsonb;
  p_children jsonb;
  p_signals jsonb;
  p_features jsonb;
  p_readiness jsonb;
  receipt jsonb;
  event_count bigint;
BEGIN
  FOREACH n IN ARRAY ARRAY[30,50,61] LOOP
    rid := 'QA_P0_ATOMIC_' || n::text;
    p_parent := jsonb_build_array(jsonb_build_object(
       'run_id',rid,'collected_at_utc','2026-11-20T16:00:00Z',
       'version','qa-p0','product_type','usdt-futures',
       'symbol_count',n,'error_count',0,
       'payload',jsonb_build_object('qa','disposable-only')));
    SELECT jsonb_agg(jsonb_build_object(
      'run_id',rid,'symbol',format('A%sUSDT',lpad(k::text,3,'0')),
      'collected_at_utc','2026-11-20T16:00:00Z',
      'state','WATCH','state_changed',false,'trade_permission',false,
      'payload',jsonb_build_object('qa','disposable-only')) ORDER BY k)
    INTO p_children FROM generate_series(1,n) k;
    SELECT jsonb_agg(jsonb_build_object(
      'run_id',rid,'signal_id',rid||'_SIG_'||k::text,
      'symbol',format('A%sUSDT',lpad(k::text,3,'0')),
      'detected_at_utc','2026-11-20T16:00:00Z',
      'reference_price',100+k,'trade_permission',false,
      'payload',jsonb_build_object('qa','disposable-only')) ORDER BY k)
    INTO p_signals FROM generate_series(1,n) k;
    SELECT jsonb_agg(jsonb_build_object(
      'run_id',rid,'signal_id',rid||'_SIG_'||k::text,
      'symbol',format('A%sUSDT',lpad(k::text,3,'0')),
      'captured_at_utc','2026-11-20T16:00:00Z',
      'trade_permission',false,'features','{}'::jsonb,
      'source_payload',jsonb_build_object('qa','disposable-only')) ORDER BY k)
    INTO p_features FROM generate_series(1,n) k;
    SELECT jsonb_agg(jsonb_build_object(
      'run_id',rid,'symbol',format('A%sUSDT',lpad(k::text,3,'0')),
      'observed_at_utc','2026-11-20T16:00:00Z',
      'trade_permission',false,'v7_trade_ready',false) ORDER BY k)
    INTO p_readiness FROM generate_series(1,n) k;

    PERFORM set_config('qa.p0_atomic_child_failure','on',true);
    BEGIN
      PERFORM public.alpha_hunter_commit_core_scan_v01(
        p_parent,p_children,p_signals,p_features,p_readiness);
      RAISE EXCEPTION 'QA_P0_EXPECTED_ATOMIC_CHILD_57014_MISSING';
    EXCEPTION WHEN SQLSTATE '57014' THEN
      NULL;
    END;
    PERFORM set_config('qa.p0_atomic_child_failure','off',true);
    IF EXISTS (SELECT 1 FROM public.alpha_hunter_snapshots WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_symbol_snapshots WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_signals WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_signal_features WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id=rid)
       OR EXISTS (SELECT 1 FROM public.qa_atomic_trigger_events WHERE run_id=rid) THEN
      RAISE EXCEPTION 'QA_P0_ATOMIC_FAILED_ROLLBACK';
    END IF;

    receipt := public.alpha_hunter_commit_core_scan_v01(
      p_parent,p_children,p_signals,p_features,p_readiness);
    IF receipt->>'committed'<>'true' OR receipt->>'run_id'<>rid
       OR (receipt->>'parent_count')::int<>1
       OR (receipt->>'symbol_count')::int<>n
       OR (receipt->>'signal_count')::int<>n
       OR (receipt->>'feature_count')::int<>n
       OR (receipt->>'readiness_count')::int<>n
       OR (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id=rid)<>1
       OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=rid)<>n
       OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id=rid)<>n
       OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id=rid)<>n
       OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id=rid)<>n
       OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id=rid)<>(1+5*n) THEN
      RAISE EXCEPTION 'QA_P0_ATOMIC_RECOVERY_INCOMPLETE';
    END IF;
    SELECT count(*) INTO event_count FROM public.qa_atomic_trigger_events WHERE run_id=rid;
    receipt := public.alpha_hunter_commit_core_scan_v01(
      p_parent,p_children,p_signals,p_features,p_readiness);
    IF receipt->>'committed'<>'true'
       OR (SELECT count(*) FROM public.qa_atomic_trigger_events WHERE run_id=rid)<>event_count THEN
      RAISE EXCEPTION 'QA_P0_ATOMIC_REPLAY_DUPLICATED_EFFECTS';
    END IF;
  END LOOP;
  RAISE NOTICE 'PASS: 30/50/61 atomic child 57014 rolled back, recovery committed once, retry no duplicate effects';
END
$atomic$;

DROP TRIGGER qa_p0_child_before_v01 ON public.alpha_hunter_symbol_snapshots;
DROP TRIGGER qa_p0_no_parent_before_v01 ON public.alpha_hunter_snapshots;
DROP FUNCTION public.qa_p0_inject_failure_shape_v01();
