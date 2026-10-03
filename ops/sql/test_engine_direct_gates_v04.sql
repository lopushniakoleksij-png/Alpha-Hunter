-- Alpha Hunter direct profitability gate refresh v0.4
--
-- Operational monitor only. Replaces heavyweight wrapper-view evaluation with
-- the same gate inputs read directly from canonical sealed evidence.
-- No trading thresholds, strategy logic, scientific sample, or permissions change.

create or replace function private.alpha_hunter_refresh_test_engine_v04()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  sp public.alpha_hunter_profitability_test_specs_v01%rowtype;
  act public.alpha_hunter_profitability_test_activations_v01%rowtype;
  latest public.alpha_hunter_snapshots%rowtype;
  prev public.alpha_hunter_test_engine_runs_v01%rowtype;
  cad public.alpha_hunter_profitability_cadence_integrity_v01%rowtype;
  pf public.alpha_hunter_private_fill_cost_readiness_v01%rowtype;

  v_now timestamptz := clock_timestamp();
  v_days double precision := 0;
  v_scan_age double precision;
  v_scan_count integer := 0;
  v_drift_scans bigint := 0;

  v_completed bigint := 0;
  v_avg_gross double precision;
  v_sd_gross double precision;
  v_avg_floor double precision;
  v_sd_floor double precision;
  v_floor_pf double precision;
  v_modeled_count bigint := 0;
  v_avg_modeled double precision;
  v_sd_modeled double precision;
  v_modeled_pf double precision;

  v_gross_lower double precision;
  v_floor_lower double precision;
  v_modeled_lower double precision;

  v_contaminated bigint := 0;
  v_duplicate_econ bigint := 0;
  v_outcome_pk_ok boolean := false;
  v_sample_ok boolean := false;
  v_sample_status text := 'UNKNOWN';

  v_git text := '';
  v_config text := '';
  v_previous_source text := 'NONE';
  v_catalyst_version text := '';
  v_strategy_count integer := 0;

  v_operational text[] := array[]::text[];
  v_economic text[] := array[
    'VALIDATED_EXECUTION_COST_MODEL_MISSING',
    'REALISTIC_NET_R_CLAIM_NOT_PERMITTED'
  ]::text[];
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

  select s.* into sp
  from public.alpha_hunter_profitability_test_specs_v01 s
  where s.spec_id=act.spec_id;

  if sp.spec_id is null then
    raise exception 'Profitability spec missing for activation %',act.spec_id;
  end if;

  select p.* into latest
  from public.alpha_hunter_snapshots p
  where (p.payload->'validation_identity'->>'run_source')=sp.required_run_source
  order by p.collected_at_utc desc
  limit 1;

  if latest.run_id is null then
    raise exception 'No live snapshot for required source %',sp.required_run_source;
  end if;

  select r.* into prev
  from public.alpha_hunter_test_engine_runs_v01 r
  where r.spec_id=sp.spec_id
  order by r.evaluated_at_utc desc
  limit 1;

  select c.* into cad
  from public.alpha_hunter_profitability_cadence_integrity_v01 c
  where c.spec_id=sp.spec_id
  limit 1;

  select f.* into pf
  from public.alpha_hunter_private_fill_cost_readiness_v01 f
  where f.spec_id=sp.spec_id
  limit 1;

  select
    count(*)::integer,
    count(*) filter(where
      (sp.frozen_scientific_fingerprint_sha256 is not null
       and coalesce(p.payload->'validation_identity'->>'scientific_fingerprint_sha256','')
           <> sp.frozen_scientific_fingerprint_sha256)
      or
      (sp.frozen_scientific_fingerprint_sha256 is null
       and (
         coalesce(p.payload->'validation_identity'->>'git_commit','')<>act.baseline_git_commit
         or coalesce(p.payload->'validation_identity'->>'config_sha256','')<>act.baseline_config_sha256
       ))
    )
  into v_scan_count,v_drift_scans
  from public.alpha_hunter_snapshots p
  where p.collected_at_utc>=act.started_at_utc
    and p.payload->'validation_identity'->>'run_source'=sp.required_run_source;

  select
    count(*),
    avg(e.gross_r_pre_cost),
    stddev_samp(e.gross_r_pre_cost),
    avg(e.floor_adjusted_r),
    stddev_samp(e.floor_adjusted_r),
    sum(e.floor_adjusted_r) filter(where e.floor_adjusted_r>0)
      / nullif(abs(sum(e.floor_adjusted_r) filter(where e.floor_adjusted_r<0)),0),
    count(*) filter(where e.modeled_net_r is not null),
    avg(e.modeled_net_r) filter(where e.modeled_net_r is not null),
    stddev_samp(e.modeled_net_r) filter(where e.modeled_net_r is not null),
    sum(e.modeled_net_r) filter(where e.modeled_net_r>0)
      / nullif(abs(sum(e.modeled_net_r) filter(where e.modeled_net_r<0)),0),
    count(*) filter(where e.first_observed_at_utc<act.started_at_utc),
    count(*)-count(distinct e.episode_id)
  into
    v_completed,v_avg_gross,v_sd_gross,v_avg_floor,v_sd_floor,v_floor_pf,
    v_modeled_count,v_avg_modeled,v_sd_modeled,v_modeled_pf,
    v_contaminated,v_duplicate_econ
  from public.alpha_hunter_strategy_paper_economics_v01 e
  where e.spec_id=sp.spec_id;

  select exists(
    select 1
    from pg_catalog.pg_constraint c
    join pg_catalog.pg_class t on t.oid=c.conrelid
    join pg_catalog.pg_namespace n on n.oid=t.relnamespace
    where n.nspname='public'
      and t.relname='alpha_hunter_strategy_forward_outcomes_v01'
      and c.contype='p'
  ) into v_outcome_pk_ok;

  v_sample_ok := (
    v_contaminated=0
    and v_duplicate_econ=0
    and v_outcome_pk_ok
  );

  v_sample_status := case
    when v_contaminated>0 then 'FAIL_PRE_BASELINE_CONTAMINATION'
    when v_duplicate_econ>0 or not v_outcome_pk_ok then 'FAIL_DUPLICATE_SAMPLE_ROWS'
    else 'PASS'
  end;

  v_days := extract(epoch from (v_now-act.started_at_utc))/86400.0;
  v_scan_age := extract(epoch from (v_now-latest.collected_at_utc));

  if v_completed>=2 then
    v_gross_lower := v_avg_gross-(sp.confidence_z*v_sd_gross/sqrt(v_completed::double precision));
    v_floor_lower := v_avg_floor-(sp.confidence_z*v_sd_floor/sqrt(v_completed::double precision));
  end if;

  if v_modeled_count>=2 then
    v_modeled_lower := v_avg_modeled-(sp.confidence_z*v_sd_modeled/sqrt(v_modeled_count::double precision));
  end if;

  v_git := coalesce(latest.payload->'validation_identity'->>'git_commit','');
  v_config := coalesce(latest.payload->'validation_identity'->>'config_sha256','');
  v_previous_source := coalesce(latest.payload->'previous_snapshot_context'->>'source','NONE');
  v_catalyst_version := coalesce(latest.payload->'catalyst_summary'->>'version','');
  v_strategy_count := coalesce(
    nullif(latest.payload->'multi_strategy_summary'->>'configured_strategy_count','')::integer,
    0
  );

  if v_scan_age>5400 then
    v_operational:=array_append(v_operational,'LIVE_SCAN_STALE');
  end if;
  if v_git='' then
    v_operational:=array_append(v_operational,'LIVE_BUILD_IDENTITY_MISSING');
  end if;
  if v_config='' then
    v_operational:=array_append(v_operational,'LIVE_CONFIG_IDENTITY_MISSING');
  end if;
  if v_strategy_count<>10 then
    v_operational:=array_append(v_operational,'S1_S10_COVERAGE_NOT_10');
  end if;
  if v_previous_source in ('','NONE') then
    v_operational:=array_append(v_operational,'PREVIOUS_CANONICAL_CONTEXT_MISSING');
  end if;
  if v_catalyst_version<>'0.2' then
    v_operational:=array_append(v_operational,'CATALYST_EVIDENCE_NOT_V02');
  end if;
  if v_drift_scans>0 then
    v_operational:=array_append(v_operational,'BUILD_OR_CONFIG_DRIFT');
  end if;
  if not coalesce(cad.cadence_integrity_ok,false) then
    v_operational:=array_append(v_operational,'CADENCE_INTEGRITY_FAILED');
  end if;
  if not v_sample_ok then
    v_operational:=array_append(v_operational,'SAMPLE_INTEGRITY_FAILED');
  end if;

  if coalesce(pf.readiness_status,'MISSING')<>'READY_FOR_PROSPECTIVE_FILL_MATCHING' then
    v_economic:=array_append(
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

  v_operational_status := case
    when cardinality(v_operational)=0 then 'PASS'
    else 'BLOCKED'
  end;

  v_profitability_status := case
    when v_drift_scans>0 then 'INVALIDATED_BY_BUILD_OR_CONFIG_DRIFT'
    when v_days<sp.minimum_test_days then 'RUNNING_MINIMUM_DURATION_NOT_MET'
    when v_completed<sp.minimum_completed_paper_trades then 'RUNNING_SAMPLE_NOT_MET'
    when sp.require_validated_cost_model then 'BLOCKED_NO_VALIDATED_REALISTIC_COST_MODEL'
    when not (
      v_modeled_lower>0
      and coalesce(v_modeled_pf,0)>1.0
    ) then 'NO_POSITIVE_NET_EDGE_DEMONSTRATED'
    else 'POSITIVE_NET_EDGE_DEMONSTRATED_IN_SEALED_PAPER_TEST'
  end;

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

  v_blockers:=v_operational||v_economic;

  v_id:=md5(
    'realtime-test-engine-db-v0.4-direct-gates|'
    ||sp.spec_id||'|'||v_now::text||'|'||latest.run_id
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
    cost_model_validated,realistic_net_r_claim_permitted,
    operational_status,profitability_status,verdict,blockers,source_status,economics,
    real_time,forward_only,historical_replay_counted,backtest_counted,paper_only,
    live_money_claim_permitted,trade_permission,threshold_change_permitted,
    production_promotion_permitted,order_path
  ) values (
    v_id,v_now,'realtime-test-engine-db-v0.4-direct-gates',sp.spec_id,
    sp.preregistered_at_utc,act.started_at_utc,latest.run_id,latest.collected_at_utc,
    v_scan_age,v_git,v_config,v_previous_source,v_catalyst_version,v_strategy_count,
    v_scan_count,
    coalesce(prev.real_strategy_observations_since_registration,0),
    coalesce(prev.real_shadow_candidates_since_registration,0),
    coalesce(prev.real_24h_forward_outcomes_since_registration,0),
    v_completed,v_days,sp.minimum_test_days,sp.minimum_completed_paper_trades,
    v_avg_gross,v_gross_lower,v_avg_floor,v_floor_lower,v_floor_pf,
    v_avg_modeled,v_modeled_lower,v_modeled_pf,
    false,false,
    v_operational_status,v_profitability_status,v_verdict,to_jsonb(v_blockers),
    coalesce(prev.source_status,'{}'::jsonb)||jsonb_build_object(
      'refresh_source','SUPABASE_PG_CRON_DIRECT_GATES_V04',
      'post_start_scans',v_scan_count,
      'identity_drift_scans',v_drift_scans,
      'cadence_integrity_status',cad.cadence_integrity_status,
      'cadence_integrity_ok',cad.cadence_integrity_ok,
      'excessive_gap_intervals',cad.excessive_gap_intervals,
      'sample_integrity_status',v_sample_status,
      'sample_integrity_ok',v_sample_ok,
      'contaminated_pre_baseline_economics_rows',v_contaminated,
      'duplicate_economics_episode_rows',v_duplicate_econ,
      'outcome_primary_key_uniqueness_verified',v_outcome_pk_ok,
      'private_fill_readiness_status',pf.readiness_status,
      'private_fill_count',pf.fill_count,
      'cost_scientific_status','DESCRIPTIVE_OBSERVED_COST_FLOOR_ONLY',
      'cost_next_gate','FORWARD_DECISION_TO_FILL_BENCHMARK_AND_SLIPPAGE_VALIDATION'
    ),
    jsonb_build_object(
      'economic_blockers',to_jsonb(v_economic),
      'duration_gate_met',v_days>=sp.minimum_test_days,
      'sample_gate_met',v_completed>=sp.minimum_completed_paper_trades,
      'conservative_floor_edge_gate_met',
        (
          v_completed>=sp.minimum_completed_paper_trades
          and v_floor_lower>0
          and coalesce(v_floor_pf,0)>1.0
        ),
      'modeled_net_edge_gate_met',false
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

revoke all on function private.alpha_hunter_refresh_test_engine_v04() from public;
grant execute on function private.alpha_hunter_refresh_test_engine_v04() to postgres,service_role;

select cron.alter_job(
  job_id := (
    select jobid
    from cron.job
    where jobname='alpha-hunter-test-engine-db-refresh-v02'
  ),
  schedule := '59 * * * *',
  command := 'select private.alpha_hunter_refresh_test_engine_v04();',
  active := true
);
