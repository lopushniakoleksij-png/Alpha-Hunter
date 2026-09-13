-- Alpha Hunter cloud production control plane v0.1
--
-- Purpose:
--   Give the phone/cloud runtime one canonical hourly control RUN_ID while
--   preserving the existing staggered Bitget/Supabase stages.
--
-- Controlled stage order:
--   :10 ANSWER_KEY
--   :11 PARENT_DIRECTION
--   :12 MONEY_ENTRY_BRIDGE
--   :14 MONEY_SCORECARD
--   :20 FINALIZE / HEALTH / INCIDENT
--
-- Safety boundary:
--   shadow_only=true
--   trade_permission=false
--   production_execution_enabled=false
--   research_trade_permission=false
--   no private Bitget credential
--   no order route
--
-- The step/health/incident streams are append-only. The run table is a
-- mutable summary pointing to immutable evidence events.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

create table if not exists public.alpha_hunter_control_plane_runs (
  control_run_id text primary key,
  scheduled_hour_utc timestamptz not null unique,
  started_at_utc timestamptz not null default clock_timestamp(),
  finalized_at_utc timestamptz,
  overall_status text not null default 'RUNNING' check (overall_status in ('RUNNING','PASS','DEGRADED','FAILED')),
  source_run_id text,
  expected_stage_count integer not null default 4 check (expected_stage_count = 4),
  passed_stage_count integer not null default 0 check (passed_stage_count >= 0),
  degraded_stage_count integer not null default 0 check (degraded_stage_count >= 0),
  failed_stage_count integer not null default 0 check (failed_stage_count >= 0),
  skipped_stage_count integer not null default 0 check (skipped_stage_count >= 0),
  data_freshness_status text not null default 'NOT_FINALIZED' check (data_freshness_status in ('NOT_FINALIZED','FRESH','STALE','DATA_INSUFFICIENT')),
  safety_status text not null default 'NOT_FINALIZED' check (safety_status in ('NOT_FINALIZED','PASS','FAIL')),
  release_version text not null default 'cloud-control-plane-v0.1',
  production_execution_enabled boolean not null default false check (production_execution_enabled = false),
  research_trade_permission boolean not null default false check (research_trade_permission = false),
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload)='object'),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp()
);

create table if not exists public.alpha_hunter_control_plane_step_events (
  step_event_id text primary key,
  control_run_id text not null references public.alpha_hunter_control_plane_runs(control_run_id),
  stage_name text not null check (stage_name in ('ANSWER_KEY','PARENT_DIRECTION','MONEY_ENTRY_BRIDGE','MONEY_SCORECARD')),
  stage_order integer not null check (stage_order between 1 and 4),
  attempt_no integer not null check (attempt_no >= 1),
  status text not null check (status in ('PASS','DEGRADED','FAILED','SKIPPED')),
  started_at_utc timestamptz not null,
  finished_at_utc timestamptz not null,
  duration_ms double precision not null check (duration_ms >= 0),
  source_run_id text,
  result_payload jsonb not null default '{}'::jsonb,
  error text,
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default clock_timestamp(),
  unique(control_run_id, stage_name, attempt_no)
);

create index if not exists idx_ah_control_steps_run_stage
  on public.alpha_hunter_control_plane_step_events(control_run_id, stage_order, attempt_no desc);

