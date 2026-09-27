-- Alpha Hunter runtime-fingerprint deployment guard v0.3
--
-- Operations-only deployment observability, outside the sealed V14 scientific
-- fingerprint.
--
-- v0.2 compared raw Git SHAs. That creates false drift when Render runs a later
-- ops-only descendant commit that contains the exact required runtime files.
--
-- v0.3 compares a deterministic SHA-256 fingerprint of the actual Render Cron
-- runtime file set. Git SHAs remain diagnostic metadata only.
--
-- Existing public deployment-drift view schema is preserved exactly.

alter table public.alpha_hunter_production_release_targets_v01
  add column if not exists runtime_fingerprint_sha256 text;

alter table public.alpha_hunter_production_release_targets_v01
  drop constraint if exists
  alpha_hunter_production_release_targets_v01_runtime_fingerprint_check;

alter table public.alpha_hunter_production_release_targets_v01
  add constraint
  alpha_hunter_production_release_targets_v01_runtime_fingerprint_check
  check (
    runtime_fingerprint_sha256 is null
    or runtime_fingerprint_sha256 ~ '^[0-9a-f]{64}$'
  );


create or replace view public.alpha_hunter_production_deployment_runtime_status_v03
with (security_invoker=true,security_barrier=true) as
with target as (
  select
    r.release_target_id,
    r.git_commit as target_git_commit,
    r.runtime_fingerprint_sha256 as target_runtime_fingerprint_sha256,
    r.recorded_at_utc as target_recorded_at_utc,
    r.source as target_source,
    r.repository
  from public.alpha_hunter_production_release_targets_v01 r
  where r.source in ('GITHUB_RUNTIME_PUSH','MANUAL_RUNTIME_TARGET')
  order by r.recorded_at_utc desc,r.created_at desc
  limit 1
),
canonical as (
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
),
live_runtime as (
  select
    c.collector_run_id as live_runtime_observation_id,
    c.source_run_id as live_runtime_source_run_id,
    c.checked_at_utc as live_runtime_observed_at_utc,
    lower(
      c.evidence->>'runtime_release_fingerprint_sha256'
    ) as live_runtime_fingerprint_sha256,
    s.payload->'validation_identity'->>'git_commit'
      as live_runtime_git_commit
  from public.alpha_hunter_execution_quality_collector_runs_v01 c
  left join public.alpha_hunter_snapshots s
    on s.run_id=c.source_run_id
  where coalesce(
    c.evidence->>'runtime_release_fingerprint_sha256',
    ''
  ) ~ '^[0-9a-fA-F]{64}$'
  order by c.checked_at_utc desc,c.created_at desc
  limit 1
),
classified as (
  select
    clock_timestamp() as checked_at_utc,
    t.release_target_id,
    t.target_git_commit,
    lower(t.target_runtime_fingerprint_sha256)
      as target_runtime_fingerprint_sha256,
    t.target_recorded_at_utc,
    t.target_source,
    t.repository,

    c.latest_canonical_run_id,
    c.latest_canonical_scan_at_utc,
    c.live_git_commit,
    c.scientific_fingerprint_sha256,

    l.live_runtime_observation_id,
    l.live_runtime_source_run_id,
    l.live_runtime_observed_at_utc,
    l.live_runtime_git_commit,
    l.live_runtime_fingerprint_sha256,

    case
      when t.target_git_commit is null then 'NO_RUNTIME_TARGET'
      when c.live_git_commit is null then 'NO_CANONICAL_SCAN'
      when t.target_runtime_fingerprint_sha256 is not null
       and l.live_runtime_fingerprint_sha256 is null
        then 'DRIFT'
      when t.target_runtime_fingerprint_sha256 is not null
       and lower(t.target_runtime_fingerprint_sha256)
         =l.live_runtime_fingerprint_sha256
        then 'MATCHED'
      when t.target_runtime_fingerprint_sha256 is not null
        then 'DRIFT'
      when c.live_git_commit=t.target_git_commit
        then 'MATCHED'
      else 'DRIFT'
    end as deployment_status,

    case
      when t.target_git_commit is null then 'NO_RUNTIME_TARGET'
      when c.live_git_commit is null then 'NO_CANONICAL_SCAN'
      when t.target_runtime_fingerprint_sha256 is not null
        then 'RUNTIME_FINGERPRINT'
      else 'LEGACY_EXACT_GIT_COMMIT'
    end as comparison_mode
  from (select 1) anchor
  left join target t on true
  left join canonical c on true
  left join live_runtime l on true
)
select
  checked_at_utc,
  release_target_id,
  target_git_commit,
  target_runtime_fingerprint_sha256,
  target_recorded_at_utc,
  target_source,
  repository,

  latest_canonical_run_id,
  latest_canonical_scan_at_utc,
  live_git_commit,
  scientific_fingerprint_sha256,

  live_runtime_observation_id,
  live_runtime_source_run_id,
  live_runtime_observed_at_utc,
  live_runtime_git_commit,
  live_runtime_fingerprint_sha256,

  comparison_mode,
  deployment_status,
  (deployment_status='DRIFT') as deployment_drift,

  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from classified;

revoke all on public.alpha_hunter_production_deployment_runtime_status_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_production_deployment_runtime_status_v03
  to service_role;


create or replace view public.alpha_hunter_production_deployment_drift_v01
with (security_invoker=true,security_barrier=true) as
select
  checked_at_utc,
  release_target_id,
  target_git_commit,
  target_recorded_at_utc,
  target_source,
  repository,
  latest_canonical_run_id,
  latest_canonical_scan_at_utc,
  live_git_commit,
  scientific_fingerprint_sha256,
  deployment_status,
  deployment_drift,
  shadow_only,
  trade_permission,
  production_promotion_permitted,
  order_path
from public.alpha_hunter_production_deployment_runtime_status_v03;

revoke all on public.alpha_hunter_production_deployment_drift_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_production_deployment_drift_v01
  to service_role;
