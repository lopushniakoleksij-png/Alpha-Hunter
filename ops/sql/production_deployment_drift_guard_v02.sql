-- Alpha Hunter runtime deployment target semantics v0.2
--
-- Operations-only observability, outside the sealed V14 scientific fingerprint.
--
-- v0.1 recorded every GitHub main push as a Render deployment target. That
-- created false drift after ops-only SQL/test/documentation commits.
--
-- v0.2:
-- - preserves the complete historical ledger;
-- - adds runtime-specific source classes;
-- - seeds the currently deployed canonical RENDER_CRON commit as a manual
--   runtime baseline;
-- - deployment drift compares only runtime-target rows.

alter table public.alpha_hunter_production_release_targets_v01
  drop constraint if exists
  alpha_hunter_production_release_targets_v01_source_check;

alter table public.alpha_hunter_production_release_targets_v01
  add constraint alpha_hunter_production_release_targets_v01_source_check
  check (
    source in (
      'GITHUB_MAIN_PUSH',
      'MANUAL_AUDIT',
      'GITHUB_RUNTIME_PUSH',
      'MANUAL_RUNTIME_TARGET'
    )
  );

insert into public.alpha_hunter_production_release_targets_v01(
  release_target_id,
  git_commit,
  recorded_at_utc,
  source,
  repository,
  shadow_only,
  trade_permission,
  production_promotion_permitted,
  order_path
)
select
  'runtime-baseline-'||left(
    s.payload->'validation_identity'->>'git_commit',
    16
  ),
  s.payload->'validation_identity'->>'git_commit',
  clock_timestamp(),
  'MANUAL_RUNTIME_TARGET',
  'lopushniakoleksij-png/Alpha-Hunter',
  true,
  false,
  false,
  'NONE'
from public.alpha_hunter_snapshots s
where s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
  and coalesce(s.payload->'validation_identity'->>'git_commit','')<>''
order by s.collected_at_utc desc
limit 1
on conflict (release_target_id) do nothing;


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
  where r.source in ('GITHUB_RUNTIME_PUSH','MANUAL_RUNTIME_TARGET')
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
    when t.target_git_commit is null then 'NO_RUNTIME_TARGET'
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
