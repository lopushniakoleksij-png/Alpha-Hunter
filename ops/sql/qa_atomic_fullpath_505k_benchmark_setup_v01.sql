-- Alpha Hunter P0 / Harada C6-C7: disposable PostgreSQL 17 ONLY.
-- SYNTHETIC STRUCTURAL ANALOGUE of the live synchronous symbol trigger chain.
-- It does NOT contain, reconstruct, or certify private production function bodies.
-- Approximate scale: 505,569 historical outcomes (verified production count
-- as of 2026-11-08 13:20 UTC). No real exchange orders or live paper records.
-- Run ONLY via guarded GitHub Actions job, after the existing 495k synthetic
-- payoff benchmark installed its candidate index. A/B comparisons are measured
-- in distinct SQL transactions per scan by the guarded Python driver.

DO $safe$
BEGIN
 IF current_database() <> 'isolated_atomic_scan_qa'
    OR current_user <> 'postgres'
    OR (SELECT count(*) FROM public.alpha_hunter_strategy_forward_outcomes_v01)<>495000
 THEN
  RAISE EXCEPTION 'QA_ONLY_WRONG_DATABASE_ROLE_OR_MISSING_495K_BASELINE';
 END IF;
END $safe$;

INSERT INTO public.alpha_hunter_strategy_forward_outcomes_v01(
 episode_id,horizon_hours,first_observed_at_utc,strategy_id,direction,
 entry_trigger_status,path_measurement_quality,ordering_ambiguous,
 evaluated_at_utc,max_adverse_excursion_pct,max_favorable_excursion_pct
)
SELECT 'qa-'||n,
 CASE WHEN n%5=0 THEN 4 ELSE 24 END,
 timestamptz '2026-09-01T00:00:00+00' + (n%220000)*interval '1 second',
 (array['S1','S2','S3','S4','S5','S6'])[(n%6)+1],
 CASE WHEN (n/6)%2=0 THEN 'LONG' ELSE 'SHORT' END,
 CASE WHEN n%7=0 THEN 'NEVER_TRIGGERED'
      WHEN n%3=0 THEN 'TRIGGERED_LIMIT' ELSE 'TRIGGERED_EXECUTE_NOW' END,
 CASE WHEN n%13=0 THEN 'INCOMPLETE' ELSE 'COMPLETE_ENOUGH' END,
 n%17=0,
 timestamptz '2026-11-01T00:00:00+00' + (n%500000)*interval '1 second',
 (n%450)::float8/100.,
 (n%900)::float8/100.
FROM generate_series(495001,505569) g(n);

ANALYZE public.alpha_hunter_strategy_forward_outcomes_v01;

CREATE TABLE public.qa_fullpath_strategy_observations (
 run_id text NOT NULL,symbol text NOT NULL,
 PRIMARY KEY(run_id,symbol)
);
CREATE TABLE public.qa_fullpath_shadow_quotes (
 run_id text NOT NULL,symbol text NOT NULL,
 PRIMARY KEY(run_id,symbol)
);
CREATE TABLE public.qa_fullpath_execution_freezes (
 run_id text NOT NULL,symbol text NOT NULL,
 PRIMARY KEY(run_id,symbol)
);
CREATE TABLE public.qa_fullpath_payoff_geometry (
 run_id text NOT NULL,symbol text NOT NULL,
 strategy_id text NOT NULL,direction text NOT NULL, matched_rows int NOT NULL,
 adverse_p50 double precision, adverse_p75 double precision,
 favorable_p50 double precision,favorable_p90 double precision,
 PRIMARY KEY(run_id,symbol)
);
CREATE TABLE public.qa_fullpath_calibrated_paper_order (
 run_id text NOT NULL,symbol text NOT NULL,
 simulated_only boolean NOT NULL DEFAULT true,
 PRIMARY KEY(run_id,symbol),
 CHECK(simulated_only)
);
CREATE TABLE public.qa_fullpath_cost_floor (
 strategy_id text NOT NULL,direction text NOT NULL,
 synthetic_cost_floor numeric NOT NULL,
 PRIMARY KEY(strategy_id,direction)
);
INSERT INTO public.qa_fullpath_cost_floor VALUES
 ('S3','LONG',0.001),('S6','LONG',0.001),('S1','SHORT',0.001);

CREATE TABLE public.qa_fullpath_request_latency (
 phase text NOT NULL, size int NOT NULL,trial int NOT NULL,
 elapsed_ms numeric NOT NULL,
 matched_505k_rows int NOT NULL,
 PRIMARY KEY(phase,size,trial)
);

-- All mock side effects have QA-only names and synthetic rows; not live trading.
CREATE FUNCTION public.qa_fullpath_symbol_to_strategy()
RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
 IF NEW.run_id LIKE 'QA_FULLPATH_%' THEN
   INSERT INTO public.qa_fullpath_strategy_observations VALUES(NEW.run_id,NEW.symbol);
 END IF;
 RETURN NEW;