create table if not exists public.alpha_hunter_control_plane_health_events (
  health_event_id text primary key,
  control_run_id text not null references public.alpha_hunter_control_plane_runs(control_run_id),
  checked_at_utc timestamptz not null default clock_timestamp(),
  status text not null check (status in ('PASS','DEGRADED','FAILED')),
  stage_order_valid boolean not null,
  source_run_consistent boolean not null,
  data_freshness_status text not null check (data_freshness_status in ('FRESH','STALE','DATA_INSUFFICIENT')),
  safety_status text not null check (safety_status in ('PASS','FAIL')),
  missing_stages jsonb not null default '[]'::jsonb check (jsonb_typeof(missing_stages)='array'),
  warnings jsonb not null default '[]'::jsonb check (jsonb_typeof(warnings)='array'),
  payload jsonb not null default '{}'::jsonb check (jsonb_typeof(payload)='object'),
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_control_health_run_time
  on public.alpha_hunter_control_plane_health_events(control_run_id, checked_at_utc desc);

create table if not exists public.alpha_hunter_production_incident_events (
  incident_event_id text primary key,
  incident_key text not null,
  control_run_id text not null references public.alpha_hunter_control_plane_runs(control_run_id),
  event_type text not null check (event_type in ('OPEN','RESOLVED')),
  severity text not null check (severity in ('INFO','MEDIUM','HIGH','CRITICAL')),
  incident_type text not null,
  occurred_at_utc timestamptz not null default clock_timestamp(),
  details jsonb not null default '{}'::jsonb check (jsonb_typeof(details)='object'),
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default clock_timestamp()
);

create index if not exists idx_ah_incident_key_time
  on public.alpha_hunter_production_incident_events(incident_key, occurred_at_utc desc);

alter table public.alpha_hunter_control_plane_runs enable row level security;
alter table public.alpha_hunter_control_plane_step_events enable row level security;
alter table public.alpha_hunter_control_plane_health_events enable row level security;
alter table public.alpha_hunter_production_incident_events enable row level security;

revoke all on table public.alpha_hunter_control_plane_runs from public, anon, authenticated;
revoke all on table public.alpha_hunter_control_plane_step_events from public, anon, authenticated;
revoke all on table public.alpha_hunter_control_plane_health_events from public, anon, authenticated;
revoke all on table public.alpha_hunter_production_incident_events from public, anon, authenticated;

grant select, insert, update on table public.alpha_hunter_control_plane_runs to service_role;
grant select, insert on table public.alpha_hunter_control_plane_step_events to service_role;
grant select, insert on table public.alpha_hunter_control_plane_health_events to service_role;
grant select, insert on table public.alpha_hunter_production_incident_events to service_role;

create or replace function private.alpha_hunter_block_append_only_mutation()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  raise exception 'append-only Alpha Hunter evidence cannot be updated or deleted';
end;
$$;
revoke all on function private.alpha_hunter_block_append_only_mutation() from public, anon, authenticated;
grant execute on function private.alpha_hunter_block_append_only_mutation() to service_role;

drop trigger if exists trg_ah_control_steps_append_only on public.alpha_hunter_control_plane_step_events;
create trigger trg_ah_control_steps_append_only
before update or delete on public.alpha_hunter_control_plane_step_events
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_control_health_append_only on public.alpha_hunter_control_plane_health_events;
create trigger trg_ah_control_health_append_only
before update or delete on public.alpha_hunter_control_plane_health_events
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_incident_events_append_only on public.alpha_hunter_production_incident_events;
create trigger trg_ah_incident_events_append_only
before update or delete on public.alpha_hunter_production_incident_events
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_control_plane_identity(p_at timestamptz default clock_timestamp())
returns table(control_run_id text, scheduled_hour_utc timestamptz)
language sql
stable
security invoker
set search_path = ''
as $$
  select
    'AHCLOUD-' || to_char((date_trunc('hour', p_at at time zone 'UTC')), 'YYYYMMDD"T"HH24"00Z"') as control_run_id,
    (date_trunc('hour', p_at at time zone 'UTC') at time zone 'UTC') as scheduled_hour_utc;
$$;
revoke all on function private.alpha_hunter_control_plane_identity(timestamptz) from public, anon, authenticated;
grant execute on function private.alpha_hunter_control_plane_identity(timestamptz) to service_role;

create or replace function private.alpha_hunter_run_controlled_stage(p_stage text, p_reference_at timestamptz default clock_timestamp())
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_control_run_id text;
  v_hour timestamptz;
  v_stage text := upper(p_stage);
  v_stage_order integer;
  v_prev_stage text;
  v_attempt integer;
  v_started timestamptz;
  v_finished timestamptz;
  v_result jsonb := '{}'::jsonb;
  v_status text := 'PASS';
  v_error text;
  v_source_run_id text;
  v_existing record;
  v_prev_ok boolean := true;
  v_event_id text;
begin
  select i.control_run_id,i.scheduled_hour_utc into v_control_run_id,v_hour
  from private.alpha_hunter_control_plane_identity(p_reference_at) i;

  v_stage_order := case v_stage
    when 'ANSWER_KEY' then 1
    when 'PARENT_DIRECTION' then 2
    when 'MONEY_ENTRY_BRIDGE' then 3
    when 'MONEY_SCORECARD' then 4
    else null
  end;
  if v_stage_order is null then
    raise exception 'unsupported Alpha Hunter controlled stage: %', p_stage;
  end if;
  v_prev_stage := case v_stage_order when 2 then 'ANSWER_KEY' when 3 then 'PARENT_DIRECTION' when 4 then 'MONEY_ENTRY_BRIDGE' else null end;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_control_run_id||'|'||v_stage,0));

  insert into public.alpha_hunter_control_plane_runs(control_run_id,scheduled_hour_utc,started_at_utc,overall_status,release_version,payload)
  values(v_control_run_id,v_hour,clock_timestamp(),'RUNNING','cloud-control-plane-v0.1',jsonb_build_object('execution_mode','PHONE_CLOUD','canonical_hour',v_hour))
  on conflict(control_run_id) do nothing;

  select s.* into v_existing
  from public.alpha_hunter_control_plane_step_events s
  where s.control_run_id=v_control_run_id and s.stage_name=v_stage and s.status in ('PASS','DEGRADED')
  order by s.attempt_no desc limit 1;
  if found then
    return jsonb_build_object(
      'mode','ALPHA_HUNTER_CONTROLLED_STAGE','control_run_id',v_control_run_id,
      'stage',v_stage,'status',v_existing.status,'deduplicated',true,
      'source_run_id',v_existing.source_run_id,'result',v_existing.result_payload,
      'shadow_only',true,'trade_permission',false
    );
  end if;

  if v_prev_stage is not null then
    select exists(
      select 1 from public.alpha_hunter_control_plane_step_events s
      where s.control_run_id=v_control_run_id and s.stage_name=v_prev_stage and s.status in ('PASS','DEGRADED')
    ) into v_prev_ok;
  end if;

  select coalesce(max(s.attempt_no),0)+1 into v_attempt
  from public.alpha_hunter_control_plane_step_events s
  where s.control_run_id=v_control_run_id and s.stage_name=v_stage;

  v_started := clock_timestamp();

  if not v_prev_ok then
    v_status := 'SKIPPED';
    v_error := 'PREDECESSOR_NOT_SUCCESSFUL:'||v_prev_stage;
    v_result := jsonb_build_object('reason',v_error);
  else
    begin
      case v_stage
        when 'ANSWER_KEY' then
          v_result := public.alpha_hunter_collect_big_mover_answer_key();
          v_source_run_id := v_result #>> '{scoring,latest_feature_run_id}';
          if coalesce((v_result->>'ticker_count')::integer,0) <= 0 then
            v_status := 'FAILED';
            v_error := 'NO_BITGET_TICKERS_RETURNED';
          end if;
        when 'PARENT_DIRECTION' then
          v_result := private.alpha_hunter_collect_big_mover_parent_direction();
          v_source_run_id := v_result->>'run_id';
          if coalesce((v_result->>'failed_rows')::integer,0) > 0 then
            v_status := 'DEGRADED';
          end if;
        when 'MONEY_ENTRY_BRIDGE' then
          v_result := private.alpha_hunter_run_big_mover_money_entry_pipeline();
          v_source_run_id := v_result->>'run_id';
        when 'MONEY_SCORECARD' then
          v_result := private.alpha_hunter_run_big_mover_money_scorecard();
          select r.source_run_id into v_source_run_id
          from public.alpha_hunter_control_plane_runs r where r.control_run_id=v_control_run_id;
          if coalesce((v_result->>'retryable_errors')::integer,0) > 0 then
            v_status := 'DEGRADED';
          end if;
      end case;

      if coalesce(v_result->>'trade_permission','false') <> 'false'
         or coalesce(v_result->>'shadow_only','true') <> 'true' then
        v_status := 'FAILED';
        v_error := coalesce(v_error||';','')||'SAFETY_BOUNDARY_VIOLATION_IN_STAGE_RESULT';
      end if;
    exception when others then
      v_status := 'FAILED';
      v_error := left(sqlerrm,1000);
      v_result := jsonb_build_object('exception',v_error);
    end;
  end if;

  v_finished := clock_timestamp();
  v_event_id := md5(v_control_run_id||'|'||v_stage||'|'||v_attempt::text||'|'||v_started::text);

  insert into public.alpha_hunter_control_plane_step_events(
    step_event_id,control_run_id,stage_name,stage_order,attempt_no,status,
    started_at_utc,finished_at_utc,duration_ms,source_run_id,result_payload,error,
    shadow_only,trade_permission
  ) values (
    v_event_id,v_control_run_id,v_stage,v_stage_order,v_attempt,v_status,
    v_started,v_finished,extract(epoch from (v_finished-v_started))*1000.0,
    v_source_run_id,coalesce(v_result,'{}'::jsonb),v_error,true,false
  );

  update public.alpha_hunter_control_plane_runs r
  set source_run_id=case when r.source_run_id is null then v_source_run_id else r.source_run_id end,
      updated_at=clock_timestamp(),
      payload=r.payload||jsonb_build_object('last_stage',v_stage,'last_stage_status',v_status)
  where r.control_run_id=v_control_run_id;

  return jsonb_build_object(
    'mode','ALPHA_HUNTER_CONTROLLED_STAGE','control_run_id',v_control_run_id,
    'stage',v_stage,'status',v_status,'attempt',v_attempt,'deduplicated',false,
    'source_run_id',v_source_run_id,'error',v_error,'result',v_result,
    'shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_run_controlled_stage(text,timestamptz) from public, anon, authenticated;
grant execute on function private.alpha_hunter_run_controlled_stage(text,timestamptz) to service_role;

create or replace function private.alpha_hunter_finalize_control_plane_hour(p_reference_at timestamptz default clock_timestamp())
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_control_run_id text;
  v_hour timestamptz;
  v_pass integer := 0;
  v_degraded integer := 0;
  v_failed integer := 0;
  v_skipped integer := 0;
  v_missing jsonb := '[]'::jsonb;
  v_warnings jsonb := '[]'::jsonb;
  v_source_consistent boolean := false;
  v_order_valid boolean := false;
  v_latest_signal timestamptz;
  v_latest_answer timestamptz;
  v_latest_shadow timestamptz;
  v_freshness text := 'DATA_INSUFFICIENT';
  v_safety text := 'PASS';
  v_safety_violations integer := 0;
  v_status text;
  v_health_id text;
  v_incident_key text;
begin
  select i.control_run_id,i.scheduled_hour_utc into v_control_run_id,v_hour
  from private.alpha_hunter_control_plane_identity(p_reference_at) i;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(v_control_run_id||'|FINALIZE',0));

  insert into public.alpha_hunter_control_plane_runs(control_run_id,scheduled_hour_utc,started_at_utc,overall_status,release_version,payload)
  values(v_control_run_id,v_hour,clock_timestamp(),'RUNNING','cloud-control-plane-v0.1',jsonb_build_object('execution_mode','PHONE_CLOUD','canonical_hour',v_hour))
  on conflict(control_run_id) do nothing;

  with expected(stage_name,stage_order) as (
    values ('ANSWER_KEY',1),('PARENT_DIRECTION',2),('MONEY_ENTRY_BRIDGE',3),('MONEY_SCORECARD',4)
  ), latest as (
    select distinct on (s.stage_name) s.*
    from public.alpha_hunter_control_plane_step_events s
    where s.control_run_id=v_control_run_id
    order by s.stage_name,s.attempt_no desc
  )
  select
    count(*) filter(where l.status='PASS'),
    count(*) filter(where l.status='DEGRADED'),
    count(*) filter(where l.status='FAILED'),
    count(*) filter(where l.status='SKIPPED'),
    coalesce(jsonb_agg(e.stage_name order by e.stage_order) filter(where l.stage_name is null or l.status not in ('PASS','DEGRADED')),'[]'::jsonb)
  into v_pass,v_degraded,v_failed,v_skipped,v_missing
  from expected e left join latest l using(stage_name);

  with latest as (
    select distinct on (s.stage_name) s.*
    from public.alpha_hunter_control_plane_step_events s
    where s.control_run_id=v_control_run_id
    order by s.stage_name,s.attempt_no desc
  )
  select coalesce(count(distinct source_run_id) filter(where source_run_id is not null) <= 1,false)
  into v_source_consistent from latest;

  with latest as (
    select distinct on (s.stage_name) s.*
    from public.alpha_hunter_control_plane_step_events s
    where s.control_run_id=v_control_run_id
    order by s.stage_name,s.attempt_no desc
  ), ordered as (
    select stage_order,finished_at_utc,lag(finished_at_utc) over(order by stage_order) as prev_finished
    from latest where status in ('PASS','DEGRADED')
  )
  select coalesce(count(*)=4 and bool_and(prev_finished is null or finished_at_utc>=prev_finished),false)
  into v_order_valid from ordered;

  select max(s.captured_at_utc) into v_latest_signal from public.alpha_hunter_signal_features s;
  select max(a.observed_at_utc) into v_latest_answer from public.alpha_hunter_big_mover_answer_key a;
  select max(b.captured_at_utc) into v_latest_shadow from public.alpha_hunter_big_mover_shadow b;

  if v_latest_signal is null or v_latest_answer is null or v_latest_shadow is null then
    v_freshness := 'DATA_INSUFFICIENT';
  elsif clock_timestamp()-v_latest_signal > interval '90 minutes'
     or clock_timestamp()-v_latest_answer > interval '90 minutes'
     or clock_timestamp()-v_latest_shadow > interval '90 minutes' then
    v_freshness := 'STALE';
  else
    v_freshness := 'FRESH';
  end if;

  select
    (select count(*) from public.alpha_hunter_big_mover_shadow x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_parent_direction_shadow x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_money_entry_shadow x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_money_scorecard_candidates x where x.trade_permission<>false or x.shadow_only<>true)
    +(select count(*) from public.alpha_hunter_big_mover_money_scorecard_outcomes x where x.trade_permission<>false or x.shadow_only<>true)
  into v_safety_violations;
  if v_safety_violations>0 then v_safety:='FAIL'; end if;

  if jsonb_array_length(v_missing)>0 then
    v_warnings := v_warnings||jsonb_build_array('MISSING_OR_UNSUCCESSFUL_STAGE');
  end if;
  if not v_source_consistent then
    v_warnings := v_warnings||jsonb_build_array('SOURCE_RUN_ID_MISMATCH');
  end if;
  if not v_order_valid then
    v_warnings := v_warnings||jsonb_build_array('STAGE_ORDER_NOT_PROVEN');
  end if;
  if v_freshness<>'FRESH' then
    v_warnings := v_warnings||jsonb_build_array('DATA_FRESHNESS_'||v_freshness);
  end if;
  if v_safety<>'PASS' then
    v_warnings := v_warnings||jsonb_build_array('SAFETY_BOUNDARY_VIOLATION');
  end if;

  v_status := case
    when v_safety='FAIL' or jsonb_array_length(v_missing)>0 or v_failed>0 or v_skipped>0 or not v_source_consistent or not v_order_valid then 'FAILED'
    when v_degraded>0 or v_freshness<>'FRESH' then 'DEGRADED'
    else 'PASS'
  end;

  v_health_id := md5(v_control_run_id||'|'||clock_timestamp()::text||'|'||v_status);
  insert into public.alpha_hunter_control_plane_health_events(
    health_event_id,control_run_id,checked_at_utc,status,stage_order_valid,source_run_consistent,
    data_freshness_status,safety_status,missing_stages,warnings,payload,shadow_only,trade_permission
  ) values (
    v_health_id,v_control_run_id,clock_timestamp(),v_status,v_order_valid,v_source_consistent,
    v_freshness,v_safety,v_missing,v_warnings,
    jsonb_build_object(
      'latest_signal_feature_utc',v_latest_signal,
      'latest_answer_key_utc',v_latest_answer,
      'latest_big_mover_shadow_utc',v_latest_shadow,
      'safety_violation_count',v_safety_violations,
      'freshness_contract','HOURLY_SOURCE_MAX_AGE_90_MINUTES',
      'expected_stage_order',jsonb_build_array('ANSWER_KEY','PARENT_DIRECTION','MONEY_ENTRY_BRIDGE','MONEY_SCORECARD')
    ),true,false
  );

  update public.alpha_hunter_control_plane_runs r
  set finalized_at_utc=clock_timestamp(),overall_status=v_status,
      passed_stage_count=v_pass,degraded_stage_count=v_degraded,failed_stage_count=v_failed,skipped_stage_count=v_skipped,
      data_freshness_status=v_freshness,safety_status=v_safety,updated_at=clock_timestamp(),
      payload=r.payload||jsonb_build_object('missing_stages',v_missing,'warnings',v_warnings,'latest_health_event_id',v_health_id)
  where r.control_run_id=v_control_run_id;

  v_incident_key := v_control_run_id||'|CONTROL_PLANE_HEALTH';
  if v_status<>'PASS' then
    if not exists(select 1 from public.alpha_hunter_production_incident_events e where e.incident_key=v_incident_key and e.event_type='OPEN') then
      insert into public.alpha_hunter_production_incident_events(
        incident_event_id,incident_key,control_run_id,event_type,severity,incident_type,occurred_at_utc,details,shadow_only,trade_permission
      ) values (
        md5(v_incident_key||'|OPEN'),v_incident_key,v_control_run_id,'OPEN',
        case when v_safety='FAIL' then 'CRITICAL' when v_status='FAILED' then 'HIGH' else 'MEDIUM' end,
        'CONTROL_PLANE_HEALTH',clock_timestamp(),
        jsonb_build_object('status',v_status,'missing_stages',v_missing,'warnings',v_warnings,'safety_status',v_safety,'freshness_status',v_freshness),
        true,false
      );
    end if;
  elsif exists(select 1 from public.alpha_hunter_production_incident_events e where e.incident_key=v_incident_key and e.event_type='OPEN')
     and not exists(select 1 from public.alpha_hunter_production_incident_events e where e.incident_key=v_incident_key and e.event_type='RESOLVED') then
    insert into public.alpha_hunter_production_incident_events(
      incident_event_id,incident_key,control_run_id,event_type,severity,incident_type,occurred_at_utc,details,shadow_only,trade_permission
    ) values (
      md5(v_incident_key||'|RESOLVED'),v_incident_key,v_control_run_id,'RESOLVED','INFO','CONTROL_PLANE_HEALTH',clock_timestamp(),
      jsonb_build_object('status','PASS','resolved_by_health_event_id',v_health_id),true,false
    );
  end if;

  return jsonb_build_object(
    'mode','ALPHA_HUNTER_CLOUD_CONTROL_PLANE_FINALIZE','control_run_id',v_control_run_id,
    'status',v_status,'passed',v_pass,'degraded',v_degraded,'failed',v_failed,'skipped',v_skipped,
    'missing_stages',v_missing,'stage_order_valid',v_order_valid,'source_run_consistent',v_source_consistent,
    'data_freshness_status',v_freshness,'safety_status',v_safety,'warnings',v_warnings,
    'shadow_only',true,'trade_permission',false
  );
