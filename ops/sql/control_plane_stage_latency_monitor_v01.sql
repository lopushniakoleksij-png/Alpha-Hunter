-- Alpha Hunter control-plane stage latency monitor v0.1
--
-- Operations-only observability. Lives under ops/sql and is outside the sealed
-- V14 scientific fingerprint.
--
-- Captures sanitized pg_cron execution timing/status for the seven-stage cloud
-- control plane. No stage command, threshold, strategy, scientific evidence, or
-- trading authority is changed.

create table if not exists public.alpha_hunter_control_plane_stage_runtime_samples_v01 (
  sample_id text primary key,
  checked_at_utc timestamptz not null,
  scheduled_hour_utc timestamptz not null,
  jobname text not null,
  stage_name text not null,
  cron_status text,
  started_at_utc timestamptz,
  finished_at_utc timestamptz,
  duration_ms double precision,
  timed_out boolean not null default false,
  result_class text not null check (
    result_class in ('SUCCESS','TIMEOUT','FAILED','NO_RUN')
  ),
  telemetry_only boolean not null default true check (telemetry_only=true),
  mutation_permitted boolean not null default false check (mutation_permitted=false),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_control_plane_stage_runtime_samples_v01
  enable row level security;

revoke all on table public.alpha_hunter_control_plane_stage_runtime_samples_v01
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_control_plane_stage_runtime_samples_v01
  to service_role;

drop trigger if exists trg_ah_control_plane_stage_runtime_append_only
  on public.alpha_hunter_control_plane_stage_runtime_samples_v01;
create trigger trg_ah_control_plane_stage_runtime_append_only
before update or delete
on public.alpha_hunter_control_plane_stage_runtime_samples_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace function private.alpha_hunter_capture_control_plane_stage_runtime_v01(
  p_now timestamptz default clock_timestamp()
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_hour timestamptz := date_trunc('hour',p_now);
  r record;
  v_rows integer := 0;
begin
  for r in
    with jobs(jobname,stage_name) as (
      values
        ('alpha-hunter-big-mover-shadow-hourly','ANSWER_KEY'),
        ('alpha-hunter-big-mover-parent-direction-hourly','PARENT_DIRECTION'),
        ('alpha-hunter-big-mover-money-entry-bridge-hourly','MONEY_ENTRY_BRIDGE'),
        ('alpha-hunter-money-entry-stage-hourly','MONEY_ENTRY_STAGE'),
        ('alpha-hunter-big-mover-money-scorecard-hourly','MONEY_SCORECARD'),
        ('alpha-hunter-execution-cost-evidence-hourly','COST_EVIDENCE'),
        ('alpha-hunter-portfolio-risk-veto-hourly','PORTFOLIO_RISK')
    ),
    latest as (
      select distinct on (j.jobname)
        j.jobname,
        j.stage_name,
        d.status as cron_status,
        d.start_time,
        d.end_time,
        d.return_message
      from jobs j
      left join cron.job cj
        on cj.jobname=j.jobname
      left join cron.job_run_details d
        on d.jobid=cj.jobid
       and d.start_time>=v_hour
       and d.start_time<v_hour+interval '1 hour'
      order by j.jobname,d.start_time desc nulls last
    )
    select
      jobname,
      stage_name,
      cron_status,
      start_time,
      end_time,
      case
        when start_time is not null and end_time is not null
          then extract(epoch from(end_time-start_time))*1000.0
        else null
      end as duration_ms,
      coalesce(return_message,'') ilike '%statement timeout%'
        or coalesce(return_message,'') ilike '%canceling statement due to statement timeout%'
        as timed_out
    from latest
  loop
    insert into public.alpha_hunter_control_plane_stage_runtime_samples_v01(
      sample_id,
      checked_at_utc,
      scheduled_hour_utc,
      jobname,
      stage_name,
      cron_status,
      started_at_utc,
      finished_at_utc,
      duration_ms,
      timed_out,
      result_class
    ) values (
      md5(v_hour::text||'|'||r.jobname),
      p_now,
      v_hour,
      r.jobname,
      r.stage_name,
      r.cron_status,
      r.start_time,
      r.end_time,
      r.duration_ms,
      coalesce(r.timed_out,false),
      case
        when r.start_time is null then 'NO_RUN'
        when coalesce(r.timed_out,false) then 'TIMEOUT'
        when lower(coalesce(r.cron_status,''))='succeeded' then 'SUCCESS'
        else 'FAILED'
      end
    )
    on conflict (sample_id) do nothing;

    v_rows := v_rows + 1;
  end loop;

  return jsonb_build_object(
    'scheduled_hour_utc',v_hour,
    'rows_considered',v_rows,
    'telemetry_only',true,
    'mutation_permitted',false,
    'trade_permission',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_capture_control_plane_stage_runtime_v01(timestamptz)
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_control_plane_stage_runtime_v01(timestamptz)
  to service_role;


create or replace view public.alpha_hunter_control_plane_stage_latency_status_v01
with (security_invoker=true,security_barrier=true) as
with latest_hour as (
  select max(scheduled_hour_utc) as scheduled_hour_utc
  from public.alpha_hunter_control_plane_stage_runtime_samples_v01
),
rows as (
  select s.*
  from public.alpha_hunter_control_plane_stage_runtime_samples_v01 s
  join latest_hour h using(scheduled_hour_utc)
)
select
  clock_timestamp() as checked_at_utc,
  scheduled_hour_utc,
  count(*)::integer as stage_samples,
  count(*) filter(where result_class='SUCCESS')::integer as successful_stages,
  count(*) filter(where result_class='TIMEOUT')::integer as timed_out_stages,
  count(*) filter(where result_class='FAILED')::integer as failed_stages,
  count(*) filter(where result_class='NO_RUN')::integer as missing_stage_runs,
  max(duration_ms) filter(where stage_name='ANSWER_KEY') as answer_key_duration_ms,
  max(duration_ms) filter(where stage_name='PARENT_DIRECTION') as parent_direction_duration_ms,
  max(duration_ms) as max_stage_duration_ms,
  case
    when count(*) filter(where result_class='TIMEOUT')>0
      then 'TIMEOUT_DETECTED'
    when count(*) filter(where result_class='FAILED')>0
      then 'FAILED_STAGE_DETECTED'
    when count(*) filter(where result_class='NO_RUN')>0
      then 'MISSING_STAGE_RUN'
    when count(*)=7
      and count(*) filter(where result_class='SUCCESS')=7
      then 'PASS'
    else 'INCOMPLETE'
  end as latency_status,
  true as telemetry_only,
  false as mutation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from rows
group by scheduled_hour_utc;

revoke all on public.alpha_hunter_control_plane_stage_latency_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_control_plane_stage_latency_status_v01
  to service_role;


do $outer$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-control-plane-stage-runtime-hourly-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;

  perform cron.schedule(
    'alpha-hunter-control-plane-stage-runtime-hourly-v01',
    '22 * * * *',
    $cmd$select private.alpha_hunter_capture_control_plane_stage_runtime_v01(clock_timestamp());$cmd$
  );
end;
$outer$;

select private.alpha_hunter_capture_control_plane_stage_runtime_v01(
  date_trunc('hour',clock_timestamp())-interval '1 second'
);
