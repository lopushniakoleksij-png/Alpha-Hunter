-- Alpha Hunter storage growth / runway telemetry v0.1
--
-- Operations-only observability. Lives under ops/sql and is outside the sealed
-- V14 scientific fingerprint.
--
-- Purpose:
-- - capture real physical DB/table/TOAST growth hourly;
-- - bind each sample to the latest canonical RENDER_CRON run;
-- - verify parent/signal compaction contracts remain active;
-- - provide measured growth-rate / 24h / 30d projections without assuming a
--   provider disk quota.
--
-- This migration performs no deletion, update, archival, recompaction, vacuum,
-- table rewrite, or scientific-evidence mutation.

create table if not exists public.alpha_hunter_storage_growth_samples_v01 (
  sample_id text primary key,
  checked_at_utc timestamptz not null,
  database_bytes bigint not null,

  snapshots_total_bytes bigint not null,
  snapshots_toast_bytes bigint not null,
  symbol_snapshots_total_bytes bigint not null,
  symbol_snapshots_toast_bytes bigint not null,
  signals_total_bytes bigint not null,
  signals_toast_bytes bigint not null,
  signal_features_total_bytes bigint not null,
  signal_features_toast_bytes bigint not null,

  latest_canonical_run_id text,
  latest_canonical_scan_at_utc timestamptz,
  latest_canonical_git_commit text,
  latest_parent_storage_contract text,
  latest_parent_payload_bytes bigint,

  latest_run_symbol_rows integer,
  latest_run_child_payload_bytes bigint,

  latest_run_signal_rows integer,
  latest_run_signal_payload_bytes bigint,
  latest_run_signal_compact_rows integer,

  latest_run_feature_rows integer,
  latest_run_feature_payload_bytes bigint,
  latest_run_feature_source_payload_bytes bigint,
  latest_run_feature_source_compact_rows integer,

  telemetry_only boolean not null default true check (telemetry_only=true),
  mutation_permitted boolean not null default false check (mutation_permitted=false),
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),

  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_storage_growth_samples_v01
  enable row level security;

revoke all on table public.alpha_hunter_storage_growth_samples_v01
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_storage_growth_samples_v01
  to service_role;

drop trigger if exists trg_ah_storage_growth_samples_append_only
  on public.alpha_hunter_storage_growth_samples_v01;
create trigger trg_ah_storage_growth_samples_append_only
before update or delete
on public.alpha_hunter_storage_growth_samples_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace function private.alpha_hunter_capture_storage_growth_v01()
returns jsonb
language plpgsql
security definer
set search_path=''
as $$
declare
  v_checked_at timestamptz := clock_timestamp();
  v_run_id text;
  v_scan_at timestamptz;
  v_git_commit text;
  v_parent_contract text;
  v_parent_payload_bytes bigint;

  v_symbol_rows integer := 0;
  v_child_payload_bytes bigint := 0;

  v_signal_rows integer := 0;
  v_signal_payload_bytes bigint := 0;
  v_signal_compact_rows integer := 0;

  v_feature_rows integer := 0;
  v_feature_payload_bytes bigint := 0;
  v_feature_source_payload_bytes bigint := 0;
  v_feature_source_compact_rows integer := 0;

  v_database_bytes bigint;

  v_snapshots_total bigint;
  v_snapshots_toast bigint;
  v_symbol_snapshots_total bigint;
  v_symbol_snapshots_toast bigint;
  v_signals_total bigint;
  v_signals_toast bigint;
  v_signal_features_total bigint;
  v_signal_features_toast bigint;

  v_sample_id text;
