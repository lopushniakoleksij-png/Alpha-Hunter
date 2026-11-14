-- Alpha Hunter P0 — isolated PG17 four-way matrix verification.
-- Same synthetic 505,569-row outcome fixture and simulated trigger topology.
-- Does NOT certify real production private function bodies/latency.
DO $qa$
DECLARE
  ix text;
  scan_size int;
  n int;
  type_count int;
  differences int;
BEGIN
 IF current_database()<>'isolated_atomic_scan_qa' OR current_user<>'postgres' THEN
  RAISE EXCEPTION 'QA_ONLY_WRONG_DB_OR_ROLE';
 END IF;
 SELECT count(*) INTO type_count FROM public.qa_fullpath_2x2_latency;
 IF type_count<>240 THEN
  RAISE EXCEPTION 'QA_2X2_MISSING_MATRIX_ROWS: %',type_count;
 END IF;
 FOREACH ix IN ARRAY ARRAY['baseline','candidate'] LOOP
  FOREACH scan_size IN ARRAY ARRAY[30,50,61] LOOP
   FOREACH n IN ARRAY ARRAY[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20] LOOP
    IF (SELECT count(*) FROM public.qa_fullpath_2x2_latency
        WHERE indexing=ix AND size=scan_size AND trial=n
        AND architecture IN ('atomic','sequential'))<>2
    THEN RAISE EXCEPTION 'QA_2X2_MISSING_PAIR_%_%_%',ix,scan_size,n; END IF;
    -- Each sequential publication is verified from an independent committed
    -- caller by Python, then compare all synthetic payoff geometry fields.
    SELECT count(*) INTO differences
    FROM public.qa_fullpath_payoff_geometry a
    FULL JOIN public.qa_fullpath_payoff_geometry s
       ON s.symbol=a.symbol
      AND s.run_id=format('QA_FULLPATH_SEQ_%s_%s_%s',upper(ix),scan_size,n)
    WHERE a.run_id=format('QA_FULLPATH_%s_%s_%s',upper(ix),scan_size,n)
      AND (s.symbol IS NULL
       OR a.strategy_id IS DISTINCT FROM s.strategy_id
       OR a.direction IS DISTINCT FROM s.direction
       OR a.matched_rows IS DISTINCT FROM s.matched_rows
       OR a.adverse_p50 IS DISTINCT FROM s.adverse_p50
       OR a.adverse_p75 IS DISTINCT FROM s.adverse_p75
       OR a.favorable_p50 IS DISTINCT FROM s.favorable_p50
       OR a.favorable_p90 IS DISTINCT FROM s.favorable_p90);
    IF differences<>0 THEN
      RAISE EXCEPTION 'QA_2X2_SCIENTIFIC_PARITY_FAILED_%_%_%',ix,scan_size,n;
    END IF;
   END LOOP;
  END LOOP;
 END LOOP;
 IF (SELECT count(*) FROM public.alpha_hunter_snapshots
       WHERE run_id='QA_FULLPATH_SEQ_FAIL_DEMO')<>1
    OR (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots
       WHERE run_id='QA_FULLPATH_SEQ_FAIL_DEMO')<>0
 THEN RAISE EXCEPTION 'QA_2X2_INJECTED_PARTIAL_PARENT_NOT_RETAINED'; END IF;
 RAISE NOTICE 'PASS: 2x2 matrix 240 points across 30/50/61, exact synthetic percentile parity for 120 sequential-vs-atomic pairs';
 RAISE NOTICE 'PASS: sequential staged commit retained parent but zero children after injected failed stage';
END $qa$;

SELECT architecture,indexing,size,count(*) n,
 round(percentile_cont(0.50) WITHIN GROUP(ORDER BY sql_ms)::numeric,2) p50_sql_ms,
 round(percentile_cont(0.95) WITHIN GROUP(ORDER BY sql_ms)::numeric,2) p95_sql_ms,
 round(percentile_cont(0.99) WITHIN GROUP(ORDER BY sql_ms)::numeric,2) p99_sql_ms,
 round(max(sql_ms)::numeric,2) max_sql_ms
FROM public.qa_fullpath_2x2_latency
GROUP BY architecture,indexing,size
ORDER BY architecture,indexing,size;
