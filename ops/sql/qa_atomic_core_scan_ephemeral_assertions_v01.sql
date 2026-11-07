-- Isolated PostgreSQL 17 acceptance fixture. DO NOT RUN IN PRODUCTION.
-- Uses synthetic data, simulated triggers and zero external services.
create temporary table qa_scan_payload (
  parent jsonb not null, children jsonb not null, signals jsonb not null,
  features jsonb not null, readiness jsonb not null
);
insert into qa_scan_payload(parent,children,signals,features,readiness) values (
  '[{"run_id":"QA_ATOMIC_SCAN_01","collected_at_utc":"2026-11-07T08:00:00Z","version":"qa","product_type":"usdt-futures","symbol_count":2,"error_count":0,"payload":{"source":"ISOLATED_QA"}}]'::jsonb,
  '[{"run_id":"QA_ATOMIC_SCAN_01","symbol":"BTCUSDT","collected_at_utc":"2026-11-07T08:00:00Z","state":"WATCH","trade_permission":false,"state_changed":false,"payload":{"symbol":"BTCUSDT"}},
    {"run_id":"QA_ATOMIC_SCAN_01","symbol":"ETHUSDT","collected_at_utc":"2026-11-07T08:00:00Z","state":"WATCH","trade_permission":false,"state_changed":false,"payload":{"symbol":"ETHUSDT"}}]'::jsonb,
  '[{"run_id":"QA_ATOMIC_SCAN_01","signal_id":"QA_SIGNAL_BTC","symbol":"BTCUSDT","detected_at_utc":"2026-11-07T08:00:00Z","trade_permission":false,"reference_price":70000,"payload":{"symbol":"BTCUSDT"}}]'::jsonb,
  '[{"run_id":"QA_ATOMIC_SCAN_01","signal_id":"QA_SIGNAL_BTC","symbol":"BTCUSDT","captured_at_utc":"2026-11-07T08:00:00Z","trade_permission":false,"features":{},"source_payload":{}}]'::jsonb,
  '[{"run_id":"QA_ATOMIC_SCAN_01","symbol":"BTCUSDT","observed_at_utc":"2026-11-07T08:00:00Z","trade_permission":false,"v7_trade_ready":false},
    {"run_id":"QA_ATOMIC_SCAN_01","symbol":"ETHUSDT","observed_at_utc":"2026-11-07T08:00:00Z","trade_permission":false,"v7_trade_ready":false}]'::jsonb
);
do $test$
declare
  p qa_scan_payload%rowtype;
  receipt jsonb;
  bad_readiness jsonb;
  bad_parent jsonb;
  before_events integer;
  after_events integer;
  label text;
