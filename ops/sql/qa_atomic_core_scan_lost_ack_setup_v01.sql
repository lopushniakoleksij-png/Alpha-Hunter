-- Harada E3: synthetic committed response-lost fixture; ephemeral PG17 only.
DO $qa$ BEGIN
 IF current_database()<>'isolated_atomic_scan_qa' OR current_user<>'postgres' THEN
  RAISE EXCEPTION 'QA_ONLY_WRONG_DATABASE_OR_ROLE';
 END IF;
END $qa$;
INSERT INTO public.qa_atomic_scale_fixtures_v01
(case_name,parent_rows,children_rows,signals_rows,features_rows,readiness_rows)
SELECT 'SIXTY_ONE_LOST_ACK',
 replace(parent_rows::text,'QA_61_TIMEOUT','QA_61_LOST_ACK')::jsonb,
 replace(children_rows::text,'QA_61_TIMEOUT','QA_61_LOST_ACK')::jsonb,
 replace(replace(signals_rows::text,'QA_61_TIMEOUT','QA_61_LOST_ACK'),'QA61_SIGNAL_','QA61_ACK_SIGNAL_')::jsonb,
 replace(replace(features_rows::text,'QA_61_TIMEOUT','QA_61_LOST_ACK'),'QA61_SIGNAL_','QA61_ACK_SIGNAL_')::jsonb,
 replace(readiness_rows::text,'QA_61_TIMEOUT','QA_61_LOST_ACK')::jsonb
FROM public.qa_atomic_scale_fixtures_v01 WHERE case_name='SIXTY_ONE';
