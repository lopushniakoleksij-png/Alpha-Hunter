-- Alpha Hunter fast profitability test-engine refresh v0.3
-- Ops-only DB function. Preserves sealed V14 profitability gates.
-- Removes repeated non-gating full-table status scans from the refresh path.

create or replace function private.alpha_hunter_refresh_test_engine_v03()
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  sp public.alpha_hunter_profitability_test_specs_v01%rowtype;
  act public.alpha_hunter_profitability_test_activations_v01%rowtype;
  latest public.alpha_hunter_snapshots%rowtype;
  prev public.alpha_hunter_test_engine_runs_v01%rowtype;
  v public.alpha_hunter_profitability_validation_status_v01%rowtype;
  c public.alpha_hunter_profitability_cadence_integrity_v01%rowtype;
  s public.alpha_hunter_profitability_sample_integrity_v01%rowtype;
  q public.alpha_hunter_shadow_decision_quote_status_v01%rowtype;
  sq public.alpha_hunter_sealed_decision_quote_status_v01%rowtype;
  pf public.alpha_hunter_private_fill_cost_readiness_v01%rowtype;

  v_now timestamptz := clock_timestamp();
  v_scan_age double precision;
  v_scan_count bigint := 0;
  v_git text;
  v_config text;
  v_previous_source text;
  v_catalyst_version text;
  v_strategy_count integer := 0;

  v_strategy_obs_count bigint := 0;
  v_shadow_candidate_count bigint := 0;
  v_forward_outcome_count bigint := 0;
  v_forward_outcomes bigint := 0;
  v_strategy_episodes bigint := 0;
  v_opportunity_rows bigint := 0;

  v_operational text[] := array[]::text[];
  v_economic text[] := array[]::text[];
  v_blockers text[];
  v_operational_status text;
  v_profitability_status text;
  v_verdict text;
  v_id text;
