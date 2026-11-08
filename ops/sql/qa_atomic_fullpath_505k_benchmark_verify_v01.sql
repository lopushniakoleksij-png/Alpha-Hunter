-- Harada P0 / C6-C7: disposable PostgreSQL17 benchmark verification ONLY.
-- No source bodies, production data or actual exchange order effects.
DO $qa$
DECLARE
 s integer;
 n0 integer;
 n1 integer;
 n2 integer;
BEGIN
 IF current_database()<>'isolated_atomic_scan_qa'
    OR current_user<>'postgres'
    OR (SELECT count(*) FROM public.alpha_hunter_strategy_forward_outcomes_v01)<>505569
 THEN RAISE EXCEPTION 'QA_FULLPATH_WRONG_DB_ROLE_OR_OUTCOME_SCALE'; END IF;
 FOREACH s IN ARRAY ARRAY[30,50,61]
 LOOP
  SELECT count(*) INTO n0 FROM public.qa_fullpath_request_latency
   WHERE phase='baseline' AND size=s;
  SELECT count(*) INTO n1 FROM public.qa_fullpath_request_latency
   WHERE phase='candidate' AND size=s;
  IF n0<>20 OR n1<>20 THEN
    RAISE EXCEPTION 'QA_FULLPATH_INSUFFICIENT_SAMPLE_BASELINE_%_CANDIDATE_%_SIZE_%',
                    n0,n1,s;
  END IF;
  IF EXISTS (
   SELECT 1
   FROM public.qa_fullpath_payoff_geometry baseline
   JOIN public.qa_fullpath_payoff_geometry candidate
     ON baseline.symbol=candidate.symbol
   WHERE baseline.run_id=format('QA_FULLPATH_BASELINE_%s_1',s)
     AND candidate.run_id=format('QA_FULLPATH_CANDIDATE_%s_1',s)
     AND (
        baseline.strategy_id IS DISTINCT FROM candidate.strategy_id
     OR baseline.direction IS DISTINCT FROM candidate.direction
     OR baseline.matched_rows IS DISTINCT FROM candidate.matched_rows
     OR baseline.adverse_p50 IS DISTINCT FROM candidate.adverse_p50
     OR baseline.adverse_p75 IS DISTINCT FROM candidate.adverse_p75
     OR baseline.favorable_p50 IS DISTINCT FROM candidate.favorable_p50
     OR baseline.favorable_p90 IS DISTINCT FROM candidate.favorable_p90
     )
  ) THEN
    RAISE EXCEPTION 'QA_FULLPATH_INDEX_CHANGED_SCIENTIFIC_PERCENTILES_SIZE_%',s;
  END IF;
  IF (SELECT count(*) FROM public.qa_fullpath_strategy_episodes
       WHERE run_id=format('QA_FULLPATH_BASELINE_%s_1',s))<>s
     OR (SELECT count(*) FROM public.qa_fullpath_strategy_24h_outcome_queue
       WHERE run_id=format('QA_FULLPATH_BASELINE_%s_1',s))<>s
     OR (SELECT count(*) FROM public.qa_fullpath_strategy_episodes
       WHERE run_id=format('QA_FULLPATH_CANDIDATE_%s_1',s))<>s
     OR (SELECT count(*) FROM public.qa_fullpath_strategy_24h_outcome_queue
       WHERE run_id=format('QA_FULLPATH_CANDIDATE_%s_1',s))<>s
     OR (SELECT count(*) FROM public.qa_fullpath_payoff_geometry
       WHERE run_id=format('QA_FULLPATH_BASELINE_%s_1',s))<>s
     OR (SELECT count(*) FROM public.qa_fullpath_payoff_geometry
       WHERE run_id=format('QA_FULLPATH_CANDIDATE_%s_1',s))<>s
  THEN RAISE EXCEPTION 'QA_FULLPATH_SCIENTIFIC_ROW_MISMATCH_SIZE_%',s;
  END IF;
 END LOOP;
 SELECT count(*) INTO n2 FROM public.qa_fullpath_request_latency
 WHERE phase='candidate_concurrent' AND size=61;
 IF n2<>6 THEN RAISE EXCEPTION 'QA_FULLPATH_CONCURRENT_SAMPLE_MISSING_%',n2; END IF;

 RAISE NOTICE 'PASS: 505569 synthetic outcomes, all baseline/candidate 20-run 30/50/61 RPC cohorts, six concurrent 61s';
 RAISE NOTICE 'PASS: synthetic historical percentiles unchanged by index, all seven synthetic nested chain side-effect families persisted exactly';
END $qa$;

-- Purely descriptive synthetic latency distribution, not production SLA.
SELECT phase,size,count(*) samples,
 round((percentile_cont(0.50) WITHIN GROUP(ORDER BY elapsed_ms))::numeric,2) p50_ms,
 round((percentile_cont(0.95) WITHIN GROUP(ORDER BY elapsed_ms))::numeric,2) p95_ms,
 round((percentile_cont(0.99) WITHIN GROUP(ORDER BY elapsed_ms))::numeric,2) p99_ms,
 round(max(elapsed_ms)::numeric,2) max_ms,
 count(*) FILTER (WHERE elapsed_ms>=12000) over_12_seconds
FROM public.qa_fullpath_request_latency
GROUP BY phase,size ORDER BY phase,size;
