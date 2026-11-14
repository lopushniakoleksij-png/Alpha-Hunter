-- Ephemeral PostgreSQL 17 only. No production access.
-- Verify service_role can actually invoke the security-invoker RPC with RLS
-- enabled and that public/anon/authenticated cannot execute the RPC.
ALTER ROLE service_role BYPASSRLS;
GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, INSERT ON
  public.alpha_hunter_snapshots,
  public.alpha_hunter_symbol_snapshots,
  public.alpha_hunter_signals,
  public.alpha_hunter_signal_features,
  public.alpha_hunter_readiness_observations_v01
TO service_role;
GRANT INSERT ON public.qa_atomic_trigger_events TO service_role;
GRANT USAGE ON SEQUENCE public.qa_atomic_trigger_events_event_id_seq TO service_role;

ALTER TABLE public.alpha_hunter_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alpha_hunter_symbol_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alpha_hunter_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alpha_hunter_signal_features ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alpha_hunter_readiness_observations_v01 ENABLE ROW LEVEL SECURITY;

DO $guard$
BEGIN
  IF has_function_privilege('anon',
    'public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)','EXECUTE')
    OR has_function_privilege('authenticated',
    'public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)','EXECUTE')
    OR NOT has_function_privilege('service_role',
    'public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)','EXECUTE')
  THEN
    RAISE EXCEPTION 'UNSAFE_RPC_EXECUTE_GRANTS';
  END IF;
END $guard$;

SET ROLE service_role;
DO $service_role_qa$
DECLARE
  v_receipt jsonb;
BEGIN
  v_receipt := public.alpha_hunter_commit_core_scan_v01(
    '[{"run_id":"QA_SERVICE_ROLE","collected_at_utc":"2026-11-07T08:00:00Z","version":"qa","product_type":"usdt-futures","symbol_count":1,"error_count":0,"payload":{"source":"SERVICE_ROLE_QA"}}]'::jsonb,
    '[{"run_id":"QA_SERVICE_ROLE","symbol":"QAUSDT","collected_at_utc":"2026-11-07T08:00:00Z","state":"WATCH","trade_permission":false,"state_changed":false,"payload":{"symbol":"QAUSDT"}}]'::jsonb,
    '[{"run_id":"QA_SERVICE_ROLE","signal_id":"QA_SERVICE_ROLE_SIGNAL","symbol":"QAUSDT","detected_at_utc":"2026-11-07T08:00:00Z","trade_permission":false,"reference_price":1,"payload":{"symbol":"QAUSDT"}}]'::jsonb,
    '[{"run_id":"QA_SERVICE_ROLE","signal_id":"QA_SERVICE_ROLE_SIGNAL","symbol":"QAUSDT","captured_at_utc":"2026-11-07T08:00:00Z","trade_permission":false,"features":{},"source_payload":{}}]'::jsonb,
    '[{"run_id":"QA_SERVICE_ROLE","symbol":"QAUSDT","observed_at_utc":"2026-11-07T08:00:00Z","trade_permission":false,"v7_trade_ready":false}]'::jsonb
  );
  IF v_receipt->>'committed' <> 'true'
    OR v_receipt->>'symbol_count'<>'1'
    OR v_receipt->>'readiness_count'<>'1'
  THEN
    RAISE EXCEPTION 'SERVICE_ROLE_INVOKER_RECEIPT_MISMATCH %',v_receipt;
  END IF;
  RAISE NOTICE 'PASS: simulated service_role with RLS enabled committed and verified five core tables';
END $service_role_qa$;
RESET ROLE;
DO $finalcheck$
BEGIN
  IF (SELECT COUNT(*) FROM public.alpha_hunter_snapshots WHERE run_id='QA_SERVICE_ROLE') <> 1
  OR (SELECT COUNT(*) FROM public.alpha_hunter_symbol_snapshots WHERE run_id='QA_SERVICE_ROLE') <> 1
  OR (SELECT COUNT(*) FROM public.alpha_hunter_signals WHERE run_id='QA_SERVICE_ROLE') <> 1
  OR (SELECT COUNT(*) FROM public.alpha_hunter_signal_features WHERE run_id='QA_SERVICE_ROLE') <> 1
  OR (SELECT COUNT(*) FROM public.alpha_hunter_readiness_observations_v01 WHERE run_id='QA_SERVICE_ROLE') <> 1
  THEN
     RAISE EXCEPTION 'SERVICE_ROLE_PERSISTENCE_INCOMPLETE';
  END IF;
  RAISE NOTICE 'PASS: service_role physical evidence counts exact; anon/authenticated lack RPC execution';
END $finalcheck$;
