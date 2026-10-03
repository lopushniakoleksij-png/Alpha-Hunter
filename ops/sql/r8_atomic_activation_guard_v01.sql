begin;

-- Alpha Hunter R8 atomic activation guard v0.1.
--
-- Scientific purpose:
--   Prevent the generic profitability activation job from starting the R8
--   profitability clock independently of the R8 paper-execution gate.
--
-- Activation contract:
--   one verified RENDER_CRON baseline
--   -> R8 paper execution activation
--   -> R8 cadence contract
--   -> R8 profitability activation
--   -> v0.6 executed-paper evaluator
-- all in one transaction, with exactly the same baseline timestamp/fingerprint.
--
-- No strategy thresholds, trade permission, exchange authority, or live order
-- path are changed.

create or replace function private.alpha_hunter_guard_r8_profitability_activation_v01()
returns trigger
language plpgsql
security definer
set search_path=''
as $function$
declare
  v_exec public.alpha_hunter_paper_execution_integrity_activation_v08%rowtype;
begin
  if new.spec_id<>'SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003' then
    return new;
  end if;

  select e.* into v_exec
  from public.alpha_hunter_paper_execution_integrity_activation_v08 e
  where e.activation_id='PAPER_EXECUTION_R8'
  order by e.activated_at_utc desc
  limit 1;

  -- Generic activation remains fail-closed and quiet until the dedicated
  -- atomic R8 activation has created the matching execution row.
  if v_exec.activation_id is null then
    return null;
  end if;

  if v_exec.activated_at_utc<>new.started_at_utc then
    raise exception
      'R8 profitability activation timestamp must match paper execution activation';
  end if;

  if coalesce(v_exec.scientific_fingerprint_sha256,'')
     <>coalesce(new.baseline_scientific_fingerprint_sha256,'')
  then
    raise exception
      'R8 profitability activation fingerprint must match paper execution activation';
  end if;

  return new;
end;
$function$;

revoke all on function private.alpha_hunter_guard_r8_profitability_activation_v01()
from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_r8_profitability_activation_interlock_v01
on public.alpha_hunter_profitability_test_activations_v01;

create trigger trg_ah_r8_profitability_activation_interlock_v01
before insert on public.alpha_hunter_profitability_test_activations_v01
for each row execute function private.alpha_hunter_guard_r8_profitability_activation_v01();


create or replace view public.alpha_hunter_r8_activation_readiness_v01
with (security_invoker=true,security_barrier=true)
as
with spec as (
  select s.*
  from public.alpha_hunter_profitability_test_specs_v01 s
  where s.spec_id='SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003'
),
candidate as (
  select
    p.run_id,
    p.collected_at_utc,
    p.payload->'validation_identity'->>'git_commit' as git_commit,
    p.payload->'validation_identity'->>'config_sha256' as config_sha256,
    p.payload->'validation_identity'->>'run_source' as run_source,
    p.payload->'validation_identity'->>'runtime_role' as runtime_role,
    p.payload->'validation_identity'->>'scientific_fingerprint_sha256'
      as scientific_fingerprint_sha256,
    p.payload->'previous_snapshot_context'->>'source' as previous_snapshot_source,
    p.payload->'catalyst_summary'->>'version' as catalyst_version,
    coalesce(
      nullif(p.payload->'multi_strategy_summary'->>'configured_strategy_count','')::integer,
      0
    ) as configured_strategy_count,
    coalesce(
      nullif(p.payload->'multi_strategy_summary'->>'total_evaluations','')::integer,
      0
    ) as total_strategy_evaluations
  from public.alpha_hunter_snapshots p
  cross join spec s
  where p.collected_at_utc>=s.preregistered_at_utc
    and p.payload->'validation_identity'->>'run_source'=s.required_run_source
    and p.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
    and p.payload->'validation_identity'->>'scientific_fingerprint_sha256'
        =s.frozen_scientific_fingerprint_sha256
  order by p.collected_at_utc
  limit 1
),
deployment as (
  select d.*
  from public.alpha_hunter_production_deployment_runtime_status_v03 d
  order by d.checked_at_utc desc
  limit 1
)
select
  s.spec_id,
  s.preregistered_at_utc,
  s.frozen_git_commit,
  s.frozen_scientific_fingerprint_sha256,
  c.run_id as candidate_run_id,
  c.collected_at_utc as candidate_scan_at_utc,
  c.git_commit as candidate_git_commit,
  c.config_sha256 as candidate_config_sha256,
  c.run_source as candidate_run_source,
  c.runtime_role as candidate_runtime_role,
  c.scientific_fingerprint_sha256 as candidate_scientific_fingerprint_sha256,
  c.previous_snapshot_source,
  c.catalyst_version,
  c.configured_strategy_count,
  c.total_strategy_evaluations,
  d.deployment_status,
  d.deployment_drift,
  d.target_runtime_fingerprint_sha256,
  d.live_runtime_fingerprint_sha256,
  exists(
    select 1
    from public.alpha_hunter_paper_execution_integrity_activation_v08 e
    where e.activation_id='PAPER_EXECUTION_R8'
  ) as paper_execution_activation_exists,
  exists(
    select 1
    from public.alpha_hunter_profitability_test_activations_v01 a
    where a.spec_id=s.spec_id
  ) as profitability_activation_exists,
  (
    c.run_id is not null
    and c.run_source='RENDER_CRON'
    and c.runtime_role='RENDER_CRON'
    and c.scientific_fingerprint_sha256=s.frozen_scientific_fingerprint_sha256
    and c.configured_strategy_count=s.required_strategy_count
    and c.total_strategy_evaluations>0
    and coalesce(c.previous_snapshot_source,'NONE')<>'NONE'
    and c.catalyst_version='0.2'
    and coalesce(d.deployment_drift,true)=false
  ) as baseline_identity_ready,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from spec s