begin
  select a.* into act
  from public.alpha_hunter_profitability_test_activations_v01 a
  where a.started_at_utc is not null
  order by a.activated_at_utc desc nulls last
  limit 1;

  if act.spec_id is null then
    raise exception 'No activated profitability spec available';
  end if;

  select x.* into sp
  from public.alpha_hunter_profitability_test_specs_v01 x
  where x.spec_id = act.spec_id
  limit 1;

  if sp.spec_id is null then
    raise exception 'Profitability spec missing for activation %', act.spec_id;
  end if;

  select p.* into latest
  from public.alpha_hunter_snapshots p
  where ((p.payload -> 'validation_identity') ->> 'run_source') = sp.required_run_source
  order by p.collected_at_utc desc
  limit 1;

  if latest.run_id is null then
    raise exception 'No live snapshot for required source %', sp.required_run_source;
  end if;

  select x.* into prev
  from public.alpha_hunter_test_engine_runs_v01 x
  where x.spec_id = sp.spec_id
  order by x.evaluated_at_utc desc
  limit 1;

  -- Gate-critical views remain authoritative.
  select x.* into v
  from public.alpha_hunter_profitability_validation_status_v01 x
  where x.spec_id = sp.spec_id
  limit 1;

  if v.spec_id is null then
    raise exception 'Validation status missing for spec %', sp.spec_id;
  end if;

  select x.* into c
  from public.alpha_hunter_profitability_cadence_integrity_v01 x
  where x.spec_id = sp.spec_id
  limit 1;

  select x.* into s
  from public.alpha_hunter_profitability_sample_integrity_v01 x
  where x.spec_id = sp.spec_id
  limit 1;

  select x.* into q
  from public.alpha_hunter_shadow_decision_quote_status_v01 x
  limit 1;

  select x.* into sq
  from public.alpha_hunter_sealed_decision_quote_status_v01 x
  where x.spec_id = sp.spec_id
  limit 1;

  select x.* into pf
  from public.alpha_hunter_private_fill_cost_readiness_v01 x
  where x.spec_id = sp.spec_id
  limit 1;

  -- Cheap exact scan count; expensive non-gating global counts are carried
  -- forward from the prior test-engine row.
  select count(*) into v_scan_count
  from public.alpha_hunter_snapshots p
  where p.collected_at_utc >= sp.preregistered_at_utc
    and ((p.payload -> 'validation_identity') ->> 'run_source') = sp.required_run_source;

  v_scan_age := extract(epoch from (v_now - latest.collected_at_utc));
  v_git := coalesce(((latest.payload -> 'validation_identity') ->> 'git_commit'),'');
  v_config := coalesce(((latest.payload -> 'validation_identity') ->> 'config_sha256'),'');
  v_previous_source := coalesce(((latest.payload -> 'previous_snapshot_context') ->> 'source'),'NONE');
  v_catalyst_version := coalesce(((latest.payload -> 'catalyst_summary') ->> 'version'),'');
  v_strategy_count := coalesce(
    nullif(((latest.payload -> 'multi_strategy_summary') ->> 'configured_strategy_count'),'')::integer,
    0
  );

  if prev.test_engine_run_id is not null then
    v_strategy_obs_count := coalesce(prev.real_strategy_observations_since_registration,0);
    v_shadow_candidate_count := coalesce(prev.real_shadow_candidates_since_registration,0);
    v_forward_outcome_count := coalesce(prev.real_24h_forward_outcomes_since_registration,0);
    v_forward_outcomes := coalesce(nullif(prev.source_status ->> 'forward_outcomes','')::bigint,0);
    v_strategy_episodes := coalesce(nullif(prev.source_status ->> 'strategy_episodes','')::bigint,0);
    v_opportunity_rows := coalesce(nullif(prev.source_status ->> 'opportunity_path_rows','')::bigint,0);
  end if;

  if v_scan_age is null then
    v_operational := array_append(v_operational,'LIVE_SCAN_AGE_UNKNOWN');
  elsif v_scan_age > 5400.0 then
    v_operational := array_append(v_operational,'LIVE_SCAN_STALE');
  end if;

  if v_git='' then
    v_operational := array_append(v_operational,'LIVE_BUILD_IDENTITY_MISSING');
  end if;
  if v_config='' then
    v_operational := array_append(v_operational,'LIVE_CONFIG_IDENTITY_MISSING');
  end if;
  if v_strategy_count<>10 then
    v_operational := array_append(v_operational,'S1_S10_COVERAGE_NOT_10');
  end if;
  if v_previous_source in ('','NONE') then
    v_operational := array_append(v_operational,'PREVIOUS_CANONICAL_CONTEXT_MISSING');
  end if;
  if v_catalyst_version<>'0.2' then
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

  if coalesce(pf.readiness_status,'MISSING')<>'READY_FOR_PROSPECTIVE_FILL_MATCHING' then
    v_economic := array_append(
      v_economic,
      case coalesce(pf.readiness_status,'MISSING')
        when 'BLOCKED_ACCOUNT_IDENTITY_UNPINNED' then 'PRIVATE_FILL_ACCOUNT_IDENTITY_UNPINNED'
        when 'BLOCKED_ACCOUNT_IDENTITY_MISMATCH' then 'PRIVATE_FILL_ACCOUNT_IDENTITY_MISMATCH'
        when 'BLOCKED_PRIVATE_ACCOUNT_NOT_CONNECTED' then 'PRIVATE_FILL_ACCOUNT_NOT_CONNECTED'
        when 'BLOCKED_FILL_TRACEABILITY_INCOMPLETE' then 'PRIVATE_FILL_TRACEABILITY_INCOMPLETE'
        else 'PRIVATE_FILL_READINESS_MISSING'
      end
    );
  end if;

  v_operational_status := case when cardinality(v_operational)=0 then 'PASS' else 'BLOCKED' end;
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
    'realtime-test-engine-db-v0.3-fast|'
    ||sp.spec_id||'|'||v_now::text||'|'||coalesce(latest.run_id,'')
  );

  insert into public.alpha_hunter_test_engine_runs_v01(
    test_engine_run_id,evaluated_at_utc,engine_version,spec_id,
    real_test_requested_at_utc,real_counted_baseline_started_at_utc,
    latest_live_run_id,latest_live_scan_at_utc,latest_live_scan_age_seconds,
    latest_live_git_commit,latest_live_config_sha256,previous_snapshot_source,
    catalyst_version,configured_strategy_count,real_scans_since_registration,
    real_strategy_observations_since_registration,
    real_shadow_candidates_since_registration,
    real_24h_forward_outcomes_since_registration,
    completed_paper_trades,test_days_elapsed,minimum_test_days,
    minimum_completed_paper_trades,avg_gross_r,gross_r_lower_95,
    avg_floor_adjusted_r,floor_adjusted_r_lower_95,floor_profit_factor,
    avg_modeled_net_r,modeled_net_r_lower_95,modeled_net_profit_factor,
    cost_model_validated,realistic_net_r_claim_permitted,operational_status,
    profitability_status,verdict,blockers,source_status,economics,
    real_time,forward_only,historical_replay_counted,backtest_counted,
    paper_only,live_money_claim_permitted,trade_permission,
    threshold_change_permitted,production_promotion_permitted,order_path
  ) values (
    v_id,v_now,'realtime-test-engine-db-v0.3-fast',sp.spec_id,
    sp.preregistered_at_utc,act.started_at_utc,latest.run_id,
    latest.collected_at_utc,v_scan_age,v_git,v_config,v_previous_source,
    v_catalyst_version,v_strategy_count,v_scan_count,
    v_strategy_obs_count,v_shadow_candidate_count,v_forward_outcome_count,
    coalesce(v.completed_paper_trades,0),
    coalesce(v.test_days_elapsed,0)::double precision,
    v.minimum_test_days,v.minimum_completed_paper_trades,
    v.avg_gross_r,v.gross_r_lower_95,v.avg_floor_adjusted_r,
    v.floor_adjusted_r_lower_95,v.floor_profit_factor,v.avg_modeled_net_r,
    v.modeled_net_r_lower_95,v.modeled_net_profit_factor,
    coalesce(v.cost_model_validated,false),
    coalesce(v.realistic_net_r_claim_permitted,false),
    v_operational_status,v_profitability_status,v_verdict,to_jsonb(v_blockers),
    jsonb_build_object(
      'realtime_test_status','RUNNING_FORWARD_REAL_TIME',
      'forward_outcomes',v_forward_outcomes,
      'strategy_episodes',v_strategy_episodes,
      'opportunity_path_rows',v_opportunity_rows,
      'non_gating_counts_carried_forward',true,
      'operational_blockers',to_jsonb(v_operational),
      'cadence_integrity_status',c.cadence_integrity_status,
      'sample_integrity_status',s.sample_integrity_status,
      'post_baseline_candidate_observations',s.post_baseline_candidate_observation_count,
      'left_censored_candidate_observations',s.left_censored_candidate_observation_count,
      'post_baseline_candidate_episodes',s.post_baseline_candidate_episode_count,
      'post_baseline_24h_outcomes',s.post_baseline_24h_outcome_rows,
      'post_baseline_24h_economic_eligible',s.post_baseline_24h_economic_eligible_rows,
      'decision_quote_count',q.captured_candidate_quotes,
      'decision_quote_complete_count',q.complete_candidate_quotes,
      'decision_quote_incomplete_count',q.incomplete_candidate_quotes,
      'decision_quote_avg_half_spread_bps',q.avg_entry_cross_half_spread_bps,
      'decision_quote_p90_half_spread_bps',q.p90_entry_cross_half_spread_bps,
      'decision_quote_scientific_status',q.scientific_status,
      'decision_quote_next_gate',q.next_gate,
      'sealed_decision_quote_rows',sq.post_baseline_quote_rows,
      'sealed_left_censored_quote_rows',sq.left_censored_quote_rows,
      'sealed_eligible_quote_rows',sq.sealed_eligible_quote_rows,
      'sealed_complete_quote_rows',sq.complete_sealed_eligible_quote_rows,
      'sealed_execute_now_quote_rows',sq.sealed_execute_now_quote_rows,
      'sealed_place_limit_quote_rows',sq.sealed_place_limit_quote_rows,
      'sealed_quote_avg_half_spread_bps',sq.avg_sealed_entry_cross_half_spread_bps,
      'sealed_quote_p90_half_spread_bps',sq.p90_sealed_entry_cross_half_spread_bps,
      'private_fill_readiness_status',pf.readiness_status,
      'private_fill_account_status',pf.private_account_status,
      'private_fill_account_mode',pf.account_mode,
      'private_fill_account_is_subaccount',pf.account_is_subaccount,
      'private_fill_identity_probe_status',pf.account_identity_probe_status,
      'private_fill_identity_gate_met',pf.account_identity_gate_met,
      'private_fill_traceability_status',pf.fill_traceability_status,
      'private_fill_traceability_gate_met',pf.fill_traceability_gate_met,
      'private_fill_count',pf.fill_count,
      'private_fill_next_gate',pf.next_gate,
      'cost_scientific_status',v.cost_scientific_status,
      'cost_next_gate',v.cost_next_gate,
      'refresh_source','SUPABASE_PG_CRON_FAST_V03'
    ),
    jsonb_build_object(
      'economic_blockers',to_jsonb(v_economic),
      'duration_gate_met',coalesce(v.duration_gate_met,false),
      'sample_gate_met',coalesce(v.sample_gate_met,false),
      'conservative_floor_edge_gate_met',coalesce(v.conservative_floor_edge_gate_met,false),
      'modeled_net_edge_gate_met',coalesce(v.modeled_net_edge_gate_met,false)
    ),
    true,true,false,false,true,false,false,false,false,'NONE'
  );

  return jsonb_build_object(
    'test_engine_run_id',v_id,
    'spec_id',sp.spec_id,
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
$function$;

revoke all on function private.alpha_hunter_refresh_test_engine_v03() from public;
grant execute on function private.alpha_hunter_refresh_test_engine_v03() to postgres, service_role;

select cron.alter_job(
  job_id := (select jobid from cron.job where jobname='alpha-hunter-test-engine-db-refresh-v02'),
  schedule := '2 * * * *',
  command := 'select private.alpha_hunter_refresh_test_engine_v03();'
);