begin
  select
    s.run_id,
    s.collected_at_utc,
    s.payload->'validation_identity'->>'git_commit',
    coalesce(s.payload->>'_storage_contract','LEGACY'),
    pg_column_size(s.payload)::bigint
  into
    v_run_id,
    v_scan_at,
    v_git_commit,
    v_parent_contract,
    v_parent_payload_bytes
  from public.alpha_hunter_snapshots s
  where s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
  order by s.collected_at_utc desc
  limit 1;

  if v_run_id is not null then
    select
      count(*)::integer,
      coalesce(sum(pg_column_size(s.payload)),0)::bigint
    into
      v_symbol_rows,
      v_child_payload_bytes
    from public.alpha_hunter_symbol_snapshots s
    where s.run_id=v_run_id;

    select
      count(*)::integer,
      coalesce(sum(pg_column_size(s.payload)),0)::bigint,
      count(*) filter(
        where s.payload->>'_storage_contract'='signal-source-v0.2'
      )::integer
    into
      v_signal_rows,
      v_signal_payload_bytes,
      v_signal_compact_rows
    from public.alpha_hunter_signals s
    where s.run_id=v_run_id;

    select
      count(*)::integer,
      coalesce(sum(pg_column_size(f.features)),0)::bigint,
      coalesce(sum(pg_column_size(f.source_payload)),0)::bigint,
      count(*) filter(
        where f.source_payload->>'_storage_contract'='signal-source-v0.2'
      )::integer
    into
      v_feature_rows,
      v_feature_payload_bytes,
      v_feature_source_payload_bytes,
      v_feature_source_compact_rows
    from public.alpha_hunter_signal_features f
    where f.run_id=v_run_id;
  end if;

  select pg_database_size(current_database())::bigint
    into v_database_bytes;

  select
    pg_total_relation_size(c.oid)::bigint,
    case when c.reltoastrelid<>0
      then pg_total_relation_size(c.reltoastrelid)::bigint
      else 0::bigint
    end
  into v_snapshots_total,v_snapshots_toast
  from pg_class c
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname='alpha_hunter_snapshots';

  select
    pg_total_relation_size(c.oid)::bigint,
    case when c.reltoastrelid<>0
      then pg_total_relation_size(c.reltoastrelid)::bigint
      else 0::bigint
    end
  into v_symbol_snapshots_total,v_symbol_snapshots_toast
  from pg_class c
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname='alpha_hunter_symbol_snapshots';

  select
    pg_total_relation_size(c.oid)::bigint,
    case when c.reltoastrelid<>0
      then pg_total_relation_size(c.reltoastrelid)::bigint
      else 0::bigint
    end
  into v_signals_total,v_signals_toast
  from pg_class c
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname='alpha_hunter_signals';

  select
    pg_total_relation_size(c.oid)::bigint,
    case when c.reltoastrelid<>0
      then pg_total_relation_size(c.reltoastrelid)::bigint
      else 0::bigint
    end
  into v_signal_features_total,v_signal_features_toast
  from pg_class c
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname='alpha_hunter_signal_features';

  v_sample_id :=
    'storage-'||md5(
      coalesce(v_run_id,'NO_RUN')||'|'||v_checked_at::text
    );

  insert into public.alpha_hunter_storage_growth_samples_v01(
    sample_id,
    checked_at_utc,
    database_bytes,
    snapshots_total_bytes,
    snapshots_toast_bytes,
    symbol_snapshots_total_bytes,
    symbol_snapshots_toast_bytes,
    signals_total_bytes,
    signals_toast_bytes,
    signal_features_total_bytes,
    signal_features_toast_bytes,
    latest_canonical_run_id,
    latest_canonical_scan_at_utc,
    latest_canonical_git_commit,
    latest_parent_storage_contract,
    latest_parent_payload_bytes,
    latest_run_symbol_rows,
    latest_run_child_payload_bytes,
    latest_run_signal_rows,
    latest_run_signal_payload_bytes,
    latest_run_signal_compact_rows,
    latest_run_feature_rows,
    latest_run_feature_payload_bytes,
    latest_run_feature_source_payload_bytes,
    latest_run_feature_source_compact_rows
  ) values (
    v_sample_id,
    v_checked_at,
    v_database_bytes,
    coalesce(v_snapshots_total,0),
    coalesce(v_snapshots_toast,0),
    coalesce(v_symbol_snapshots_total,0),
    coalesce(v_symbol_snapshots_toast,0),
    coalesce(v_signals_total,0),
    coalesce(v_signals_toast,0),
    coalesce(v_signal_features_total,0),
    coalesce(v_signal_features_toast,0),
    v_run_id,
    v_scan_at,
    v_git_commit,
    v_parent_contract,
    v_parent_payload_bytes,
    v_symbol_rows,
    v_child_payload_bytes,
    v_signal_rows,
    v_signal_payload_bytes,
    v_signal_compact_rows,
    v_feature_rows,
    v_feature_payload_bytes,
    v_feature_source_payload_bytes,
    v_feature_source_compact_rows
  )
  on conflict (sample_id) do nothing;

  return jsonb_build_object(
    'sample_id',v_sample_id,
    'checked_at_utc',v_checked_at,
    'database_bytes',v_database_bytes,
    'latest_canonical_run_id',v_run_id,
    'latest_canonical_git_commit',v_git_commit,
    'latest_parent_storage_contract',v_parent_contract,
    'latest_run_signal_rows',v_signal_rows,
    'latest_run_signal_compact_rows',v_signal_compact_rows,
    'latest_run_feature_rows',v_feature_rows,
    'latest_run_feature_source_compact_rows',v_feature_source_compact_rows,
    'telemetry_only',true,
    'mutation_permitted',false,
    'trade_permission',false,
    'order_path','NONE'
  );
