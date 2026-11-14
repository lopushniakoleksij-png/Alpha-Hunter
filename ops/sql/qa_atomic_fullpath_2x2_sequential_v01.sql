-- ALPHA HUNTER P0 / Harada D: 2x2 architecture x index comparison.
-- Isolated PostgreSQL17 only: installed after synthetic 505k full-path setup.
-- Uses the same core tables and nested trigger analogue as atomic-RPC CI.
-- Each stage MUST be called from a separate psql connection (real commits);
-- this SQL function is only ONE stage, NOT a five-stage single transaction.
-- Source rows are copied from prior atomic fixture, which adds SELECT overhead.
-- Not production REST/HTTP, private function bodies, or full role equivalence.
DO $qa$
BEGIN
 IF current_database() <> 'isolated_atomic_scan_qa'
    OR current_user <> 'postgres' THEN
   RAISE EXCEPTION 'QA_ONLY_WRONG_DB_ROLE';
 END IF;
END $qa$;

CREATE TABLE public.qa_fullpath_2x2_latency (
  indexing text NOT NULL,
  architecture text NOT NULL,
  size integer NOT NULL,
  trial integer NOT NULL,
  sql_ms numeric NOT NULL,
  client_wall_ms numeric NOT NULL,
  stage_count integer NOT NULL,
  PRIMARY KEY(indexing,architecture,size,trial)
);

CREATE OR REPLACE FUNCTION public.qa_fullpath_sequential_stage_v01(
  p_indexing text, p_size integer, p_trial integer, p_stage text)
RETURNS jsonb LANGUAGE plpgsql AS $qa$
DECLARE
  source_run text;
  target_run text;
  source_signal_prefix text;
  target_signal_prefix text;
  n integer;
  start_time timestamptz;
  elapsed_ms numeric;
BEGIN
 IF current_database() <> 'isolated_atomic_scan_qa'
    OR current_user <> 'postgres'
    OR p_indexing NOT IN ('baseline','candidate')
    OR p_size NOT IN (30,50,61)
    OR p_trial<1 OR p_trial>20
    OR p_stage NOT IN ('parent','symbols','signals','features','readiness')
 THEN RAISE EXCEPTION 'QA_SEQUENTIAL_BAD_CONTEXT'; END IF;

 source_run:=format('QA_FULLPATH_%s_%s_%s',upper(p_indexing),p_size,p_trial);
 target_run:=format('QA_FULLPATH_SEQ_%s_%s_%s',upper(p_indexing),p_size,p_trial);
 source_signal_prefix:='QAFULL_'||upper(p_indexing)||'_';
 target_signal_prefix:='QAFULL_SEQ_'||upper(p_indexing)||'_';

 -- All SQL is real PostgreSQL DML. Each independent CLI process commits at
 -- statement end, creating a genuine parent-only state if symbol stage fails.
 start_time:=clock_timestamp();
 CASE p_stage
  WHEN 'parent' THEN
   INSERT INTO public.alpha_hunter_snapshots
   SELECT (jsonb_populate_record(NULL::public.alpha_hunter_snapshots,
     to_jsonb(src)||jsonb_build_object('run_id',target_run))).*
   FROM public.alpha_hunter_snapshots src WHERE src.run_id=source_run;
  WHEN 'symbols' THEN
   INSERT INTO public.alpha_hunter_symbol_snapshots
   SELECT (jsonb_populate_record(NULL::public.alpha_hunter_symbol_snapshots,
     to_jsonb(src)||jsonb_build_object('run_id',target_run))).*
   FROM public.alpha_hunter_symbol_snapshots src WHERE src.run_id=source_run;
  WHEN 'signals' THEN
   INSERT INTO public.alpha_hunter_signals
   SELECT (jsonb_populate_record(NULL::public.alpha_hunter_signals,
     to_jsonb(src)||jsonb_build_object(
       'run_id',target_run,
       'signal_id',replace(src.signal_id,source_signal_prefix,target_signal_prefix)
     ))).*
   FROM public.alpha_hunter_signals src WHERE src.run_id=source_run;
  WHEN 'features' THEN
   INSERT INTO public.alpha_hunter_signal_features
   SELECT (jsonb_populate_record(NULL::public.alpha_hunter_signal_features,
     to_jsonb(src)||jsonb_build_object(
       'run_id',target_run,
       'signal_id',replace(src.signal_id,source_signal_prefix,target_signal_prefix)
     ))).*
   FROM public.alpha_hunter_signal_features src WHERE src.run_id=source_run;
  WHEN 'readiness' THEN
   INSERT INTO public.alpha_hunter_readiness_observations_v01
   SELECT (jsonb_populate_record(NULL::public.alpha_hunter_readiness_observations_v01,
     to_jsonb(src)||jsonb_build_object('run_id',target_run))).*
   FROM public.alpha_hunter_readiness_observations_v01 src WHERE src.run_id=source_run;
 END CASE;

 GET DIAGNOSTICS n = ROW_COUNT;
 elapsed_ms:=1000*extract(epoch from clock_timestamp()-start_time);
 IF n<>p_size AND NOT (p_stage='parent' AND n=1) THEN
  RAISE EXCEPTION 'QA_SEQUENTIAL_WRONG_STAGE_COUNT_%_expected_%_actual_%',p_stage,p_size,n;
 END IF;
 RETURN jsonb_build_object(
   'run_id',target_run,'stage',p_stage,'stage_count',n,
   'elapsed_sql_ms',elapsed_ms,'qa_only',true);
