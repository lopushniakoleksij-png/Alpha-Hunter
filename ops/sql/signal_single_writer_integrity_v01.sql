-- Alpha Hunter signal single-writer integrity v0.1
--
-- Operations-only observability, outside the sealed V14 scientific fingerprint.
--
-- The canonical scanner is the only permitted writer of alpha_hunter_signals.
-- performance_job.py may verify canonical rows and collect execution-quality
-- evidence, but must not rewrite signal payloads.
--
-- This view checks the exact canonical source_run_id referenced by the latest
-- auxiliary collector telemetry. That avoids false confidence from inspecting a
-- later compact scan in the same hourly burst.

create or replace view public.alpha_hunter_signal_single_writer_integrity_v01
with (security_invoker=true,security_barrier=true) as
with latest_aux as (
  select
    c.collector_run_id,
    c.source_run_id,
    c.checked_at_utc,
    c.collector_status,
    c.subprocess_exit_code,
    c.snapshot_source
  from public.alpha_hunter_execution_quality_collector_runs_v01 c
  where c.source_run_id is not null
  order by c.checked_at_utc desc,c.created_at desc
  limit 1
),
snapshot_identity as (
  select
    s.run_id,
    s.collected_at_utc,
    s.payload->'validation_identity'->>'run_source' as run_source,
    s.payload->'validation_identity'->>'runtime_role' as runtime_role,
    s.payload->'validation_identity'->>'git_commit' as git_commit,
    s.payload->'validation_identity'->>'scientific_fingerprint_sha256'
      as scientific_fingerprint_sha256
  from public.alpha_hunter_snapshots s
  join latest_aux a on a.source_run_id=s.run_id
  limit 1
),
signal_stats as (
  select
    a.source_run_id,
    count(s.*)::integer as signal_rows,
    count(*) filter(
      where s.payload->>'_storage_contract'='signal-source-v0.2'
    )::integer as compact_signal_rows,
    count(*) filter(
      where coalesce(s.payload->>'_storage_contract','LEGACY')
        <>'signal-source-v0.2'
    )::integer as noncompact_signal_rows,
    coalesce(sum(pg_column_size(s.payload)),0)::bigint
      as signal_payload_bytes,
    round(avg(pg_column_size(s.payload))::numeric,1)
      as avg_signal_payload_bytes
  from latest_aux a
  left join public.alpha_hunter_signals s
    on s.run_id=a.source_run_id
  group by a.source_run_id
)
select
  clock_timestamp() as checked_at_utc,

  a.collector_run_id,
  a.source_run_id as auxiliary_source_run_id,
  a.checked_at_utc as auxiliary_checked_at_utc,
  a.collector_status,
  a.subprocess_exit_code,
  a.snapshot_source,

  i.collected_at_utc as source_scan_at_utc,
  i.run_source,
  i.runtime_role,
  i.git_commit,
  i.scientific_fingerprint_sha256,

  coalesce(s.signal_rows,0) as signal_rows,
  coalesce(s.compact_signal_rows,0) as compact_signal_rows,
  coalesce(s.noncompact_signal_rows,0) as noncompact_signal_rows,
  coalesce(s.signal_payload_bytes,0) as signal_payload_bytes,
  s.avg_signal_payload_bytes,

  case
    when a.source_run_id is null then 'NO_AUXILIARY_RUN'
    when coalesce(s.signal_rows,0)=0 then 'NO_SIGNAL_ROWS'
    when coalesce(s.noncompact_signal_rows,0)>0
      then 'SIGNAL_SINGLE_WRITER_REGRESSION'
    when coalesce(s.compact_signal_rows,0)=coalesce(s.signal_rows,0)
      then 'PASS'
    else 'UNKNOWN'
  end as single_writer_status,

  'CANONICAL_SCANNER_ONLY'::text as expected_signal_writer,
  false as auxiliary_signal_write_permitted,
  true as telemetry_only,
  false as mutation_permitted,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from (select 1) anchor
left join latest_aux a on true
left join snapshot_identity i on true
left join signal_stats s on true;

revoke all on public.alpha_hunter_signal_single_writer_integrity_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_signal_single_writer_integrity_v01
  to service_role;
