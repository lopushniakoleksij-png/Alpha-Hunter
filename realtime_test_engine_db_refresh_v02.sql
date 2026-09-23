-- Alpha Hunter DB-native real-time test engine refresh v0.2
--
-- Purpose:
--   Keep alpha_hunter_test_engine_latest_v01 current even when GitHub Actions
--   scheduling is delayed or skipped. This job reads only persisted production
--   evidence and writes an immutable status row. It does not scan markets.
--
-- Safety:
--   paper/shadow only; no execution, threshold, or production-promotion authority.

create or replace function private.alpha_hunter_refresh_test_engine_v02()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  r public.alpha_hunter_realtime_profitability_monitor_v01%rowtype;
  v public.alpha_hunter_profitability_validation_status_v01%rowtype;
  c public.alpha_hunter_profitability_cadence_integrity_v01%rowtype;
  s public.alpha_hunter_profitability_sample_integrity_v01%rowtype;
  f public.alpha_hunter_strategy_forward_status_v01%rowtype;
  o public.alpha_hunter_strategy_opportunity_status_v01%rowtype;
  k public.alpha_hunter_execution_cost_floor_status_v01%rowtype;
  v_now timestamptz := clock_timestamp();
  v_scan_age double precision;
  v_operational text[] := array[]::text[];
  v_economic text[] := array[]::text[];
  v_blockers text[];
  v_operational_status text;
  v_profitability_status text;
  v_verdict text;
  v_id text;