END $qa$;

CREATE OR REPLACE FUNCTION public.qa_fullpath_assert_sequential_v01(
  p_indexing text,p_size integer,p_trial integer)
RETURNS void LANGUAGE plpgsql AS $qa$
DECLARE
 rid text;
 size int;
BEGIN
 IF current_database()<>'isolated_atomic_scan_qa' OR current_user<>'postgres'
   OR p_indexing NOT IN('baseline','candidate') OR p_size NOT IN(30,50,61)
 THEN RAISE EXCEPTION 'QA_ASSERT_BAD_CONTEXT'; END IF;
 rid:=format('QA_FULLPATH_SEQ_%s_%s_%s',upper(p_indexing),p_size,p_trial);
 size:=p_size;
 IF (SELECT count(*) FROM public.alpha_hunter_snapshots WHERE run_id=rid)<>1
  OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.alpha_hunter_signals WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.alpha_hunter_signal_features WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.qa_fullpath_strategy_episodes WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.qa_fullpath_strategy_24h_outcome_queue WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.qa_fullpath_strategy_observations WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.qa_fullpath_shadow_quotes WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.qa_fullpath_execution_freezes WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.qa_fullpath_payoff_geometry WHERE run_id=rid)<>size
  OR (SELECT count(*) FROM public.qa_fullpath_calibrated_paper_order WHERE run_id=rid)<>size
 THEN RAISE EXCEPTION 'QA_SEQUENTIAL_INCOMPLETE_%',rid; END IF;
END $qa$;

-- Deliberate fault in one synthetic 30-symbol writer to demonstrate that
-- separate stages are NOT atomic, unlike the candidate RPC. Never production.
CREATE OR REPLACE FUNCTION public.qa_sequential_fail_symbol_stage_v01()
RETURNS trigger LANGUAGE plpgsql AS $qa$
BEGIN
 IF NEW.run_id='QA_FULLPATH_SEQ_FAIL_DEMO' AND NEW.symbol='S030USDT' THEN
  RAISE EXCEPTION USING ERRCODE='57014',MESSAGE='QA_SEQUENCE_INJECTED_57014';
 END IF;
 RETURN NEW;
END $qa$;
CREATE TRIGGER qa_sequential_fail_symbol_stage_v01
AFTER INSERT ON public.alpha_hunter_symbol_snapshots FOR EACH ROW
EXECUTE FUNCTION public.qa_sequential_fail_symbol_stage_v01();
