-- R10 non-scientific descendant activation bridge v0.1
--
-- Purpose:
-- - preserve the preregistered R10 scientific fingerprint and frozen Git anchor;
-- - allow owner-approved descendant commits only when the runtime science is unchanged;
-- - keep runtime Git identity truthful rather than relabeling the live commit;
-- - preserve R9 closure, fail-closed evidence, paper-only authority, and atomic R10 activation.
--
-- This migration does not change strategy, entry, risk, R:R, cadence, execution
-- authority, exchange authority, or the scientific fingerprint.
begin;

create table if not exists public.alpha_hunter_r10_runtime_commit_approvals_v01 (
  approval_id text primary key,
  registration_id text not null
    references public.alpha_hunter_r10_preregistrations_v01(registration_id)
    on delete restrict,
  frozen_git_commit text not null check(frozen_git_commit ~ '^[a-f0-9]{40}$'),
  approved_runtime_git_commit text not null check(approved_runtime_git_commit ~ '^[a-f0-9]{40}$'),
  scientific_fingerprint_sha256 text not null
    check(scientific_fingerprint_sha256 ~ '^[a-f0-9]{64}$'),
  approved_at_utc timestamptz not null default clock_timestamp(),
  reason text not null check(length(reason)>0),
  evidence jsonb not null check(jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check(paper_only),
  exchange_authority boolean not null default false check(not exchange_authority),
  trade_permission boolean not null default false check(not trade_permission),
  production_promotion_permitted boolean not null default false
    check(not production_promotion_permitted),
  order_path text not null default 'NONE' check(order_path='NONE'),
  unique(registration_id,approved_runtime_git_commit),
  check(frozen_git_commit<>approved_runtime_git_commit)
);

alter table public.alpha_hunter_r10_runtime_commit_approvals_v01 enable row level security;
revoke all on public.alpha_hunter_r10_runtime_commit_approvals_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r10_runtime_commit_approvals_v01 to service_role;

drop trigger if exists trg_ah_r10_runtime_commit_approvals_append_only_v01
on public.alpha_hunter_r10_runtime_commit_approvals_v01;
create trigger trg_ah_r10_runtime_commit_approvals_append_only_v01
before update or delete on public.alpha_hunter_r10_runtime_commit_approvals_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace view public.alpha_hunter_r10_activation_readiness_v01
with(security_invoker=true,security_barrier=true) as
select
  r.registration_id,
  r.spec_id,
  r.preregistered_at_utc,
  r.frozen_git_commit,
  r.frozen_scientific_fingerprint_sha256,
  r.protocol_version,
  v.verification_id,
  v.run_id as verified_run_id,
  v.scan_collected_at_utc as verified_scan_at_utc,
  v.previous_snapshot_source,
  v.previous_snapshot_run_id,
  (a.activation_id is not null) as activation_exists,
  (
    v.verification_id is not null
    and v.scan_collected_at_utc>r.preregistered_at_utc
    and (
      v.git_commit=r.frozen_git_commit
      or exists(
        select 1
        from public.alpha_hunter_r10_runtime_commit_approvals_v01 ca
        where ca.registration_id=r.registration_id
          and ca.frozen_git_commit=r.frozen_git_commit
          and ca.approved_runtime_git_commit=v.git_commit
          and ca.scientific_fingerprint_sha256=r.frozen_scientific_fingerprint_sha256
      )
    )
    and v.scientific_fingerprint_sha256=r.frozen_scientific_fingerprint_sha256
    and v.run_source=r.required_run_source
    and v.runtime_role=r.required_runtime_role
    and v.previous_snapshot_source<>'NONE'
    and v.configured_strategy_count=r.required_strategy_count
    and v.total_strategy_evaluations>0
    and v.unprotected_open_positions=0
    and v.r9_admission_open_rows=0
    and v.orders_after_r9_halt=0
    and not v.trade_permission_any
    and not v.exchange_authority_any
    and v.order_path_all_none
    and v.r10_spec_rows=1
    and v.r10_activation_rows_before=0
    and a.activation_id is null
  ) as ready_for_owner_activation,
  true as paper_only,
  false as exchange_authority,
  false as trade_permission,
  false as production_promotion_permitted,
  false as live_money_claim_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_r10_preregistrations_v01 r
left join public.alpha_hunter_r10_runtime_verifications_v01 v
  on v.registration_id=r.registration_id
 and v.spec_id=r.spec_id
left join public.alpha_hunter_paper_execution_activation_v10 a
  on a.activation_id=r.registration_id;

revoke all on public.alpha_hunter_r10_activation_readiness_v01
from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r10_activation_readiness_v01 to service_role;

create or replace function private.alpha_hunter_activate_r10_executed_paper_v01(
  p_registration_id text,
  p_verification_id text
)
returns jsonb
language plpgsql
security invoker
set search_path=''
as $function$
declare
  r public.alpha_hunter_r10_preregistrations_v01%rowtype;
  v public.alpha_hunter_r10_runtime_verifications_v01%rowtype;
  s public.alpha_hunter_profitability_test_specs_v01%rowtype;
  p public.alpha_hunter_snapshots%rowtype;
  existing public.alpha_hunter_paper_execution_activation_v10%rowtype;
  open_r9 integer:=0;
  after_halt integer:=0;
  current_protected integer:=0;
  current_r9_cohort integer:=0;
  current_integrity_failures integer:=0;
  current_trade_permission boolean:=false;
  current_exchange_authority boolean:=false;
  current_order_path_all_none boolean:=true;
  existing_profit integer:=0;
  existing_cadence integer:=0;
  valid_symbols integer:=0;
  strategy_rows integer:=0;
  microstructure_rows integer:=0;
  closed_rows integer:=0;
  previous_source text:='NONE';
  catalyst_version text:='';
  config_sha text:='';
  runtime_commit_approved boolean:=false;
  activated_at timestamptz;
begin
  if p_registration_id<>'PAPER_EXECUTION_R10' then
    raise exception 'R10 registration identity mismatch';
  end if;

  select * into r
  from public.alpha_hunter_r10_preregistrations_v01
  where registration_id=p_registration_id;

  if r.registration_id is null then
    raise exception 'R10 preregistration is missing';
  end if;

  select * into v
  from public.alpha_hunter_r10_runtime_verifications_v01
  where verification_id=p_verification_id
    and registration_id=r.registration_id
    and spec_id=r.spec_id;

  if v.verification_id is null then
    raise exception
      'R10 runtime verification is missing or does not match preregistration';
  end if;

  select * into s
  from public.alpha_hunter_profitability_test_specs_v01
  where spec_id=r.spec_id;

  if s.spec_id is null then
    raise exception 'R10 profitability spec is missing';
  end if;

  if s.scientific_role<>'SUCCESSOR_EXECUTED_PAPER_24H_R10'
     or s.protocol_version<>r.protocol_version
     or s.required_strategy_count<>r.required_strategy_count
     or s.required_minimum_rr<>r.required_minimum_rr
     or s.evaluation_horizon_hours<>r.evaluation_horizon_hours
     or s.minimum_test_days<>r.minimum_test_days
     or s.minimum_completed_paper_trades<>r.minimum_completed_paper_trades
     or s.confidence_z<>r.confidence_z
     or not s.require_validated_cost_model
     or not s.shadow_only
     or s.trade_permission
     or s.production_promotion_permitted
     or s.order_path<>'NONE'
     or s.required_run_source<>r.required_run_source
     or s.frozen_git_commit<>r.frozen_git_commit
     or s.frozen_scientific_fingerprint_sha256
        <>r.frozen_scientific_fingerprint_sha256
  then
    raise exception 'R10 frozen spec does not exactly match preregistration';
  end if;

  if s.preregistered_at_utc<>r.preregistered_at_utc then
    raise exception 'R10 spec/preregistration time boundary mismatch';
  end if;

  select * into p
  from public.alpha_hunter_snapshots
  where run_id=v.run_id;

  if p.run_id is null then
    raise exception 'R10 verified canonical snapshot is missing';
  end if;

  previous_source:=coalesce(
    p.payload->'previous_snapshot_context'->>'source','NONE'
  );
  catalyst_version:=coalesce(
    p.payload->'catalyst_summary'->>'version',''
  );
  config_sha:=coalesce(
    p.payload->'validation_identity'->>'config_sha256',''
  );

  select (
    v.git_commit=r.frozen_git_commit
    or exists(
      select 1
      from public.alpha_hunter_r10_runtime_commit_approvals_v01 ca
      where ca.registration_id=r.registration_id
        and ca.frozen_git_commit=r.frozen_git_commit
        and ca.approved_runtime_git_commit=v.git_commit
        and ca.scientific_fingerprint_sha256=r.frozen_scientific_fingerprint_sha256
    )
  ) into runtime_commit_approved;

  if p.collected_at_utc<>v.scan_collected_at_utc
     or p.collected_at_utc<=r.preregistered_at_utc
     or coalesce(p.payload->'validation_identity'->>'git_commit','')<>v.git_commit
     or not runtime_commit_approved
     or coalesce(
       p.payload->'validation_identity'->>'scientific_fingerprint_sha256',''
     )<>r.frozen_scientific_fingerprint_sha256
     or coalesce(p.payload->'validation_identity'->>'run_source','')
        <>r.required_run_source
     or coalesce(p.payload->'validation_identity'->>'runtime_role','')
        <>r.required_runtime_role
     or previous_source='NONE'
     or coalesce(p.payload->'previous_snapshot_context'->>'run_id','')=''
     or coalesce(
       nullif(
         p.payload->'multi_strategy_summary'->>'configured_strategy_count',''
       )::integer,0
     )<>r.required_strategy_count
     or coalesce(
       nullif(p.payload->'multi_strategy_summary'->>'total_evaluations','')
         ::integer,0
     )<=0
     or catalyst_version<>'0.2'
     or config_sha=''
  then
    raise exception
      'R10 verified snapshot does not satisfy frozen canonical identity/context';
  end if;

  if not runtime_commit_approved
     or v.scientific_fingerprint_sha256
        <>r.frozen_scientific_fingerprint_sha256
     or v.run_source<>r.required_run_source
     or v.runtime_role<>r.required_runtime_role
     or v.previous_snapshot_source='NONE'
     or v.previous_snapshot_run_id=''
     or v.configured_strategy_count<>r.required_strategy_count
     or v.total_strategy_evaluations<=0
     or v.unprotected_open_positions<>0
     or v.r9_admission_open_rows<>0
     or v.orders_after_r9_halt<>0
     or v.r9_cohort_rows<0
     or v.r9_integrity_failed_orders<0
     or v.trade_permission_any
     or v.exchange_authority_any
     or not v.order_path_all_none
     or v.r10_spec_rows<>1
     or v.r10_activation_rows_before<>0
  then
    raise exception 'R10 runtime verification fails owner activation contract';
  end if;

  select count(*) into open_r9
  from public.alpha_hunter_paper_admission_open_v09;

  if open_r9<>0 then
    raise exception 'R9 admission is unexpectedly open';
  end if;

  select count(*) into after_halt
  from public.alpha_hunter_paper_orders_v02 o
  cross join (
    select halted_at_utc
    from public.alpha_hunter_paper_admission_halts_v09
    where activation_id='PAPER_EXECUTION_R9'
  ) h
  where o.submitted_at_utc>h.halted_at_utc;

  if after_halt<>0 then
    raise exception 'Orders exist after R9 halt; refusing R10 activation';
  end if;

  select * into existing
  from public.alpha_hunter_paper_execution_activation_v10
  where activation_id=r.registration_id;

  select count(*) into existing_profit
  from public.alpha_hunter_profitability_test_activations_v01
  where spec_id=r.spec_id;

  select count(*) into existing_cadence
  from public.alpha_hunter_profitability_cadence_contract_v01
  where spec_id=r.spec_id;

  if existing.activation_id is not null
     or existing_profit<>0
     or existing_cadence<>0
  then
    raise exception
      'R10 activation/cadence/profitability state already exists or is partial';
  end if;

  activated_at:=clock_timestamp();

  if v.verified_at_utc<v.scan_collected_at_utc
     or activated_at<=v.verified_at_utc
     or activated_at-v.verified_at_utc
        >make_interval(mins=>r.maximum_activation_verification_age_minutes)
     or activated_at-v.scan_collected_at_utc
        >make_interval(mins=>r.maximum_monitoring_gap_minutes)
  then
    raise exception 'R10 activation verification is stale or temporally invalid';
  end if;

  select
    count(*)::integer,
    coalesce(bool_or(trade_permission),false),
    coalesce(bool_or(exchange_authority),false),
    coalesce(bool_and(order_path='NONE'),true)
  into
    current_protected,
    current_trade_permission,
    current_exchange_authority,
    current_order_path_all_none
  from public.alpha_hunter_paper_protection_horizon_open_v09;

  select count(*)::integer into current_r9_cohort
  from public.alpha_hunter_paper_cohort_members_v09;

  select coalesce(max(integrity_failed_orders),0)::integer
  into current_integrity_failures
  from public.alpha_hunter_paper_profitability_status_v09;

  if current_protected<>v.protected_open_positions
     or current_r9_cohort<>v.r9_cohort_rows
     or current_integrity_failures<>v.r9_integrity_failed_orders
     or current_trade_permission
     or current_exchange_authority
     or not current_order_path_all_none
  then
    raise exception 'R10 production state changed after runtime verification';
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
        and jsonb_typeof(
          c.payload->'timeframes'->'1H'->'last_closed_candle'
        )='object'
    )
  into valid_symbols,strategy_rows,microstructure_rows,closed_rows
  from public.alpha_hunter_symbol_snapshots c
  where c.run_id=v.run_id;

  if valid_symbols=0
     or strategy_rows<>valid_symbols
     or microstructure_rows<>valid_symbols
     or closed_rows<>valid_symbols
  then
    raise exception 'R10 verified canonical child evidence is incomplete';
  end if;

  insert into public.alpha_hunter_paper_execution_activation_v10(
    activation_id,spec_id,protocol_version,activated_at_utc,
    runtime_verified_at_utc,admission_cutoff_at_utc,
    release_git_commit,scientific_fingerprint_sha256,
    maximum_entry_age_minutes,maximum_monitoring_gap_minutes,
    horizon_hours,maximum_horizon_lag_minutes,
    required_run_source,required_runtime_role,evidence,
    paper_only,exchange_authority,trade_permission,
    production_promotion_permitted,order_path
  ) values (
    r.registration_id,r.spec_id,r.protocol_version,activated_at,
    v.verified_at_utc,
    activated_at+(r.admission_window_days||' days')::interval,
    v.git_commit,r.frozen_scientific_fingerprint_sha256,
    r.maximum_entry_age_minutes,r.maximum_monitoring_gap_minutes,
    r.evaluation_horizon_hours,r.maximum_horizon_lag_minutes,
    r.required_run_source,r.required_runtime_role,
    jsonb_build_object(
      'owner_only_activation',true,
      'frozen_git_commit',r.frozen_git_commit,
      'runtime_git_commit',v.git_commit,
      'non_scientific_descendant_approved',v.git_commit<>r.frozen_git_commit,
      'atomic_r10_activation',true,
      'preregistration_id',r.registration_id,
      'verification_id',v.verification_id,
      'verified_run_id',v.run_id,
      'verified_scan_at_utc',v.scan_collected_at_utc,
      'previous_snapshot_source',v.previous_snapshot_source,
      'previous_snapshot_run_id',v.previous_snapshot_run_id,
      'verified_protected_open_positions',v.protected_open_positions,
      'verified_r9_cohort_rows',v.r9_cohort_rows,
      'verified_r9_integrity_failed_orders',v.r9_integrity_failed_orders,
      'historical_rows_reused',false,
      'r9_reopened',false
    ),
    true,false,false,false,'NONE'
  );

  insert into public.alpha_hunter_profitability_cadence_contract_v01(
    spec_id,baseline_not_before_utc,
    expected_frequency_minutes,minimum_interval_minutes,
    maximum_interval_minutes,expected_schedule,
    no_manual_scans_after_baseline,scientific_role,
    frozen,trade_permission,production_promotion_permitted,order_path
  ) values (
    r.spec_id,
    activated_at,
    20,15,35,
    'RENDER_CRON_ALIGNED_00_20_40',
    true,
    'SEALED_SCAN_CADENCE_CONTRACT_R10',
    true,false,false,'NONE'
  );

  insert into public.alpha_hunter_profitability_test_activations_v01(
    spec_id,baseline_run_id,started_at_utc,
    baseline_config_sha256,baseline_git_commit,
    baseline_previous_snapshot_source,baseline_catalyst_version,
    baseline_symbol_rows,baseline_strategy_rows,
    baseline_microstructure_rows,baseline_closed_candle_rows,
    activation_checks,baseline_scientific_fingerprint_sha256,
    scientific_role,shadow_only,trade_permission,
    production_promotion_permitted,order_path
  ) values (
    r.spec_id,
    v.run_id,
    activated_at,
    config_sha,
    r.frozen_git_commit,
    previous_source,
    catalyst_version,
    valid_symbols,
    strategy_rows,
    microstructure_rows,
    closed_rows,
    jsonb_build_object(
      'atomic_r10_activation',true,
      'paper_execution_activation_aligned',true,
      'cadence_contract_aligned',true,
      'preregistration_boundary_ok',
        v.scan_collected_at_utc>r.preregistered_at_utc,
      'identity_mode','SCIENTIFIC_FINGERPRINT',
      'scientific_fingerprint_ok',true,
      'git_anchor_commit',r.frozen_git_commit,
      'baseline_observed_git_commit',
        p.payload->'validation_identity'->>'git_commit',
      'previous_context_ok',previous_source<>'NONE',
      'strategy_count_ok',true,
      'strategy_rows_complete',strategy_rows=valid_symbols,
      'microstructure_rows_complete',microstructure_rows=valid_symbols,
      'closed_candle_rows_complete',closed_rows=valid_symbols,
      'sample_source','alpha_hunter_paper_completed_trades_valid_v10',
      'quarantine_source','alpha_hunter_paper_completed_trades_quarantine_v10',
      'quarantine_nonzero_invalidates_cohort',true,
      'historical_rows_reused',false
    ),
    r.frozen_scientific_fingerprint_sha256,
    'SEALED_PROFITABILITY_ACTIVATION_R10_EXECUTED_PAPER',
    true,false,false,'NONE'
  );

  return jsonb_build_object(
    'status','ACTIVATED',
    'activation_id',r.registration_id,
    'spec_id',r.spec_id,
    'verified_run_id',v.run_id,
    'runtime_git_commit',v.git_commit,
    'frozen_git_commit',r.frozen_git_commit,
    'started_at_utc',activated_at,
    'scientific_fingerprint_sha256',
      r.frozen_scientific_fingerprint_sha256,
    'paper_only',true,
    'exchange_authority',false,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'live_money_claim_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function
private.alpha_hunter_activate_r10_executed_paper_v01(text,text)
from public,anon,authenticated,service_role;


commit;
