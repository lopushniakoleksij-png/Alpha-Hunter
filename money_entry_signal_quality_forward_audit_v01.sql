-- Alpha Hunter Money Entry signal-quality forward audit v0.1
--
-- Continuous shadow-only verification of the permanent execution signal-quality
-- contract. This audit does not score trades, activate thresholds, grant trade
-- permission, or create an order path.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

create table if not exists public.alpha_hunter_signal_quality_forward_audits (
  audit_id text primary key,
  hour_bucket_utc timestamptz not null,
  audited_at_utc timestamptz not null default clock_timestamp(),
  source_run_id text,
  stage_rows integer not null default 0 check (stage_rows >= 0),
  eligible_rows integer not null default 0 check (eligible_rows >= 0),
  eligible_direction_failures integer not null default 0 check (eligible_direction_failures >= 0),
  eligible_momentum_failures integer not null default 0 check (eligible_momentum_failures >= 0),
  eligible_integrity_failures integer not null default 0 check (eligible_integrity_failures >= 0),
  signal_quality_blocked_rows integer not null default 0 check (signal_quality_blocked_rows >= 0),
  safety_boundary_violations integer not null default 0 check (safety_boundary_violations >= 0),
  invariant_pass boolean not null,
  evidence jsonb not null default '{}'::jsonb check (jsonb_typeof(evidence)='object'),
  model_version text not null default 'money-entry-signal-quality-forward-audit-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp(),
  unique(hour_bucket_utc)
);

alter table public.alpha_hunter_signal_quality_forward_audits enable row level security;
revoke all on table public.alpha_hunter_signal_quality_forward_audits from public, anon, authenticated;
grant select, insert on table public.alpha_hunter_signal_quality_forward_audits to service_role;

drop trigger if exists trg_ah_signal_quality_forward_audits_append_only
  on public.alpha_hunter_signal_quality_forward_audits;
create trigger trg_ah_signal_quality_forward_audits_append_only
before update or delete on public.alpha_hunter_signal_quality_forward_audits
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_run_signal_quality_forward_audit()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_hour timestamptz := date_trunc('hour', clock_timestamp());
  v_source_run_id text;
  v_stage_rows integer := 0;
  v_eligible integer := 0;
  v_direction_fail integer := 0;
  v_momentum_fail integer := 0;
  v_integrity_fail integer := 0;
  v_blocked integer := 0;
  v_safety integer := 0;
  v_pass boolean := false;
  v_audit_id text;
begin
  select s.source_run_id
    into v_source_run_id
  from public.alpha_hunter_money_entry_stage_snapshots s
  order by s.source_captured_at_utc desc, s.created_at desc
  limit 1;

  if v_source_run_id is not null then
    select
      count(*)::integer,
      count(*) filter (where s.stage_eligible)::integer,
      count(*) filter (where s.stage_eligible and s.scanner_direction_aligned is not true)::integer,
      count(*) filter (where s.stage_eligible and s.scanner_momentum_confirmed is not true)::integer,
      count(*) filter (where s.stage_eligible and s.scanner_data_integrity_pass is not true)::integer,
      count(*) filter (
        where s.stage_status='NO_T0'
          and (
            s.blockers ? 'SCANNER_DIRECTION_ALIGNMENT_NOT_CAPTURED'
            or s.blockers ? 'SCANNER_DIRECTION_NOT_ALIGNED'
            or s.blockers ? 'SCANNER_MOMENTUM_NOT_CAPTURED'
            or s.blockers ? 'SCANNER_MOMENTUM_NOT_CONFIRMED'
            or s.blockers ? 'SCANNER_DATA_INTEGRITY_NOT_CAPTURED'
            or s.blockers ? 'SCANNER_DATA_INTEGRITY_NOT_VERIFIED'
          )
      )::integer
    into v_stage_rows, v_eligible, v_direction_fail, v_momentum_fail, v_integrity_fail, v_blocked
    from public.alpha_hunter_money_entry_stage_snapshots s
    where s.source_run_id=v_source_run_id;
  end if;

  select count(*)::integer into v_safety
  from public.alpha_hunter_money_entry_stage_snapshots s
  where s.shadow_only is not true or s.trade_permission is not false;

  v_pass := (
    v_direction_fail=0
    and v_momentum_fail=0
    and v_integrity_fail=0
    and v_safety=0
  );

  v_audit_id := md5('money-entry-signal-quality-forward-audit-v0.1|' || v_hour::text);

  insert into public.alpha_hunter_signal_quality_forward_audits(
    audit_id,hour_bucket_utc,audited_at_utc,source_run_id,stage_rows,eligible_rows,
    eligible_direction_failures,eligible_momentum_failures,eligible_integrity_failures,
    signal_quality_blocked_rows,safety_boundary_violations,invariant_pass,evidence,
    model_version,shadow_only,trade_permission
  ) values(
    v_audit_id,v_hour,clock_timestamp(),v_source_run_id,v_stage_rows,v_eligible,
    v_direction_fail,v_momentum_fail,v_integrity_fail,v_blocked,v_safety,v_pass,
    jsonb_build_object(
      'core_contract','CORE_EXECUTION_SIGNAL_QUALITY_CONTRACT.md',
      'required_scanner_direction_aligned',true,
      'required_scanner_momentum_confirmed',true,
      'required_scanner_data_integrity_pass',true,
      'audit_is_execution_permission',false,
      'forward_test_started',true
    ),
    'money-entry-signal-quality-forward-audit-v0.1',true,false
  )
  on conflict(hour_bucket_utc) do nothing;

  return jsonb_build_object(
    'mode','MONEY_ENTRY_SIGNAL_QUALITY_FORWARD_AUDIT',
    'hour_bucket_utc',v_hour,
    'source_run_id',v_source_run_id,
    'stage_rows',v_stage_rows,
    'eligible_rows',v_eligible,
    'eligible_direction_failures',v_direction_fail,
    'eligible_momentum_failures',v_momentum_fail,
    'eligible_integrity_failures',v_integrity_fail,
    'signal_quality_blocked_rows',v_blocked,
    'safety_boundary_violations',v_safety,
    'invariant_pass',v_pass,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_run_signal_quality_forward_audit() from public, anon, authenticated;
grant execute on function private.alpha_hunter_run_signal_quality_forward_audit() to service_role;

-- Run after the :20 production-control finalizer so each hourly audit observes
-- the completed evidence chain for the hour.
do $$
begin
  if exists(select 1 from cron.job where jobname='alpha-hunter-signal-quality-forward-audit-hourly') then
    perform cron.unschedule(jobid)
    from cron.job
    where jobname='alpha-hunter-signal-quality-forward-audit-hourly';
  end if;

  perform cron.schedule(
    'alpha-hunter-signal-quality-forward-audit-hourly',
    '22 * * * *',
    'select private.alpha_hunter_run_signal_quality_forward_audit();'
  );
end;
$$;