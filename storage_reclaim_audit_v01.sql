-- Alpha Hunter storage reclaim audit v0.1
--
-- Purpose:
--   Quantify where PostgreSQL disk is physically concentrated before any
--   archival/recompaction decision is made.
--
-- This is telemetry only. It performs no row mutation, retention change,
-- archive operation, table rewrite, or disk reclamation action.

create or replace view public.alpha_hunter_storage_reclaim_audit_v01
with (security_invoker=true, security_barrier=true) as
with targets(table_name) as (
  values
    ('alpha_hunter_snapshots'::text),
    ('alpha_hunter_symbol_snapshots'::text),
    ('alpha_hunter_signals'::text),
    ('alpha_hunter_signal_features'::text),
    ('alpha_hunter_strategy_observations_v01'::text),
    ('alpha_hunter_universe_hourly'::text)
),
relations as (
  select
    t.table_name,
    c.oid as relation_oid,
    c.reltoastrelid as toast_oid,
    coalesce(s.n_live_tup,0)::bigint as live_rows,
    coalesce(s.n_dead_tup,0)::bigint as dead_rows,
    s.last_vacuum,
    s.last_autovacuum,
    s.last_analyze,
    s.last_autoanalyze
  from targets t
  join pg_namespace n
    on n.nspname='public'
  join pg_class c
    on c.relnamespace=n.oid
   and c.relname=t.table_name
   and c.relkind='r'
  left join pg_stat_user_tables s
    on s.relid=c.oid
),
measured as (
  select
    r.*,
    pg_total_relation_size(r.relation_oid)::bigint as total_bytes,
    pg_relation_size(r.relation_oid)::bigint as heap_bytes,
    pg_indexes_size(r.relation_oid)::bigint as index_bytes,
    case
      when r.toast_oid<>0 then pg_total_relation_size(r.toast_oid)::bigint
      else 0::bigint
    end as toast_bytes,
    coalesce(ts.n_live_tup,0)::bigint as toast_live_rows,
    coalesce(ts.n_dead_tup,0)::bigint as toast_dead_rows,
    ts.last_vacuum as toast_last_vacuum,
    ts.last_autovacuum as toast_last_autovacuum
  from relations r
  left join pg_stat_all_tables ts
    on ts.relid=r.toast_oid
)
select
  clock_timestamp() as checked_at_utc,
  table_name,
  live_rows,
  dead_rows,
  total_bytes,
  heap_bytes,
  index_bytes,
  toast_bytes,
  toast_live_rows,
  toast_dead_rows,
  round(
    case
      when total_bytes>0
        then toast_bytes::numeric / total_bytes::numeric * 100
      else 0::numeric
    end,
    2
  ) as toast_pct_of_relation,
  pg_size_pretty(total_bytes) as total_size_pretty,
  pg_size_pretty(heap_bytes) as heap_size_pretty,
  pg_size_pretty(index_bytes) as index_size_pretty,
  pg_size_pretty(toast_bytes) as toast_size_pretty,
  last_vacuum,
  last_autovacuum,
  last_analyze,
  last_autoanalyze,
  toast_last_vacuum,
  toast_last_autovacuum,
  case
    when toast_bytes >= 50::bigint * 1024 * 1024
         and toast_live_rows>0
      then 'LIVE_TOAST_ARCHIVE_OR_RECOMPACT_REVIEW'
    when dead_rows>0 or toast_dead_rows>0
      then 'ORDINARY_VACUUM_ANALYZE_REVIEW'
    else 'MONITOR'
  end as maintenance_class,
  case
    when toast_bytes >= 50::bigint * 1024 * 1024
         and toast_live_rows>0
      then false
    else null
  end as ordinary_vacuum_expected_to_solve_live_payload_size,
  true as telemetry_only,
  false as mutation_permitted
from measured;

comment on view public.alpha_hunter_storage_reclaim_audit_v01 is
  'Read-only storage/TOAST audit used to plan archival or recompaction safely. '
  'It performs no data mutation and grants no execution authority.';

revoke all on public.alpha_hunter_storage_reclaim_audit_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_storage_reclaim_audit_v01
  to service_role;


create or replace view public.alpha_hunter_storage_reclaim_summary_v01
with (security_invoker=true, security_barrier=true) as
select
  clock_timestamp() as checked_at_utc,
  pg_database_size(current_database())::bigint as database_bytes,
  pg_size_pretty(pg_database_size(current_database())) as database_size_pretty,
  sum(total_bytes)::bigint as audited_relation_bytes,
  pg_size_pretty(sum(total_bytes)::bigint) as audited_relation_size_pretty,
  sum(toast_bytes)::bigint as audited_toast_bytes,
  pg_size_pretty(sum(toast_bytes)::bigint) as audited_toast_size_pretty,
  count(*) filter(
    where maintenance_class='LIVE_TOAST_ARCHIVE_OR_RECOMPACT_REVIEW'
  )::integer as live_toast_review_tables,
  true as telemetry_only,
  false as mutation_permitted
from public.alpha_hunter_storage_reclaim_audit_v01;

comment on view public.alpha_hunter_storage_reclaim_summary_v01 is
  'Read-only rollup of Alpha Hunter storage concentration; no reclaim action is executed.';

revoke all on public.alpha_hunter_storage_reclaim_summary_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_storage_reclaim_summary_v01
  to service_role;