left join candidate c on true
left join deployment d on true;

revoke all on public.alpha_hunter_r8_activation_readiness_v01
from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r8_activation_readiness_v01
to service_role;


create or replace function private.alpha_hunter_activate_r8_executed_paper_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $function$
declare
  v_spec public.alpha_hunter_profitability_test_specs_v01%rowtype;
  v_parent public.alpha_hunter_snapshots%rowtype;
  v_deploy public.alpha_hunter_production_deployment_runtime_status_v03%rowtype;
  v_existing_exec public.alpha_hunter_paper_execution_integrity_activation_v08%rowtype;
  v_existing_profit public.alpha_hunter_profitability_test_activations_v01%rowtype;
  v_valid_symbols integer:=0;
  v_strategy_rows integer:=0;
  v_micro_rows integer:=0;
  v_closed_rows integer:=0;
  v_previous_source text:='NONE';
  v_catalyst_version text:='';
  v_config_sha text:='';
  v_git text:='';
  v_fingerprint text:='';
  v_baseline timestamptz;
  v_jobid bigint;
begin
  select s.* into v_spec
  from public.alpha_hunter_profitability_test_specs_v01 s
  where s.spec_id='SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003';

  if v_spec.spec_id is null then
    raise exception 'R8 executed-paper profitability spec is missing';
  end if;

  select e.* into v_existing_exec
  from public.alpha_hunter_paper_execution_integrity_activation_v08 e
  where e.activation_id='PAPER_EXECUTION_R8'
  order by e.activated_at_utc desc
  limit 1;

  select a.* into v_existing_profit
  from public.alpha_hunter_profitability_test_activations_v01 a
  where a.spec_id=v_spec.spec_id
  order by a.activated_at_utc desc
  limit 1;

  if v_existing_exec.activation_id is not null
     and v_existing_profit.spec_id is not null
  then
    if v_existing_exec.activated_at_utc<>v_existing_profit.started_at_utc
       or coalesce(v_existing_exec.scientific_fingerprint_sha256,'')
          <>coalesce(v_existing_profit.baseline_scientific_fingerprint_sha256,'')
    then
      raise exception 'R8 existing activation rows are misaligned';
    end if;

    return jsonb_build_object(
      'status','ALREADY_ACTIVATED',
      'baseline_run_id',v_existing_profit.baseline_run_id,
      'started_at_utc',v_existing_profit.started_at_utc,
      'scientific_fingerprint_sha256',
        v_existing_profit.baseline_scientific_fingerprint_sha256,
      'paper_only',true,
      'trade_permission',false,
      'production_promotion_permitted',false,
      'order_path','NONE'
    );
  end if;

  if (v_existing_exec.activation_id is null)
     <> (v_existing_profit.spec_id is null)
  then
    raise exception 'R8 partial activation state detected; refusing non-atomic repair';
  end if;

  select d.* into v_deploy
  from public.alpha_hunter_production_deployment_runtime_status_v03 d
  order by d.checked_at_utc desc
  limit 1;

  if v_deploy.checked_at_utc is null then
    raise exception 'R8 deployment truth evidence is missing';
  end if;

  if coalesce(v_deploy.deployment_drift,true) then
    raise exception 'R8 production runtime is still in deployment drift';
  end if;

  select p.* into v_parent
  from public.alpha_hunter_snapshots p
  where p.collected_at_utc>=v_spec.preregistered_at_utc
    and p.payload->'validation_identity'->>'run_source'=v_spec.required_run_source
    and p.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
    and p.payload->'validation_identity'->>'scientific_fingerprint_sha256'
        =v_spec.frozen_scientific_fingerprint_sha256
    and coalesce(
      nullif(p.payload->'multi_strategy_summary'->>'configured_strategy_count','')::integer,
      0
    )=v_spec.required_strategy_count
    and coalesce(
      nullif(p.payload->'multi_strategy_summary'->>'total_evaluations','')::integer,
      0
    )>0
    and coalesce(p.payload->'previous_snapshot_context'->>'source','NONE')<>'NONE'
    and coalesce(p.payload->'catalyst_summary'->>'version','')='0.2'
  order by p.collected_at_utc
  limit 1;

  if v_parent.run_id is null then
    raise exception
      'No post-preregistration canonical RENDER_CRON run matches the R8 scientific fingerprint';
  end if;

  select
    count(*) filter(where c.error is null),
    count(*) filter(
      where c.error is null
        and jsonb_typeof(c.payload->'multi_strategy_engine')='object'
    ),
    count(*) filter(
      where c.error is null
        and jsonb_typeof(c.payload->'microstructure')='object'
    ),
    count(*) filter(
      where c.error is null
        and jsonb_typeof(c.payload->'timeframes'->'1H'->'last_closed_candle')='object'
    )
  into
    v_valid_symbols,v_strategy_rows,v_micro_rows,v_closed_rows
  from public.alpha_hunter_symbol_snapshots c
  where c.run_id=v_parent.run_id;

  if v_valid_symbols=0
     or v_strategy_rows<>v_valid_symbols
     or v_micro_rows<>v_valid_symbols
     or v_closed_rows<>v_valid_symbols
  then
    raise exception 'R8 canonical baseline child evidence is incomplete';
  end if;

  v_previous_source:=coalesce(
    v_parent.payload->'previous_snapshot_context'->>'source',
    'NONE'
  );
  v_catalyst_version:=coalesce(
    v_parent.payload->'catalyst_summary'->>'version',
    ''
  );
  v_config_sha:=coalesce(
    v_parent.payload->'validation_identity'->>'config_sha256',
    ''
  );
  v_git:=coalesce(
    v_parent.payload->'validation_identity'->>'git_commit',
    ''
  );
  v_fingerprint:=coalesce(
    v_parent.payload->'validation_identity'->>'scientific_fingerprint_sha256',
    ''
  );
  v_baseline:=v_parent.collected_at_utc;

  if v_config_sha='' or v_git='' then
    raise exception 'R8 canonical baseline build/config identity is incomplete';
  end if;

  if v_fingerprint<>v_spec.frozen_scientific_fingerprint_sha256 then
    raise exception 'R8 canonical baseline scientific fingerprint mismatch';
  end if;

  insert into public.alpha_hunter_paper_execution_integrity_activation_v08(
    activation_id,
    activated_at_utc,
    release_git_commit,
    scientific_fingerprint_sha256,
    maximum_entry_age_minutes,
    maximum_monitoring_gap_minutes,
    required_run_source,
    required_runtime_role,
    evidence,
    scientific_role,
    paper_only,
    exchange_authority,
    trade_permission,
    production_promotion_permitted,
    order_path
  ) values (
    'PAPER_EXECUTION_R8',
    v_baseline,
    v_git,
    v_fingerprint,
    35,
    35,
    'RENDER_CRON',
    'RENDER_CRON',
    jsonb_build_object(
      'baseline_run_id',v_parent.run_id,
      'baseline_scan_at_utc',v_baseline,
      'baseline_git_commit',v_git,
      'baseline_config_sha256',v_config_sha,
      'baseline_scientific_fingerprint_sha256',v_fingerprint,
      'deployment_status',v_deploy.deployment_status,
      'deployment_drift',v_deploy.deployment_drift,
      'target_runtime_fingerprint_sha256',
        v_deploy.target_runtime_fingerprint_sha256,
      'live_runtime_fingerprint_sha256',
        v_deploy.live_runtime_fingerprint_sha256,
      'atomic_activation',true,
      'historical_rows_reused',false
    ),
    'PAPER_EXECUTION_R8_INTEGRITY_ACTIVATION',
    true,false,false,false,'NONE'
  );

  insert into public.alpha_hunter_profitability_cadence_contract_v01(
    spec_id,
    baseline_not_before_utc,
    expected_frequency_minutes,
    minimum_interval_minutes,
    maximum_interval_minutes,
    expected_schedule,
    no_manual_scans_after_baseline,
    scientific_role,
    frozen,
    trade_permission,
    production_promotion_permitted,
    order_path
  ) values (
    v_spec.spec_id,
    v_baseline,
    20,
    15,
    35,
    'RENDER_CRON_ALIGNED_00_20_40',
    true,
    'SEALED_SCAN_CADENCE_CONTRACT_R8',
    true,false,false,'NONE'
  );

  insert into public.alpha_hunter_profitability_test_activations_v01(
    spec_id,
    baseline_run_id,
    started_at_utc,
    baseline_config_sha256,
    baseline_git_commit,
    baseline_previous_snapshot_source,
    baseline_catalyst_version,
    baseline_symbol_rows,
    baseline_strategy_rows,
    baseline_microstructure_rows,
    baseline_closed_candle_rows,
    activation_checks,
    baseline_scientific_fingerprint_sha256,
    scientific_role,
    shadow_only,
    trade_permission,
    production_promotion_permitted,
    order_path
  ) values (
    v_spec.spec_id,
    v_parent.run_id,
    v_baseline,
    v_config_sha,
    v_git,
    v_previous_source,
    v_catalyst_version,
    v_valid_symbols,
    v_strategy_rows,
    v_micro_rows,
    v_closed_rows,
    jsonb_build_object(
      'atomic_r8_activation',true,
      'paper_execution_activation_aligned',true,
      'cadence_contract_aligned',true,
      'preregistration_boundary_ok',
        v_baseline>=v_spec.preregistered_at_utc,
      'identity_mode','SCIENTIFIC_FINGERPRINT',
      'scientific_fingerprint_ok',true,
      'git_anchor_commit',v_spec.frozen_git_commit,
      'baseline_observed_git_commit',v_git,
      'strategy_count_ok',true,
      'previous_context_ok',true,
      'catalyst_v02_ok',true,
      'strategy_rows_complete',true,
      'microstructure_rows_complete',true,
      'closed_candle_rows_complete',true,
      'deployment_status',v_deploy.deployment_status,
      'deployment_drift',v_deploy.deployment_drift,
      'sample_source','alpha_hunter_paper_completed_trades_valid_v08',
      'quarantine_source','alpha_hunter_paper_completed_trades_quarantine_v08',
      'quarantine_nonzero_invalidates_cohort',true
    ),
    v_fingerprint,
    'SEALED_PROFITABILITY_ACTIVATION_R8_EXECUTED_PAPER',
    true,false,false,'NONE'
  );

  select j.jobid into strict v_jobid
  from cron.job j
  where j.jobname='alpha-hunter-test-engine-db-refresh-v02';

  perform cron.alter_job(
    v_jobid,
    schedule:='5,25,45 * * * *',
    command:='select private.alpha_hunter_refresh_test_engine_v06_r8();',
    active:=true
  );

  return jsonb_build_object(
    'status','ACTIVATED',
    'spec_id',v_spec.spec_id,
    'baseline_run_id',v_parent.run_id,
    'started_at_utc',v_baseline,
    'baseline_git_commit',v_git,
    'scientific_fingerprint_sha256',v_fingerprint,
    'valid_symbol_rows',v_valid_symbols,
    'strategy_rows',v_strategy_rows,
    'microstructure_rows',v_micro_rows,
    'closed_candle_rows',v_closed_rows,
    'test_engine','private.alpha_hunter_refresh_test_engine_v06_r8',
    'paper_only',true,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_activate_r8_executed_paper_v01()
from public,anon,authenticated,service_role;

commit;