end;
$$;
revoke all on function private.alpha_hunter_finalize_control_plane_hour(timestamptz) from public, anon, authenticated;
grant execute on function private.alpha_hunter_finalize_control_plane_hour(timestamptz) to service_role;

-- Harden scorecard SECURITY DEFINER functions to an empty search_path.
alter function private.alpha_hunter_seed_big_mover_money_scorecard() set search_path = '';
alter function private.alpha_hunter_run_big_mover_money_scorecard() set search_path = '';

-- Keep the existing staggered schedule, but route every stage through the
-- control-plane wrapper. Re-running a successful/degraded stage in the same
-- hour deduplicates instead of rescanning Bitget.
do $outer$
declare r record;
begin
  for r in
    select jobid from cron.job
    where jobname in (
      'alpha-hunter-big-mover-shadow-hourly',
      'alpha-hunter-big-mover-parent-direction-hourly',
      'alpha-hunter-big-mover-money-entry-bridge-hourly',
      'alpha-hunter-big-mover-money-scorecard-hourly',
      'alpha-hunter-control-plane-finalize-hourly'
    )
  loop
    perform cron.unschedule(r.jobid);
  end loop;

  perform cron.schedule(
    'alpha-hunter-big-mover-shadow-hourly','10 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('ANSWER_KEY', clock_timestamp());$cmd$
  );
  perform cron.schedule(
    'alpha-hunter-big-mover-parent-direction-hourly','11 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('PARENT_DIRECTION', clock_timestamp());$cmd$
  );
  perform cron.schedule(
    'alpha-hunter-big-mover-money-entry-bridge-hourly','12 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_BRIDGE', clock_timestamp());$cmd$
  );
  perform cron.schedule(
    'alpha-hunter-big-mover-money-scorecard-hourly','14 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('MONEY_SCORECARD', clock_timestamp());$cmd$
  );
  perform cron.schedule(
    'alpha-hunter-control-plane-finalize-hourly','20 * * * *',
    $cmd$select private.alpha_hunter_finalize_control_plane_hour(clock_timestamp());$cmd$
  );
end;
$outer$;
