-- Alpha Hunter / Harada E6: synthetic concurrent writers, ephemeral PG17 only.
-- Never execute on production. 2 run IDs and controlled nested trigger delay.
DO $qa$
BEGIN
  IF current_database()<>'isolated_atomic_scan_qa' OR current_user<>'postgres' THEN
    RAISE EXCEPTION 'QA_ONLY_WRONG_DATABASE_OR_ROLE';
  END IF;
END $qa$;

INSERT INTO public.qa_atomic_scale_fixtures_v01
  (case_name,parent_rows,children_rows,signals_rows,features_rows,readiness_rows)
SELECT case_name,
  replace(parent_rows::text,'QA_61_TIMEOUT',run_id)::jsonb,
  replace(children_rows::text,'QA_61_TIMEOUT',run_id)::jsonb,
  replace(replace(signals_rows::text,'QA_61_TIMEOUT',run_id),
    'QA61_SIGNAL_',signal_prefix)::jsonb,
  replace(replace(features_rows::text,'QA_61_TIMEOUT',run_id),
    'QA61_SIGNAL_',signal_prefix)::jsonb,
  replace(readiness_rows::text,'QA_61_TIMEOUT',run_id)::jsonb
FROM public.qa_atomic_scale_fixtures_v01 seed
CROSS JOIN (VALUES
  ('SIXTY_ONE_CONCURRENT','QA_61_CONCURRENT','QA61_CONCUR_SIGNAL_'),
  ('SIXTY_ONE_CONFLICT','QA_61_RACE_CONFLICT','QA61_RACE_SIGNAL_')
) AS v(case_name,run_id,signal_prefix)
WHERE seed.case_name='SIXTY_ONE';

-- The first transaction stalls *inside the actual RPC*, after it acquires
-- the per-run advisory lock. The other concurrent caller must WAIT for it.
CREATE OR REPLACE FUNCTION public.qa_concurrent_nested_delay_v01()
RETURNS trigger LANGUAGE plpgsql AS $qa$
BEGIN
  IF NEW.run_id IN ('QA_61_CONCURRENT','QA_61_RACE_CONFLICT')
     AND NEW.symbol='T001USDT' THEN
    PERFORM pg_catalog.pg_sleep(3);
  END IF;
  RETURN NEW;
END $qa$;
CREATE TRIGGER qa_concurrent_nested_delay_v01
AFTER INSERT ON public.alpha_hunter_symbol_snapshots
FOR EACH ROW EXECUTE FUNCTION public.qa_concurrent_nested_delay_v01();
