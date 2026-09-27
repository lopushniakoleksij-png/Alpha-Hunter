-- Alpha Hunter production deployment drift guard v0.1
--
-- Operations-only release observability, outside the sealed V14 scientific
-- fingerprint.
--
-- GitHub main pushes append the target commit. Production compares that target
-- with the latest canonical RENDER_CRON snapshot commit. No deployment action,
-- trading authority, strategy threshold, or scientific state is changed.

create table if not exists public.alpha_hunter_production_release_targets_v01 (
  release_target_id text primary key,
  git_commit text not null,
  recorded_at_utc timestamptz not null,
  source text not null check (source in ('GITHUB_MAIN_PUSH','MANUAL_AUDIT')),
  repository text not null,
  shadow_only boolean not null default true check (shadow_only=true),
  trade_permission boolean not null default false check (trade_permission=false),
  production_promotion_permitted boolean not null default false
    check (production_promotion_permitted=false),
  order_path text not null default 'NONE' check (order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_production_release_targets_v01
  enable row level security;

revoke all on table public.alpha_hunter_production_release_targets_v01
  from public,anon,authenticated,service_role;
grant select,insert on table public.alpha_hunter_production_release_targets_v01
  to service_role;

drop trigger if exists trg_ah_production_release_targets_append_only
  on public.alpha_hunter_production_release_targets_v01;
create trigger trg_ah_production_release_targets_append_only
before update or delete
on public.alpha_hunter_production_release_targets_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace view public.alpha_hunter_production_deployment_drift_v01
with (security_invoker=true,security_barrier=true) as
with target as (
  select
    r.release_target_id,
    r.git_commit as target_git_commit,
    r.recorded_at_utc as target_recorded_at_utc,
    r.source as target_source,
    r.repository
  from public.alpha_hunter_production_release_targets_v01 r
  order by r.recorded_at_utc desc,r.created_at desc
  limit 1
),
live as (
  select
    s.run_id as latest_canonical_run_id,
    s.collected_at_utc as latest_canonical_scan_at_utc,
    s.payload->'validation_identity'->>'git_commit' as live_git_commit,
    s.payload->'validation_identity'->>'scientific_fingerprint_sha256'
      as scientific_fingerprint_sha256
  from public.alpha_hunter_snapshots s
  where s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
  order by s.collected_at_utc desc
  limit 1
)
select
  clock_timestamp() as checked_at_utc,
  t.release_target_id,
  t.target_git_commit,
  t.target_recorded_at_utc,
  t.target_source,
  t.repository,
  l.latest_canonical_run_id,
  l.latest_canonical_scan_at_utc,
  l.live_git_commit,
  l.scientific_fingerprint_sha256,
  case
    when t.target_git_commit is null then 'NO_TARGET'
    when l.live_git_commit is null then 'NO_CANONICAL_SCAN'
    when l.live_git_commit=t.target_git_commit then 'MATCHED'
    else 'DRIFT'
  end as deployment_status,
  case
    when t.target_git_commit is not null
     and l.live_git_commit is not null
     and l.live_git_commit<>t.target_git_commit
      then true
    else false
  end as deployment_drift,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from (select 1) anchor
left join target t on true
left join live l on true;

revoke all on public.alpha_hunter_production_deployment_drift_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_production_deployment_drift_v01
  to service_role;
