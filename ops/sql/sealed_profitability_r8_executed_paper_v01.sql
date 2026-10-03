begin;

-- Alpha Hunter sealed profitability R8 executed-paper protocol v0.1.
--
-- Preregistration only. This migration does NOT activate R8, does NOT open the
-- R8 paper-execution gate, and does NOT change the pg_cron evaluator.
--
-- R8 scientific sample:
--   public.alpha_hunter_paper_completed_trades_valid_v08
--
-- Scientific integrity rule:
--   any post-activation completed trade in the R8 quarantine invalidates the
--   cohort rather than being silently excluded from profitability statistics.
--
-- Paper/shadow only. No exchange authority.

insert into public.alpha_hunter_profitability_test_specs_v01 (
  spec_id,
  protocol_version,
  frozen_git_commit,
  required_strategy_count,
  required_minimum_rr,
  evaluation_horizon_hours,
  minimum_test_days,
  minimum_completed_paper_trades,
  confidence_z,
  require_validated_cost_model,
  preregistered_at_utc,
  scientific_role,
  shadow_only,
  trade_permission,
  production_promotion_permitted,
  order_path,
  required_run_source,
  frozen_scientific_fingerprint_sha256
) values (
  'SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003',
  'sealed-profitability-v0.5-r8-executed-paper-integrity',
  '4f45f9d9ba343eccbbf8e4d49fe13a163ec7f2c8',
  10,
  5.0,
  24,
  30,
  100,
  1.96,
  true,
  clock_timestamp(),
  'SEALED_PROFITABILITY_PREREGISTRATION_R8_EXECUTED_PAPER',
  true,
  false,
  false,
  'NONE',
  'RENDER_CRON',
  '176b271ab6fe8b1905bfeb5118be77b6183cad6311925795cd912a7b055b99d1'
)
on conflict(spec_id) do nothing;


create or replace view public.alpha_hunter_r8_profitability_preregistration_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  s.spec_id,
  s.protocol_version,
  s.frozen_git_commit,
  s.frozen_scientific_fingerprint_sha256,
  s.minimum_test_days,
  s.minimum_completed_paper_trades,
  s.confidence_z,
  s.require_validated_cost_model,
  s.preregistered_at_utc,
  exists(
    select 1
    from public.alpha_hunter_profitability_test_activations_v01 a
    where a.spec_id=s.spec_id
  ) as profitability_activation_exists,
  exists(
    select 1
    from public.alpha_hunter_paper_execution_integrity_activation_v08 e
    where e.activation_id='PAPER_EXECUTION_R8'
      and e.scientific_fingerprint_sha256
          =s.frozen_scientific_fingerprint_sha256
  ) as paper_execution_activation_exists,
  'alpha_hunter_paper_completed_trades_valid_v08'::text as sample_source,
  'alpha_hunter_paper_completed_trades_quarantine_v08'::text as quarantine_source,
  true as quarantine_nonzero_invalidates_cohort,
  true as paper_only,
  false as live_money_claim_permitted,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_profitability_test_specs_v01 s
where s.spec_id='SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003';

revoke all on public.alpha_hunter_r8_profitability_preregistration_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r8_profitability_preregistration_status_v01
  to service_role;


create or replace function private.alpha_hunter_refresh_test_engine_v06_r8()
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  sp public.alpha_hunter_profitability_test_specs_v01%rowtype;
  act public.alpha_hunter_profitability_test_activations_v01%rowtype;
  latest public.alpha_hunter_snapshots%rowtype;
  cad public.alpha_hunter_profitability_cadence_integrity_v01%rowtype;
  exec_act public.alpha_hunter_paper_execution_integrity_activation_v08%rowtype;
  integrity public.alpha_hunter_paper_execution_integrity_status_v08%rowtype;
  cost public.alpha_hunter_execution_cost_validation_readiness_v04%rowtype;

  v_now timestamptz:=clock_timestamp();
  v_days double precision:=0;
  v_scan_age double precision;
  v_scan_count bigint:=0;
  v_drift_scans bigint:=0;

  v_completed bigint:=0;
  v_quarantined bigint:=0;
  v_wins bigint:=0;
  v_nonwins bigint:=0;
  v_avg_gross double precision;
  v_sd_gross double precision;
  v_avg_net double precision;
  v_sd_net double precision;
  v_net_pf double precision;
  v_total_net_r double precision;
  v_total_net_pnl double precision;
  v_avg_net_pnl double precision;
  v_win_rate double precision;
  v_gross_lower double precision;
  v_net_lower double precision;

  v_operational text[]:=array[]::text[];
  v_economic text[]:=array[]::text[];
  v_blockers text[];
  v_operational_status text;
  v_profitability_status text;
  v_verdict text;
  v_id text;

  v_git text:='';
  v_config text:='';
  v_previous_source text:='NONE';
  v_catalyst_version text:='';
  v_strategy_count integer:=0;
  v_cost_validated boolean:=false;
  v_realistic_claim boolean:=false;
