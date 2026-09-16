-- Alpha Hunter fast execution scan trigger v0.1
--
-- Purpose:
-- Reduce the confirmation-tax / late-detection gap without weakening any
-- execution threshold. The protected hourly production scan remains intact.
-- This adds three extra public-data scanner runs per hour, offset from the
-- hourly cycle, by calling the existing dashboard /api/run-scan endpoint.
--
-- Safety:
-- - scanner only; no order endpoint
-- - no private exchange write path
-- - no execution threshold changes
-- - app-level scan lock prevents overlapping scans
-- - append-only trigger evidence
-- - trade_permission=false

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

create table if not exists public.alpha_hunter_fast_scan_trigger_events (
  event_id text primary key,
  trigger_bucket_utc timestamptz not null unique,
  triggered_at_utc timestamptz not null default clock_timestamp(),
  endpoint text not null,
  http_status integer,
  response_body text,
  accepted boolean not null default false,
  model_version text not null default 'fast-execution-scan-trigger-v0.1',
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_fast_scan_trigger_events enable row level security;
revoke all on table public.alpha_hunter_fast_scan_trigger_events from public, anon, authenticated;
grant select, insert on table public.alpha_hunter_fast_scan_trigger_events to service_role;

create index if not exists idx_ah_fast_scan_trigger_events_time
  on public.alpha_hunter_fast_scan_trigger_events(triggered_at_utc desc);

drop trigger if exists trg_ah_fast_scan_trigger_events_append_only
  on public.alpha_hunter_fast_scan_trigger_events;
create trigger trg_ah_fast_scan_trigger_events_append_only
before update or delete on public.alpha_hunter_fast_scan_trigger_events
for each row execute function private.alpha_hunter_block_append_only_mutation();

create or replace function private.alpha_hunter_trigger_fast_execution_scan()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_endpoint constant text := 'https://alpha-hunter-j5i3.onrender.com/api/run-scan';
  v_now timestamptz := clock_timestamp();
  v_bucket timestamptz := date_trunc('minute', v_now);
  v_status integer;
  v_content text;
  v_accepted boolean := false;
  v_event_id text;
begin
  -- The endpoint returns immediately (202) and the Flask app's scan_lock makes
  -- overlapping requests idempotently remain on the already-running scan.
  select (r).status, (r).content
    into v_status, v_content
  from (
    select extensions.http_post(
      v_endpoint::varchar,
      '{}'::varchar,
      'application/json'::varchar
    ) as r
  ) q;

  v_accepted := v_status in (200, 202);
  v_event_id := md5(
    'fast-execution-scan-trigger-v0.1|' || v_bucket::text
  );

  insert into public.alpha_hunter_fast_scan_trigger_events(
    event_id,
    trigger_bucket_utc,
    triggered_at_utc,
    endpoint,
    http_status,
    response_body,
    accepted,
    model_version,
    shadow_only,
    trade_permission
  ) values (
    v_event_id,
    v_bucket,
    v_now,
    v_endpoint,
    v_status,
    left(v_content, 4000),
    v_accepted,
    'fast-execution-scan-trigger-v0.1',
    true,
    false
  )
  on conflict (event_id) do nothing;

  return jsonb_build_object(
    'mode','FAST_EXECUTION_SCAN_TRIGGER',
    'triggered_at_utc',v_now,
    'http_status',v_status,
    'accepted',v_accepted,
    'shadow_only',true,
    'trade_permission',false
  );
exception when others then
  -- A failed trigger must not mutate execution state or silently look healthy.
  v_event_id := md5(
    'fast-execution-scan-trigger-v0.1|' || v_bucket::text
  );

  insert into public.alpha_hunter_fast_scan_trigger_events(
    event_id,
    trigger_bucket_utc,
    triggered_at_utc,
    endpoint,
    http_status,
    response_body,
    accepted,
    model_version,
    shadow_only,
    trade_permission
  ) values (
    v_event_id,
    v_bucket,
    v_now,
    v_endpoint,
    null,
    left(sqlerrm, 4000),
    false,
    'fast-execution-scan-trigger-v0.1',
    true,
    false
  )
  on conflict (event_id) do nothing;

  return jsonb_build_object(
    'mode','FAST_EXECUTION_SCAN_TRIGGER',
    'triggered_at_utc',v_now,
    'http_status',null,
    'accepted',false,
    'error',sqlerrm,
    'shadow_only',true,
    'trade_permission',false
  );
end;
$$;

revoke all on function private.alpha_hunter_trigger_fast_execution_scan() from public, anon, authenticated;
grant execute on function private.alpha_hunter_trigger_fast_execution_scan() to service_role;

-- Keep the protected top-of-hour production scan unchanged. These three
-- additional scans reduce the maximum observation gap to roughly 20 minutes
-- while avoiding the :10-:22 database evidence pipeline window.
select cron.unschedule(jobid)
from cron.job
where jobname='alpha-hunter-fast-execution-scan-v01';

select cron.schedule(
  'alpha-hunter-fast-execution-scan-v01',
  '7,27,47 * * * *',
  $$select private.alpha_hunter_trigger_fast_execution_scan();$$
);