END $f$;
CREATE TRIGGER qa_fullpath_symbol_capture AFTER INSERT
ON public.alpha_hunter_symbol_snapshots FOR EACH ROW
EXECUTE FUNCTION public.qa_fullpath_symbol_to_strategy();

CREATE FUNCTION public.qa_fullpath_strategy_to_quote()
RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
 INSERT INTO public.qa_fullpath_shadow_quotes VALUES(NEW.run_id,NEW.symbol);
 RETURN NEW;
END $f$;
CREATE TRIGGER qa_fullpath_quote_capture AFTER INSERT
ON public.qa_fullpath_strategy_observations FOR EACH ROW
EXECUTE FUNCTION public.qa_fullpath_strategy_to_quote();

CREATE FUNCTION public.qa_fullpath_quote_to_freeze()
RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
 INSERT INTO public.qa_fullpath_execution_freezes VALUES(NEW.run_id,NEW.symbol);
 RETURN NEW;
END $f$;
CREATE TRIGGER qa_fullpath_freeze_capture AFTER INSERT
ON public.qa_fullpath_shadow_quotes FOR EACH ROW
EXECUTE FUNCTION public.qa_fullpath_quote_to_freeze();

CREATE FUNCTION public.qa_fullpath_freeze_to_calibrated_order()
RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
 INSERT INTO public.qa_fullpath_calibrated_paper_order(run_id,symbol,simulated_only)
 VALUES(NEW.run_id,NEW.symbol,true);
 RETURN NEW;
END $f$;
CREATE TRIGGER qa_fullpath_calibrated_order AFTER INSERT
ON public.qa_fullpath_execution_freezes FOR EACH ROW
EXECUTE FUNCTION public.qa_fullpath_freeze_to_calibrated_order();

CREATE FUNCTION public.qa_fullpath_freeze_to_payoff_geometry()
RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE
 v_strategy text;
 v_direction text;
 v_count int;
 v_adverse50 double precision;
 v_adverse75 double precision;
 v_favorable50 double precision;
 v_favorable90 double precision;
 v_floor numeric;
BEGIN
 CASE (substring(NEW.symbol from 2 for 3)::int % 3)
  WHEN 0 THEN v_strategy:='S3'; v_direction:='LONG';
  WHEN 1 THEN v_strategy:='S6'; v_direction:='LONG';
  ELSE v_strategy:='S1'; v_direction:='SHORT';
 END CASE;

 -- The mathematical percentile shape and filter classes match the
 -- discovered nested hot path, NOT exact private stored procedure logic.
 SELECT count(*)::int,
   percentile_cont(0.5) WITHIN GROUP(ORDER BY o.max_adverse_excursion_pct),
   percentile_cont(0.75) WITHIN GROUP(ORDER BY o.max_adverse_excursion_pct),
   percentile_cont(0.5) WITHIN GROUP(ORDER BY o.max_favorable_excursion_pct),
   percentile_cont(0.90) WITHIN GROUP(ORDER BY o.max_favorable_excursion_pct)
 INTO v_count,v_adverse50,v_adverse75,v_favorable50,v_favorable90
 FROM public.alpha_hunter_strategy_forward_outcomes_v01 o
 WHERE o.horizon_hours=24
   AND o.strategy_id=v_strategy
   AND o.direction=v_direction
   AND o.entry_trigger_status IN ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
   AND o.path_measurement_quality='COMPLETE_ENOUGH'
   AND o.ordering_ambiguous=false
   AND o.evaluated_at_utc<=timestamptz '2026-11-07T07:00:00Z'
   AND o.max_adverse_excursion_pct IS NOT NULL
   AND o.max_favorable_excursion_pct IS NOT NULL;

 SELECT synthetic_cost_floor INTO STRICT v_floor
 FROM public.qa_fullpath_cost_floor
 WHERE strategy_id=v_strategy AND direction=v_direction;

 IF v_count=0 OR v_floor IS NULL THEN
  RAISE EXCEPTION 'QA_FULLPATH_EMPTY_HISTORICAL_OR_MISSING_COST_FLOOR';
 END IF;

 INSERT INTO public.qa_fullpath_payoff_geometry
 VALUES(NEW.run_id,NEW.symbol,v_strategy,v_direction,v_count,
        v_adverse50,v_adverse75,v_favorable50,v_favorable90);
 RETURN NEW;
END $f$;
CREATE TRIGGER qa_fullpath_payoff_geometry AFTER INSERT
ON public.qa_fullpath_execution_freezes FOR EACH ROW
EXECUTE FUNCTION public.qa_fullpath_freeze_to_payoff_geometry();