begin
  select a.* into act
  from public.alpha_hunter_profitability_test_activations_v01 a
  where a.spec_id='SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003'
    and a.started_at_utc is not null
  order by a.activated_at_utc desc
  limit 1;

  if act.spec_id is null then
    raise exception 'R8 executed-paper profitability spec is not activated';
  end if;

  select s.* into sp
  from public.alpha_hunter_profitability_test_specs_v01 s
  where s.spec_id=act.spec_id;

  if sp.spec_id is null then
    raise exception 'R8 profitability spec missing for activation';
  end if;

  select e.* into exec_act
  from public.alpha_hunter_paper_execution_integrity_activation_v08 e
  where e.activation_id='PAPER_EXECUTION_R8'
  order by e.activated_at_utc desc
  limit 1;

  if exec_act.activation_id is null then
    v_operational:=array_append(v_operational,'R8_PAPER_EXECUTION_NOT_ACTIVATED');
  elsif exec_act.scientific_fingerprint_sha256
        <>sp.frozen_scientific_fingerprint_sha256 then
    v_operational:=array_append(v_operational,'R8_EXECUTION_ACTIVATION_FINGERPRINT_MISMATCH');
  elsif exec_act.activated_at_utc<>act.started_at_utc then
    v_operational:=array_append(v_operational,'R8_EXECUTION_AND_PROFITABILITY_BASELINE_MISALIGNED');
  end if;

  select p.* into latest
  from public.alpha_hunter_snapshots p
  where p.payload->'validation_identity'->>'run_source'=sp.required_run_source
  order by p.collected_at_utc desc
  limit 1;

  if latest.run_id is null then
    raise exception 'No live RENDER_CRON snapshot available for R8';
  end if;

  select c.* into cad
  from public.alpha_hunter_profitability_cadence_integrity_v01 c
  where c.spec_id=sp.spec_id
  limit 1;

  select i.* into integrity
  from public.alpha_hunter_paper_execution_integrity_status_v08 i
  where i.activation_id='PAPER_EXECUTION_R8'
  limit 1;

  select c.* into cost
  from public.alpha_hunter_execution_cost_validation_readiness_v04 c
  limit 1;

  select
    count(*),
    count(*) filter(where t.paper_net_pnl_ex_funding>0),
    count(*) filter(where t.paper_net_pnl_ex_funding<=0),
    avg(t.gross_r),
    stddev_samp(t.gross_r),
    avg(t.net_r_ex_funding),
    stddev_samp(t.net_r_ex_funding),
    sum(t.net_r_ex_funding) filter(where t.net_r_ex_funding>0)
      /nullif(abs(sum(t.net_r_ex_funding) filter(where t.net_r_ex_funding<0)),0),
    sum(t.net_r_ex_funding),
    sum(t.paper_net_pnl_ex_funding),
    avg(t.paper_net_pnl_ex_funding)
  into
    v_completed,v_wins,v_nonwins,
    v_avg_gross,v_sd_gross,v_avg_net,v_sd_net,v_net_pf,
    v_total_net_r,v_total_net_pnl,v_avg_net_pnl
  from public.alpha_hunter_paper_completed_trades_valid_v08 t;

  select count(*)
  into v_quarantined
  from public.alpha_hunter_paper_completed_trades_quarantine_v08 q;

  select
    count(*),
    count(*) filter(where
      coalesce(p.payload->'validation_identity'->>'scientific_fingerprint_sha256','')
      <>sp.frozen_scientific_fingerprint_sha256
    )
  into v_scan_count,v_drift_scans
  from public.alpha_hunter_snapshots p
  where p.collected_at_utc>=act.started_at_utc
    and p.payload->'validation_identity'->>'run_source'=sp.required_run_source;

  v_days:=extract(epoch from (v_now-act.started_at_utc))/86400.0;
  v_scan_age:=extract(epoch from (v_now-latest.collected_at_utc));

  if v_completed>=2 then
    v_gross_lower:=v_avg_gross-(sp.confidence_z*v_sd_gross/sqrt(v_completed::double precision));
    v_net_lower:=v_avg_net-(sp.confidence_z*v_sd_net/sqrt(v_completed::double precision));
  end if;

  if v_completed>0 then
    v_win_rate:=100.0*v_wins::double precision/v_completed::double precision;
  end if;

  v_git:=coalesce(latest.payload->'validation_identity'->>'git_commit','');
  v_config:=coalesce(latest.payload->'validation_identity'->>'config_sha256','');
  v_previous_source:=coalesce(latest.payload->'previous_snapshot_context'->>'source','NONE');
  v_catalyst_version:=coalesce(latest.payload->'catalyst_summary'->>'version','');
  v_strategy_count:=coalesce(
    nullif(latest.payload->'multi_strategy_summary'->>'configured_strategy_count','')::integer,
    0
  );

  v_cost_validated:=coalesce(cost.full_cost_validation_evidence_complete,false)
    and coalesce(cost.cost_model_activation_permitted,false);
  v_realistic_claim:=coalesce(cost.realistic_net_r_claim_permitted,false);

  if v_scan_age>5400 then
    v_operational:=array_append(v_operational,'LIVE_SCAN_STALE');
  end if;
  if v_git='' then
    v_operational:=array_append(v_operational,'LIVE_BUILD_IDENTITY_MISSING');
  end if;
  if v_config='' then
    v_operational:=array_append(v_operational,'LIVE_CONFIG_IDENTITY_MISSING');
  end if;
  if coalesce(
       latest.payload->'validation_identity'->>'scientific_fingerprint_sha256',''
     )<>sp.frozen_scientific_fingerprint_sha256 then
    v_operational:=array_append(v_operational,'LIVE_SCIENTIFIC_FINGERPRINT_MISMATCH');
  end if;
  if v_strategy_count<>sp.required_strategy_count then
    v_operational:=array_append(v_operational,'S1_S10_COVERAGE_NOT_10');
  end if;
  if v_previous_source in ('','NONE') then
    v_operational:=array_append(v_operational,'PREVIOUS_CANONICAL_CONTEXT_MISSING');
  end if;
  if v_catalyst_version<>'0.2' then
    v_operational:=array_append(v_operational,'CATALYST_EVIDENCE_NOT_V02');
  end if;
  if v_drift_scans>0 then
    v_operational:=array_append(v_operational,'R8_SCIENTIFIC_FINGERPRINT_DRIFT');
  end if;
  if not coalesce(cad.cadence_integrity_ok,false) then
    v_operational:=array_append(v_operational,'CADENCE_INTEGRITY_FAILED');
  end if;
  if v_quarantined>0 then
    v_operational:=array_append(v_operational,'R8_COMPLETED_TRADE_QUARANTINE_NONZERO');
  end if;
  if coalesce(integrity.duplicate_active_exposure_groups,0)>0 then
    v_operational:=array_append(v_operational,'R8_DUPLICATE_ACTIVE_EXPOSURE_DETECTED');
  end if;
  if not coalesce(integrity.one_exposure_guard_integrity_ok,false) then
    v_operational:=array_append(v_operational,'R8_ONE_EXPOSURE_GUARD_INTEGRITY_FAILED');
  end if;

  if not v_cost_validated then
    v_economic:=array_append(v_economic,'VALIDATED_EXECUTION_COST_MODEL_MISSING');
  end if;
  if not v_realistic_claim then
    v_economic:=array_append(v_economic,'REALISTIC_NET_R_CLAIM_NOT_PERMITTED');
  end if;

  v_operational_status:=case
    when cardinality(v_operational)=0 then 'PASS'
    else 'BLOCKED'
  end;

  v_profitability_status:=case
    when v_quarantined>0 then 'INVALIDATED_BY_R8_EXECUTION_INTEGRITY_DEFECT'
    when v_drift_scans>0 then 'INVALIDATED_BY_R8_SCIENTIFIC_FINGERPRINT_DRIFT'
    when cardinality(v_operational)>0 then 'BLOCKED_R8_OPERATIONAL_INTEGRITY'
    when v_days<sp.minimum_test_days then 'RUNNING_MINIMUM_DURATION_NOT_MET'
    when v_completed<sp.minimum_completed_paper_trades then 'RUNNING_SAMPLE_NOT_MET'
    when not (
      v_net_lower>0
      and coalesce(v_net_pf,0)>1.0
    ) then 'NO_POSITIVE_PAPER_EXECUTION_EDGE_EX_FUNDING_DEMONSTRATED'
    when not v_cost_validated or not v_realistic_claim
      then 'PAPER_EXECUTION_EDGE_EX_FUNDING_OBSERVED_COST_MODEL_BLOCKED'
    else 'POSITIVE_NET_EDGE_DEMONSTRATED_IN_SEALED_R8_EXECUTED_PAPER_TEST'
  end;

  v_verdict:=case
    when v_profitability_status='POSITIVE_NET_EDGE_DEMONSTRATED_IN_SEALED_R8_EXECUTED_PAPER_TEST'
      then 'PAPER_EDGE_DEMONSTRATED'
    when v_profitability_status='NO_POSITIVE_PAPER_EXECUTION_EDGE_EX_FUNDING_DEMONSTRATED'
      then 'NO_POSITIVE_PAPER_EDGE_DEMONSTRATED'
    when v_profitability_status like 'RUNNING_%'
      then 'TEST_RUNNING'
    when v_profitability_status='PAPER_EXECUTION_EDGE_EX_FUNDING_OBSERVED_COST_MODEL_BLOCKED'
      then 'TEST_BLOCKED_COST_MODEL'
    else 'NOT_PROVEN'
  end;

  v_blockers:=v_operational||v_economic;

  v_id:=md5(
    'realtime-test-engine-db-v0.6-r8-executed-paper|'
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
    v_id,v_now,'realtime-test-engine-db-v0.6-r8-executed-paper',sp.spec_id,
    sp.preregistered_at_utc,act.started_at_utc,
    latest.run_id,latest.collected_at_utc,v_scan_age,
    v_git,v_config,v_previous_source,v_catalyst_version,v_strategy_count,
    v_scan_count,
    0,0,0,
    v_completed,v_days,sp.minimum_test_days,sp.minimum_completed_paper_trades,
    v_avg_gross,v_gross_lower,
    null,null,null,
    v_avg_net,v_net_lower,v_net_pf,
    v_cost_validated,v_realistic_claim,
    v_operational_status,v_profitability_status,v_verdict,to_jsonb(v_blockers),
    jsonb_build_object(
      'refresh_source','SUPABASE_PG_CRON_R8_EXECUTED_PAPER_V06',
      'sample_source','alpha_hunter_paper_completed_trades_valid_v08',
      'quarantine_source','alpha_hunter_paper_completed_trades_quarantine_v08',
      'clean_completed_trades',v_completed,
      'quarantined_completed_trades',v_quarantined,
      'quarantine_nonzero_invalidates_cohort',true,
      'post_start_scans',v_scan_count,
      'identity_drift_scans',v_drift_scans,
      'cadence_integrity_status',cad.cadence_integrity_status,
      'cadence_integrity_ok',cad.cadence_integrity_ok,
      'duplicate_active_exposure_groups',
        coalesce(integrity.duplicate_active_exposure_groups,0),
      'one_exposure_guard_integrity_ok',
        coalesce(integrity.one_exposure_guard_integrity_ok,false),
      'r8_execution_activation_id',exec_act.activation_id,
      'r8_execution_activation_fingerprint',
        exec_act.scientific_fingerprint_sha256,
      'cost_validation_status',cost.validation_status,
      'cost_validation_next_gate',cost.next_gate
    ),
    jsonb_build_object(
      'clean_wins',v_wins,
      'clean_nonwins',v_nonwins,
      'clean_win_rate_pct',v_win_rate,
      'gross_r_lower_95',v_gross_lower,
      'paper_net_r_ex_funding_avg',v_avg_net,
      'paper_net_r_ex_funding_lower_95',v_net_lower,
      'paper_net_r_ex_funding_profit_factor',v_net_pf,
      'paper_total_net_r_ex_funding',v_total_net_r,
      'paper_total_net_pnl_ex_funding_usdt',v_total_net_pnl,
      'paper_avg_net_pnl_ex_funding_usdt',v_avg_net_pnl,
      'duration_gate_met',v_days>=sp.minimum_test_days,
      'sample_gate_met',v_completed>=sp.minimum_completed_paper_trades,
      'executed_paper_edge_ex_funding_gate_met',
        (
          v_completed>=sp.minimum_completed_paper_trades
          and v_net_lower>0
          and coalesce(v_net_pf,0)>1.0
          and v_quarantined=0
        ),
      'full_cost_validation_evidence_complete',
        coalesce(cost.full_cost_validation_evidence_complete,false),
      'realistic_net_r_claim_permitted',v_realistic_claim
    ),
    true,true,false,false,true,
    false,false,false,false,'NONE'
  );

  return jsonb_build_object(
    'test_engine_run_id',v_id,
    'spec_id',sp.spec_id,
    'operational_status',v_operational_status,
    'profitability_status',v_profitability_status,
    'verdict',v_verdict,
    'completed_paper_trades',v_completed,
    'quarantined_completed_trades',v_quarantined,
    'clean_win_rate_pct',v_win_rate,
    'paper_net_r_ex_funding_lower_95',v_net_lower,
    'paper_net_r_ex_funding_profit_factor',v_net_pf,
    'blockers',to_jsonb(v_blockers),
    'paper_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_refresh_test_engine_v06_r8()
  from public;
grant execute on function private.alpha_hunter_refresh_test_engine_v06_r8()
  to postgres,service_role;

commit;
