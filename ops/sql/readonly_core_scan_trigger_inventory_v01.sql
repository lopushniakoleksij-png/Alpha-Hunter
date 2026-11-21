-- READ-ONLY live database inventory for independent private DBA review.
-- No source bodies, production row payloads, credentials, secrets or mutations.
-- Execute in Supabase SQL editor with an authorised read-only account.
-- Compare inventory fingerprints between live production and the PRIVATE clone.
-- Do not publish results that include internal private function definitions.
with target_tables(table_name) as (
  values
    ('alpha_hunter_snapshots'),
    ('alpha_hunter_symbol_snapshots'),
    ('alpha_hunter_signals'),
    ('alpha_hunter_signal_features'),
    ('alpha_hunter_readiness_observations_v01'),
    ('alpha_hunter_strategy_observations_v01'),
    ('alpha_hunter_shadow_decision_quotes_v01'),
    ('alpha_hunter_execution_decision_freezes_v01')
)
select
  n.nspname as schema_name,
  c.relname as source_table,
  t.tgname as trigger_name,
  pn.nspname as function_schema,
  p.proname as function_name,
  md5(pg_get_triggerdef(t.oid)) as trigger_ddl_fingerprint,
  md5(pg_get_functiondef(p.oid)) as function_body_fingerprint,
  pg_get_triggerdef(t.oid) as trigger_definition
from pg_trigger t
join pg_class c on c.oid=t.tgrelid
join pg_namespace n on n.oid=c.relnamespace
join pg_proc p on p.oid=t.tgfoid
join pg_namespace pn on pn.oid=p.pronamespace
join target_tables x on x.table_name=c.relname
where n.nspname='public'
  and not t.tgisinternal
order by c.relname,t.tgname;

-- Confirm no production promotion occurred inadvertently:
select
  to_regprocedure('public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)') is not null
    as atomic_core_rpc_installed,
  to_regclass('public.idx_ah_payoff_geometry_percentiles_candidate_v01') is not null
    as candidate_percentile_index_installed;

-- Parent-child completeness for recent actual production observations:
with recent as (
  select run_id,collected_at_utc,symbol_count,error_count
  from public.alpha_hunter_snapshots
  order by collected_at_utc desc limit 8
)
select
 r.run_id,r.collected_at_utc,r.symbol_count,r.error_count,
 (select count(*) from public.alpha_hunter_symbol_snapshots x where x.run_id=r.run_id) as symbol_rows,
 (select count(*) from public.alpha_hunter_signals x where x.run_id=r.run_id) as signal_rows,
 (select count(*) from public.alpha_hunter_signal_features x where x.run_id=r.run_id) as feature_rows,
 (select count(*) from public.alpha_hunter_readiness_observations_v01 x where x.run_id=r.run_id) as readiness_rows
from recent r order by r.collected_at_utc desc;