end;
$$;

revoke all on function private.alpha_hunter_capture_storage_growth_v01()
  from public,anon,authenticated;
grant execute on function private.alpha_hunter_capture_storage_growth_v01()
  to service_role;


create or replace view public.alpha_hunter_storage_growth_status_v01
with (security_invoker=true,security_barrier=true) as
with ranked as (
  select
    s.*,
    row_number() over(
      order by s.checked_at_utc desc,s.created_at desc
    ) as rn,
    count(*) over() as sample_count
  from public.alpha_hunter_storage_growth_samples_v01 s
),
latest as (
  select * from ranked where rn=1
),
previous as (
  select * from ranked where rn=2
),
joined as (
  select
    l.*,
    p.checked_at_utc as previous_checked_at_utc,
    p.database_bytes as previous_database_bytes,
    extract(
      epoch from (l.checked_at_utc-p.checked_at_utc)
    )/3600.0 as measured_interval_hours,
    (l.database_bytes-p.database_bytes)::bigint as database_delta_bytes
  from latest l
  left join previous p on true
)
select
  checked_at_utc,
  sample_count,
  database_bytes,
  pg_size_pretty(database_bytes) as database_size_pretty,

  snapshots_total_bytes,
  snapshots_toast_bytes,
  symbol_snapshots_total_bytes,
  symbol_snapshots_toast_bytes,
  signals_total_bytes,
  signals_toast_bytes,
  signal_features_total_bytes,
  signal_features_toast_bytes,

  latest_canonical_run_id,
  latest_canonical_scan_at_utc,
  latest_canonical_git_commit,
  latest_parent_storage_contract,
  latest_parent_payload_bytes,
  latest_run_symbol_rows,
  latest_run_child_payload_bytes,
  latest_run_signal_rows,
  latest_run_signal_payload_bytes,
  latest_run_signal_compact_rows,
  latest_run_feature_rows,
  latest_run_feature_payload_bytes,
  latest_run_feature_source_payload_bytes,
  latest_run_feature_source_compact_rows,

  case
    when latest_parent_storage_contract<>'snapshot-parent-v0.2'
      then 'PARENT_COMPACTION_REGRESSION'
    when latest_run_signal_rows>0
      and latest_run_signal_compact_rows<>latest_run_signal_rows
      then 'SIGNAL_COMPACTION_REGRESSION'
    when latest_run_feature_rows>0
      and latest_run_feature_source_compact_rows<>latest_run_feature_rows
      then 'FEATURE_SOURCE_COMPACTION_REGRESSION'
    else 'CURRENT_WRITES_COMPACT'
  end as current_write_compaction_status,

  previous_checked_at_utc,
  previous_database_bytes,
  database_delta_bytes,
  measured_interval_hours,

  case
    when previous_database_bytes is not null
      and measured_interval_hours between 0.25 and 6.0
      then database_delta_bytes/measured_interval_hours
    else null
  end as measured_database_bytes_per_hour,

  case
    when previous_database_bytes is not null
      and measured_interval_hours between 0.25 and 6.0
      then greatest(database_delta_bytes/measured_interval_hours,0)*24
    else null
  end as projected_positive_growth_24h_bytes,

  case
    when previous_database_bytes is not null
      and measured_interval_hours between 0.25 and 6.0
      then greatest(database_delta_bytes/measured_interval_hours,0)*24*30
    else null
  end as projected_positive_growth_30d_bytes,

  case
    when previous_database_bytes is not null
      and measured_interval_hours between 0.25 and 6.0
      then database_bytes
        + greatest(database_delta_bytes/measured_interval_hours,0)*24*30
    else null
  end as projected_database_bytes_30d,

  case
    when sample_count<2 then 'BASELINE_ONLY'
    when measured_interval_hours not between 0.25 and 6.0
      then 'INTERVAL_NOT_COMPARABLE'
    else 'MEASURED'
  end as growth_measurement_status,

  true as telemetry_only,
  false as mutation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from joined;

revoke all on public.alpha_hunter_storage_growth_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_storage_growth_status_v01
  to service_role;


do $outer$
declare
  r record;
begin
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-storage-growth-hourly-v01'
  loop
    perform cron.unschedule(r.jobid);
  end loop;

  perform cron.schedule(
    'alpha-hunter-storage-growth-hourly-v01',
    '27 * * * *',
    $cmd$select private.alpha_hunter_capture_storage_growth_v01();$cmd$
  );
end;
$outer$;

select private.alpha_hunter_capture_storage_growth_v01();