begin
  select m.* into r
  from public.alpha_hunter_realtime_profitability_monitor_v01 m
  order by m.real_test_requested_at_utc desc
  limit 1;

  if r.spec_id is null then
    raise exception 'No profitability spec available';
  end if;

  select x.* into v
  from public.alpha_hunter_profitability_validation_status_v01 x
  where x.spec_id=r.spec_id
  limit 1;

  if v.spec_id is null then
    raise exception 'Validation status missing for spec %', r.spec_id;
  end if;

  select x.* into c
  from public.alpha_hunter_profitability_cadence_integrity_v01 x
  where x.spec_id=r.spec_id
  limit 1;

  select x.* into s
  from public.alpha_hunter_profitability_sample_integrity_v01 x
  where x.spec_id=r.spec_id
  limit 1;

  select x.* into f
  from public.alpha_hunter_strategy_forward_status_v01 x
  limit 1;

  select x.* into o
  from public.alpha_hunter_strategy_opportunity_status_v01 x
  limit 1;

  select x.* into k
  from public.alpha_hunter_execution_cost_floor_status_v01 x
  where x.cost_scope='ALL'
  limit 1;

  v_scan_age := r.latest_live_scan_age_seconds::double precision;

  if v_scan_age is null then
    v_operational := array_append(v_operational,'LIVE_SCAN_AGE_UNKNOWN');
  elsif v_scan_age > 5400.0 then
    v_operational := array_append(v_operational,'LIVE_SCAN_STALE');
  end if;

  if coalesce(r.latest_live_git_commit,'')='' then
    v_operational := array_append(v_operational,'LIVE_BUILD_IDENTITY_MISSING');
  end if;
  if coalesce(r.latest_live_config_sha256,'')='' then
    v_operational := array_append(v_operational,'LIVE_CONFIG_IDENTITY_MISSING');
  end if;
  if coalesce(r.configured_strategy_count,0)<>10 then
    v_operational := array_append(v_operational,'S1_S10_COVERAGE_NOT_10');
  end if;
  if coalesce(r.previous_snapshot_source,'NONE') in ('','NONE') then
    v_operational := array_append(v_operational,'PREVIOUS_CANONICAL_CONTEXT_MISSING');
  end if;
  if coalesce(r.catalyst_version,'')<>'0.2' then
    v_operational := array_append(v_operational,'CATALYST_EVIDENCE_NOT_V02');
  end if;
  if not coalesce(v.test_activated,false) then
    v_operational := array_append(v_operational,'SEALED_TEST_BASELINE_NOT_ACTIVATED');
  end if;
  if not coalesce(v.identity_drift_gate_met,false) then
    v_operational := array_append(v_operational,'BUILD_OR_CONFIG_DRIFT');
  end if;
  if v.test_activated and not coalesce(c.cadence_integrity_ok,false) then
    v_operational := array_append(v_operational,'CADENCE_INTEGRITY_FAILED');
  end if;
  if v.test_activated and not coalesce(s.sealed_sample_integrity_ok,false) then
    v_operational := array_append(v_operational,'SAMPLE_INTEGRITY_FAILED');
  end if;

  if not coalesce(v.cost_model_validated,false) then
    v_economic := array_append(v_economic,'VALIDATED_EXECUTION_COST_MODEL_MISSING');
  end if;
  if not coalesce(v.realistic_net_r_claim_permitted,false) then
    v_economic := array_append(v_economic,'REALISTIC_NET_R_CLAIM_NOT_PERMITTED');
  end if;

  v_operational_status := case
    when cardinality(v_operational)=0 then 'PASS'
    else 'BLOCKED'
  end;
  v_blockers := v_operational || v_economic;
  v_profitability_status := coalesce(v.profitability_test_status,'UNKNOWN');

  v_verdict := case
    when v_profitability_status='POSITIVE_NET_EDGE_DEMONSTRATED_IN_SEALED_PAPER_TEST'
      then 'PAPER_EDGE_DEMONSTRATED'
    when v_profitability_status='NO_POSITIVE_NET_EDGE_DEMONSTRATED'
      then 'NO_POSITIVE_PAPER_EDGE_DEMONSTRATED'
    when v_profitability_status like 'RUNNING_%'
      then 'TEST_RUNNING'
    when v_profitability_status='BLOCKED_NO_VALIDATED_REALISTIC_COST_MODEL'
      then 'TEST_BLOCKED_COST_MODEL'
    else 'NOT_PROVEN'
  end;

  v_id := md5(
    'realtime-test-engine-db-v0.2|'
    ||r.spec_id||'|'||v_now::text||'|'||coalesce(r.latest_live_run_id,'')
  );

  insert into public.alpha_hunter_test_engine_runs_v01(
    test_engine_run_id,
    evaluated_at_utc,
    engine_version,
    spec_id,
    real_test_requested_at_utc,
    real_counted_baseline_started_at_utc,
    latest_live_run_id,
    latest_live_scan_at_utc,
    latest_live_scan_age_seconds,
    latest_live_git_commit,
    latest_live_config_sha256,
    previous_snapshot_source,
    catalyst_version,
    configured_strategy_count,
    real_scans_since_registration,
    real_strategy_observations_since_registration,
    real_shadow_candidates_since_registration,
    real_24h_forward_outcomes_since_registration,
    completed_paper_trades,
    test_days_elapsed,
    minimum_test_days,
    minimum_completed_paper_trades,
    avg_gross_r,
    gross_r_lower_95,
    avg_floor_adjusted_r,
    floor_adjusted_r_lower_95,
    floor_profit_factor,
    avg_modeled_net_r,
    modeled_net_r_lower_95,
    modeled_net_profit_factor,
    cost_model_validated,
    realistic_net_r_claim_permitted,
    operational_status,
    profitability_status,
    verdict,
    blockers,
    source_status,
    economics,
    real_time,
    forward_only,
    historical_replay_counted,
    backtest_counted,
    paper_only,
    live_money_claim_permitted,
    trade_permission,
    threshold_change_permitted,
    production_promotion_permitted,
    order_path
  ) values (
    v_id,
    v_now,
    'realtime-test-engine-db-v0.2',
    r.spec_id,
    r.real_test_requested_at_utc,
    r.real_counted_baseline_started_at_utc,
    r.latest_live_run_id,
    r.latest_live_scan_at_utc,
    v_scan_age,
    r.latest_live_git_commit,
    r.latest_live_config_sha256,
    r.previous_snapshot_source,
    r.catalyst_version,
    r.configured_strategy_count,
    coalesce(r.real_scans_since_registration,0),
    coalesce(r.real_strategy_observations_since_registration,0),
    coalesce(r.real_shadow_candidates_since_registration,0),
    coalesce(r.real_24h_forward_outcomes_since_registration,0),
    coalesce(v.completed_paper_trades,0),
    coalesce(v.test_days_elapsed,0)::double precision,
    v.minimum_test_days,
    v.minimum_completed_paper_trades,
    v.avg_gross_r,
    v.gross_r_lower_95,
    v.avg_floor_adjusted_r,
    v.floor_adjusted_r_lower_95,
    v.floor_profit_factor,
    v.avg_modeled_net_r,
    v.modeled_net_r_lower_95,
    v.modeled_net_profit_factor,
    coalesce(v.cost_model_validated,false),
    coalesce(v.realistic_net_r_claim_permitted,false),
    v_operational_status,
    v_profitability_status,
    v_verdict,
    to_jsonb(v_blockers),
    jsonb_build_object(
      'realtime_test_status',r.realtime_test_status,
      'forward_outcomes',f.forward_outcomes,
      'strategy_episodes',f.strategy_episodes,
      'opportunity_path_rows',o.opportunity_path_rows,
      'operational_blockers',to_jsonb(v_operational),
      'cadence_integrity_status',c.cadence_integrity_status,
      'sample_integrity_status',s.sample_integrity_status,
      'cost_scientific_status',k.scientific_status,
      'cost_next_gate',k.next_gate,
      'refresh_source','SUPABASE_PG_CRON'
    ),
    jsonb_build_object(
      'economic_blockers',to_jsonb(v_economic),
      'duration_gate_met',coalesce(v.duration_gate_met,false),
      'sample_gate_met',coalesce(v.sample_gate_met,false),
      'conservative_floor_edge_gate_met',
        coalesce(v.conservative_floor_edge_gate_met,false),
      'modeled_net_edge_gate_met',
        coalesce(v.modeled_net_edge_gate_met,false)
    ),
    true,
    true,
    false,
    false,
    true,
    false,
    false,
    false,
    false,
    'NONE'
  );

  return jsonb_build_object(
    'test_engine_run_id',v_id,
    'spec_id',r.spec_id,
    'operational_status',v_operational_status,
    'profitability_status',v_profitability_status,
    'verdict',v_verdict,
    'blockers',to_jsonb(v_blockers),
    'paper_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_refresh_test_engine_v02()
  from public,anon,authenticated,service_role;

do $$
declare
  v_job_id bigint;
begin
  for v_job_id in
    select jobid
    from cron.job
    where jobname='alpha-hunter-test-engine-db-refresh-v02'
  loop
    perform cron.unschedule(v_job_id);
  end loop;
end;
$$;

select cron.schedule(
  'alpha-hunter-test-engine-db-refresh-v02',
  '*/10 * * * *',
  'select private.alpha_hunter_refresh_test_engine_v02();'
);