begin
  select * into p from qa_scan_payload limit 1;
  -- Fail second child after the parent and first child have inserted.
  perform pg_catalog.set_config('qa.fail_symbol','on',true);
  begin
    perform public.alpha_hunter_commit_core_scan_v01(
      p.parent,p.children,p.signals,p.features,p.readiness
    );
    raise exception 'EXPECTED_INJECTED_SYMBOL_FAILURE_MISSING';
  exception when others then
    if sqlerrm not like '%INJECTED_SYMBOL_TRIGGER_TIMEOUT%' then raise; end if;
  end;
  perform pg_catalog.set_config('qa.fail_symbol','off',true);
  if (select count(*) from public.alpha_hunter_snapshots)<>0
      or (select count(*) from public.alpha_hunter_symbol_snapshots)<>0
      or (select count(*) from public.qa_atomic_trigger_events)<>0 then
    raise exception 'ROLLBACK_FAILURE: first injected trigger failure left rows';
  end if;
  raise notice 'PASS: symbol trigger rollback of parent, child, and side effects';

  -- Fail downstream feature after the parent, both children and signal.
  perform pg_catalog.set_config('qa.fail_feature','on',true);
  begin
    perform public.alpha_hunter_commit_core_scan_v01(
      p.parent,p.children,p.signals,p.features,p.readiness
    );
    raise exception 'EXPECTED_INJECTED_FEATURE_FAILURE_MISSING';
  exception when others then
    if sqlerrm not like '%INJECTED_FEATURE_TRIGGER_FAILURE%' then raise; end if;
  end;
  perform pg_catalog.set_config('qa.fail_feature','off',true);
  if (select count(*) from public.alpha_hunter_snapshots)<>0
     or (select count(*) from public.alpha_hunter_symbol_snapshots)<>0
     or (select count(*) from public.alpha_hunter_signals)<>0
     or (select count(*) from public.alpha_hunter_signal_features)<>0
     or (select count(*) from public.alpha_hunter_readiness_observations_v01)<>0
     or (select count(*) from public.qa_atomic_trigger_events)<>0 then
    raise exception 'ROLLBACK_FAILURE: downstream trigger failure left rows';
  end if;
  raise notice 'PASS: downstream trigger rollback of all evidence and side effects';

  -- Successful core snapshot: exact full-count confirmation.
  receipt:=public.alpha_hunter_commit_core_scan_v01(
    p.parent,p.children,p.signals,p.features,p.readiness
  );
  if receipt->>'committed' <> 'true'
     or receipt->>'parent_count'<>'1'
     or receipt->>'symbol_count'<>'2'
     or receipt->>'signal_count'<>'1'
     or receipt->>'feature_count'<>'1'
     or receipt->>'readiness_count'<>'2'
     or (select count(*) from public.qa_atomic_trigger_events)<>7 then
    raise exception 'SUCCESS_COUNT_MISMATCH: %',receipt;
  end if;
  raise notice 'PASS: all five core families and synthetic trigger events committed';
  select count(*) into before_events from public.qa_atomic_trigger_events;

  -- Safe replay: identical duplicate evidence must not fire INSERT or UPDATE triggers.
  receipt:=public.alpha_hunter_commit_core_scan_v01(
    p.parent,p.children,p.signals,p.features,p.readiness
  );
  select count(*) into after_events from public.qa_atomic_trigger_events;
  if after_events<>before_events
     or receipt->>'symbol_count'<>'2'
     or receipt->>'readiness_count'<>'2' then
    raise exception 'RETRY_TRIGGER_SIDE_EFFECTS_DETECTED';
  end if;
  raise notice 'PASS: replay is idempotent, zero repeated trigger side effects';

  -- Same identity with different parent version is rejected, not overwritten.
  bad_parent:=pg_catalog.jsonb_set(p.parent,'{0,version}','"TAMPERED"'::jsonb);
  begin
    perform public.alpha_hunter_commit_core_scan_v01(
      bad_parent,p.children,p.signals,p.features,p.readiness
    );
    raise exception 'EXPECTED_CONFLICT_FAILURE_MISSING';
  exception when others then
    if sqlerrm not like '%persisted content mismatch%' then raise; end if;
  end;
  if (select version from public.alpha_hunter_snapshots where run_id='QA_ATOMIC_SCAN_01')<>'qa' then
    raise exception 'IMMUTABLE_EVIDENCE_MUTATED';
  end if;
  raise notice 'PASS: immutable conflict rejection';

  -- Tampered readiness run identity must fail before writing.
  bad_readiness:=pg_catalog.jsonb_set(
      p.readiness,'{0,run_id}','"DIFFERENT_SCAN"'::jsonb
  );
  begin
    perform public.alpha_hunter_commit_core_scan_v01(
      p.parent,p.children,p.signals,p.features,bad_readiness
    );
    raise exception 'EXPECTED_RUN_ID_MISMATCH_NOT_DETECTED';
  exception when others then
    if sqlerrm not like '%run_id mismatch%' then raise; end if;
  end;
  raise notice 'PASS: cross-run identity rejected';

  if (select count(*) from public.alpha_hunter_snapshots)<>1
     or (select count(*) from public.alpha_hunter_symbol_snapshots)<>2
     or (select count(*) from public.alpha_hunter_signals)<>1
     or (select count(*) from public.alpha_hunter_signal_features)<>1
     or (select count(*) from public.alpha_hunter_readiness_observations_v01)<>2
     or (select count(*) from public.qa_atomic_trigger_events)<>7 then
    raise exception 'FINAL_STATE_NOT_COMPLETE';
  end if;
  if pg_catalog.has_function_privilege('anon','public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)','EXECUTE')
     or pg_catalog.has_function_privilege('authenticated','public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)','EXECUTE')
     or not pg_catalog.has_function_privilege('service_role','public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)','EXECUTE') then
    raise exception 'RPC_ROLE_PRIVILEGE_ERROR';
  end if;
  raise notice 'PASS: complete final state and role privilege checks';
end
$test$;
