begin;

-- R10 preregistration + owner-only activation interlock v0.1.
--
-- INACTIVE BY DEFAULT:
-- - creates no R10 spec row;
-- - creates no preregistration row;
-- - creates no runtime-verification row;
-- - creates no paper-execution activation;
-- - does not open R10 admission;
-- - does not alter live/exchange authority.
--
-- Only a privileged owner can insert preregistration/runtime-verification evidence
-- or execute the activation function. service_role can read status only.

create table if not exists public.alpha_hunter_r10_preregistrations_v01 (
  registration_id text primary key
    check(registration_id='PAPER_EXECUTION_R10'),
  spec_id text not null unique
    references public.alpha_hunter_profitability_test_specs_v01(spec_id)
    on delete restrict,
  preregistered_at_utc timestamptz not null,
  frozen_git_commit text not null
    check(frozen_git_commit ~ '^[a-f0-9]{40}$'),
  frozen_scientific_fingerprint_sha256 text not null
    check(frozen_scientific_fingerprint_sha256 ~ '^[a-f0-9]{64}$'),
  protocol_version text not null
    check(protocol_version='paper-horizon-24h-v0.1'),
  required_run_source text not null default 'RENDER_CRON'
    check(required_run_source='RENDER_CRON'),
  required_runtime_role text not null default 'RENDER_CRON'
    check(required_runtime_role='RENDER_CRON'),
  required_strategy_count integer not null default 10
    check(required_strategy_count=10),
  required_minimum_rr numeric not null default 5
    check(required_minimum_rr=5),
  evaluation_horizon_hours integer not null default 24
    check(evaluation_horizon_hours=24),
  minimum_test_days integer not null default 30
    check(minimum_test_days=30),
  minimum_completed_paper_trades integer not null default 100
    check(minimum_completed_paper_trades=100),
  maximum_entry_age_minutes integer not null default 35
    check(maximum_entry_age_minutes=35),
  maximum_monitoring_gap_minutes integer not null default 35
    check(maximum_monitoring_gap_minutes=35),
  maximum_horizon_lag_minutes integer not null default 35
    check(maximum_horizon_lag_minutes=35),
  require_validated_cost_model boolean not null default true
    check(require_validated_cost_model),
  admission_window_days integer not null default 30
    check(admission_window_days=30),
  evidence jsonb not null check(jsonb_typeof(evidence)='object'),
  scientific_role text not null default 'SUCCESSOR_EXECUTED_PAPER_24H_R10'
    check(scientific_role='SUCCESSOR_EXECUTED_PAPER_24H_R10'),
  paper_only boolean not null default true check(paper_only),
  exchange_authority boolean not null default false check(not exchange_authority),
  trade_permission boolean not null default false check(not trade_permission),
  production_promotion_permitted boolean not null default false
    check(not production_promotion_permitted),
  live_money_claim_permitted boolean not null default false
    check(not live_money_claim_permitted),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_r10_preregistrations_v01 enable row level security;
revoke all on public.alpha_hunter_r10_preregistrations_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r10_preregistrations_v01 to service_role;

drop trigger if exists trg_ah_r10_preregistrations_append_only_v01
on public.alpha_hunter_r10_preregistrations_v01;
create trigger trg_ah_r10_preregistrations_append_only_v01
before update or delete on public.alpha_hunter_r10_preregistrations_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create table if not exists public.alpha_hunter_r10_runtime_verifications_v01 (
  verification_id text primary key,
  registration_id text not null
    references public.alpha_hunter_r10_preregistrations_v01(registration_id)
    on delete restrict,
  spec_id text not null,
  run_id text not null unique,
  verified_at_utc timestamptz not null,
  scan_collected_at_utc timestamptz not null,
  git_commit text not null check(git_commit ~ '^[a-f0-9]{40}$'),
  scientific_fingerprint_sha256 text not null
    check(scientific_fingerprint_sha256 ~ '^[a-f0-9]{64}$'),
  run_source text not null check(run_source='RENDER_CRON'),
  runtime_role text not null check(runtime_role='RENDER_CRON'),
  previous_snapshot_source text not null
    check(previous_snapshot_source<>'NONE' and length(previous_snapshot_source)>0),
  previous_snapshot_run_id text not null
    check(length(previous_snapshot_run_id)>0),
  configured_strategy_count integer not null check(configured_strategy_count=10),
  total_strategy_evaluations integer not null check(total_strategy_evaluations>0),
  protected_open_positions integer not null check(protected_open_positions>=0),
  unprotected_open_positions integer not null check(unprotected_open_positions=0),
  r9_admission_open_rows integer not null check(r9_admission_open_rows=0),
  orders_after_r9_halt integer not null check(orders_after_r9_halt=0),
  trade_permission_any boolean not null check(not trade_permission_any),
  exchange_authority_any boolean not null check(not exchange_authority_any),
  order_path_all_none boolean not null check(order_path_all_none),
  r10_spec_rows integer not null check(r10_spec_rows=1),
  r10_activation_rows_before integer not null check(r10_activation_rows_before=0),
  evidence jsonb not null check(jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check(paper_only),
  trade_permission boolean not null default false check(not trade_permission),
  exchange_authority boolean not null default false check(not exchange_authority),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp(),
  unique(registration_id,spec_id)
);

alter table public.alpha_hunter_r10_runtime_verifications_v01 enable row level security;
revoke all on public.alpha_hunter_r10_runtime_verifications_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r10_runtime_verifications_v01 to service_role;

drop trigger if exists trg_ah_r10_runtime_verifications_append_only_v01
on public.alpha_hunter_r10_runtime_verifications_v01;
create trigger trg_ah_r10_runtime_verifications_append_only_v01
before update or delete on public.alpha_hunter_r10_runtime_verifications_v01
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
    and v.git_commit=r.frozen_git_commit
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
    raise exception 'R10 runtime verification is missing or does not match preregistration';
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
     or not s.require_validated_cost_model
     or s.required_run_source<>r.required_run_source
     or s.frozen_git_commit<>r.frozen_git_commit
     or s.frozen_scientific_fingerprint_sha256<>r.frozen_scientific_fingerprint_sha256
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

  if p.collected_at_utc<>v.scan_collected_at_utc
     or p.collected_at_utc<=r.preregistered_at_utc
     or coalesce(p.payload->'validation_identity'->>'git_commit','')<>r.frozen_git_commit
     or coalesce(p.payload->'validation_identity'->>'scientific_fingerprint_sha256','')
        <>r.frozen_scientific_fingerprint_sha256
     or coalesce(p.payload->'validation_identity'->>'run_source','')<>r.required_run_source
     or coalesce(p.payload->'validation_identity'->>'runtime_role','')<>r.required_runtime_role
     or coalesce(p.payload->'previous_snapshot_context'->>'source','NONE')='NONE'
     or coalesce(p.payload->'previous_snapshot_context'->>'run_id','')=''
     or coalesce(
       nullif(p.payload->'multi_strategy_summary'->>'configured_strategy_count','')::integer,
       0
     )<>r.required_strategy_count
     or coalesce(
       nullif(p.payload->'multi_strategy_summary'->>'total_evaluations','')::integer,
       0
     )<=0
  then
    raise exception 'R10 verified snapshot does not satisfy frozen canonical identity/context';
  end if;

  if v.git_commit<>r.frozen_git_commit
     or v.scientific_fingerprint_sha256<>r.frozen_scientific_fingerprint_sha256
     or v.run_source<>r.required_run_source
     or v.runtime_role<>r.required_runtime_role
     or v.previous_snapshot_source='NONE'
     or v.previous_snapshot_run_id=''
     or v.configured_strategy_count<>r.required_strategy_count
     or v.total_strategy_evaluations<=0
     or v.unprotected_open_positions<>0
     or v.r9_admission_open_rows<>0
     or v.orders_after_r9_halt<>0
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

  if existing.activation_id is not null then
    raise exception 'R10 is already activated';
  end if;

  insert into public.alpha_hunter_paper_execution_activation_v10(
    activation_id,
    spec_id,
    protocol_version,
    activated_at_utc,
    runtime_verified_at_utc,
    admission_cutoff_at_utc,
    release_git_commit,
    scientific_fingerprint_sha256,
    maximum_entry_age_minutes,
    maximum_monitoring_gap_minutes,
    horizon_hours,
    maximum_horizon_lag_minutes,
    required_run_source,
    required_runtime_role,
    evidence,
    paper_only,
    exchange_authority,
    trade_permission,
    production_promotion_permitted,
    order_path
  ) values (
    r.registration_id,
    r.spec_id,
    r.protocol_version,
    clock_timestamp(),
    v.verified_at_utc,
    clock_timestamp()+(r.admission_window_days||' days')::interval,
    r.frozen_git_commit,
    r.frozen_scientific_fingerprint_sha256,
    r.maximum_entry_age_minutes,
    r.maximum_monitoring_gap_minutes,
    r.evaluation_horizon_hours,
    r.maximum_horizon_lag_minutes,
    r.required_run_source,
    r.required_runtime_role,
    jsonb_build_object(
      'owner_only_activation',true,
      'preregistration_id',r.registration_id,
      'verification_id',v.verification_id,
      'verified_run_id',v.run_id,
      'verified_scan_at_utc',v.scan_collected_at_utc,
      'previous_snapshot_source',v.previous_snapshot_source,
      'previous_snapshot_run_id',v.previous_snapshot_run_id,
      'historical_rows_reused',false,
      'r9_reopened',false
    ),
    true,false,false,false,'NONE'
  );

  return jsonb_build_object(
    'status','ACTIVATED',
    'activation_id',r.registration_id,
    'spec_id',r.spec_id,
    'verified_run_id',v.run_id,
    'scientific_fingerprint_sha256',r.frozen_scientific_fingerprint_sha256,
    'paper_only',true,
    'exchange_authority',false,
    'trade_permission',false,
    'production_promotion_permitted',false,
    'live_money_claim_permitted',false,
    'order_path','NONE'
  );
end;
$function$;

revoke all on function private.alpha_hunter_activate_r10_executed_paper_v01(text,text)
from public,anon,authenticated,service_role;

commit;
