-- P0 Harada D7 / E1: ephemeral-only real PostgreSQL statement_timeout fixture.
-- MUST be executed only in CI's disposable isolated_atomic_scan_qa database.
-- This is NOT a production-equivalent private trigger graph or full workload.
-- Requires qa_atomic_core_scan_30_61_timeout_v01.sql to have populated fixtures.
DO $qa$
BEGIN
  IF current_database() <> 'isolated_atomic_scan_qa'
     OR current_user <> 'postgres' THEN
    RAISE EXCEPTION 'QA_ONLY_WRONG_DATABASE_OR_ROLE';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.qa_atomic_scale_fixtures_v01
                 WHERE case_name='SIXTY_ONE') THEN
    RAISE EXCEPTION 'QA61_BASE_FIXTURE_MISSING';
  END IF;
END
$qa$;

INSERT INTO public.qa_atomic_scale_fixtures_v01
  (case_name,parent_rows,children_rows,signals_rows,features_rows,readiness_rows)
SELECT
  'SIXTY_ONE_REAL_TIMEOUT',
  replace(parent_rows::text,'QA_61_TIMEOUT','QA_61_REAL_TIMEOUT')::jsonb,
  replace(children_rows::text,'QA_61_TIMEOUT','QA_61_REAL_TIMEOUT')::jsonb,
  replace(replace(signals_rows::text,'QA_61_TIMEOUT','QA_61_REAL_TIMEOUT'),
          'QA61_SIGNAL_','QA61_REAL_SIGNAL_')::jsonb,
  replace(replace(features_rows::text,'QA_61_TIMEOUT','QA_61_REAL_TIMEOUT'),
          'QA61_SIGNAL_','QA61_REAL_SIGNAL_')::jsonb,
  replace(readiness_rows::text,'QA_61_TIMEOUT','QA_61_REAL_TIMEOUT')::jsonb
FROM public.qa_atomic_scale_fixtures_v01
WHERE case_name='SIXTY_ONE';

-- A real sleep in a nested AFTER INSERT trigger will consume statement time.
-- Time budget is enforced by PostgreSQL itself, NOT RAISE SQLSTATE 57014.
CREATE OR REPLACE FUNCTION public.qa_nested_real_timeout_v01()
RETURNS trigger LANGUAGE plpgsql AS $trigger$
BEGIN
  IF new.run_id='QA_61_REAL_TIMEOUT' AND new.symbol='T061USDT' THEN
    PERFORM pg_catalog.pg_sleep(0.6);
  END IF;
  RETURN new;
END
$trigger$;
CREATE TRIGGER qa_nested_real_timeout_v01
AFTER INSERT ON public.alpha_hunter_symbol_snapshots
FOR EACH ROW EXECUTE FUNCTION public.qa_nested_real_timeout_v01();