-- Generates source-accurate 30/50/61 core rows with real RPC behavior.
-- Each SELECT from the CLI is a new independent PostgreSQL transaction.
CREATE FUNCTION public.qa_fullpath_run(p_phase text,p_size int,p_trial int)
RETURNS jsonb LANGUAGE plpgsql AS $f$
DECLARE
 rid text;
 p_parent jsonb;
 p_child jsonb;
 p_signal jsonb;
 p_feature jsonb;
 p_ready jsonb;
 receipt jsonb;
 started timestamptz;
 elapsed numeric;
 matches int;
BEGIN
 IF p_phase NOT IN ('baseline','candidate','candidate_concurrent')
    OR p_size NOT IN (30,50,61)
    OR p_trial < 1 OR p_trial > 200 THEN
   RAISE EXCEPTION 'QA_FULLPATH_BAD_TEST_PARAMS';
 END IF;
 rid:=format('QA_FULLPATH_%s_%s_%s',upper(p_phase),p_size,p_trial);
 p_parent:=jsonb_build_array(jsonb_build_object(
   'run_id',rid,'collected_at_utc','2026-11-08T12:00:00Z',
   'version','QA_FULLPATH_SYNTHETIC','product_type','usdt-futures',
   'symbol_count',p_size,'error_count',0,
   'payload',jsonb_build_object('qa','private-functions-not-reproduced')));
 SELECT jsonb_agg(jsonb_build_object(
     'run_id',rid,'symbol',format('S%sUSDT',lpad(n::text,3,'0')),
     'collected_at_utc','2026-11-08T12:00:00Z',
     'trade_permission',false,'state_changed',false,'state','WATCH',
     'payload',jsonb_build_object('qa','fullpath','ordinal',n)) ORDER BY n)
 INTO p_child FROM generate_series(1,p_size) n;
 SELECT jsonb_agg(jsonb_build_object(
     'run_id',rid,'signal_id',format('QAFULL_%s_%s_%s',upper(p_phase),p_trial,n),
     'symbol',format('S%sUSDT',lpad(n::text,3,'0')),
     'detected_at_utc','2026-11-08T12:00:00Z',
     'reference_price',100+n,'trade_permission',false,
     'payload',jsonb_build_object('qa','fullpath')) ORDER BY n)
 INTO p_signal FROM generate_series(1,p_size) n;
 SELECT jsonb_agg(jsonb_build_object(
     'run_id',rid,'signal_id',format('QAFULL_%s_%s_%s',upper(p_phase),p_trial,n),
     'symbol',format('S%sUSDT',lpad(n::text,3,'0')),
     'captured_at_utc','2026-11-08T12:00:00Z',
     'trade_permission',false,'features','{}'::jsonb,
     'source_payload',jsonb_build_object('qa','fullpath')) ORDER BY n)
 INTO p_feature FROM generate_series(1,p_size) n;
 SELECT jsonb_agg(jsonb_build_object(
     'run_id',rid,'symbol',format('S%sUSDT',lpad(n::text,3,'0')),
     'observed_at_utc','2026-11-08T12:00:00Z',
     'trade_permission',false,'v7_trade_ready',false) ORDER BY n)
 INTO p_ready FROM generate_series(1,p_size) n;
 started:=clock_timestamp();
 receipt:=public.alpha_hunter_commit_core_scan_v01(
   p_parent,p_child,p_signal,p_feature,p_ready);
 elapsed:=1000*extract(epoch from clock_timestamp()-started);
 IF receipt->>'committed'<>'true'
    OR (receipt->>'symbol_count')::int<>p_size
    OR (receipt->>'signal_count')::int<>p_size
    OR (receipt->>'feature_count')::int<>p_size
    OR (receipt->>'readiness_count')::int<>p_size
    OR (SELECT count(*) FROM public.qa_fullpath_strategy_observations WHERE run_id=rid)<>p_size
    OR (SELECT count(*) FROM public.qa_fullpath_shadow_quotes WHERE run_id=rid)<>p_size
    OR (SELECT count(*) FROM public.qa_fullpath_execution_freezes WHERE run_id=rid)<>p_size
    OR (SELECT count(*) FROM public.qa_fullpath_payoff_geometry WHERE run_id=rid)<>p_size
    OR (SELECT count(*) FROM public.qa_fullpath_calibrated_paper_order WHERE run_id=rid)<>p_size
 THEN RAISE EXCEPTION 'QA_FULLPATH_INCOMPLETE_OR_INCONSISTENT_%',rid; END IF;
 SELECT sum(matched_rows)::int INTO matches
 FROM public.qa_fullpath_payoff_geometry WHERE run_id=rid;
 INSERT INTO public.qa_fullpath_request_latency
 VALUES(p_phase,p_size,p_trial,elapsed,matches);
 RETURN jsonb_build_object('run_id',rid,'committed',true,'elapsed_ms',elapsed,
          'symbols',p_size,'historical_rows_sum',matches,'qa_only',true);
END $f$;
