-- ALPHA HUNTER / STAGE 2 - READ-ONLY PUBLIC TRIGGER SUPERSET INVENTORY V02
-- No DDL, DML, EXPLAIN ANALYZE, credentials or private SQL function bodies.
-- Execute inside a trusted session and keep detailed output with the private DBA.
-- This is a conservative inventory of ALL alpha_hunter_% trigger-bearing tables.
-- It is NOT proof of the transitive write dependency graph: PL/pgSQL dynamic
-- statements / extension objects / cross-schema triggers may require more work.
--
-- 1. Reproducible top-level fingerprint and definer count.
with inventory as (
  select n.nspname as schema_name, c.relname as table_name, t.tgname,
         p.oid as function_oid, p.prosecdef as security_definer,
         md5(pg_catalog.pg_get_triggerdef(t.oid)) as trigger_hash,
         md5(pg_catalog.pg_get_functiondef(p.oid)) as function_hash
  from pg_catalog.pg_trigger t
  join pg_catalog.pg_class c on c.oid=t.tgrelid
  join pg_catalog.pg_namespace n on n.oid=c.relnamespace
  join pg_catalog.pg_proc p on p.oid=t.tgfoid
  where n.nspname='public' and not t.tgisinternal
    and c.relname like 'alpha_hunter_%'
)
select count(*) as app_trigger_count,
       count(distinct table_name) as trigger_bearing_tables,
       count(distinct function_oid) as trigger_functions,
       count(*) filter (where security_definer) as security_definer_call_sites,
       md5(string_agg(schema_name||'.'||table_name||'/'||tgname||':'||
                      trigger_hash||':'||function_hash, ';'
                      order by table_name,tgname)) as inventory_fingerprint
from inventory;

-- 2. Per-trigger fingerprint, with no function or trigger source bodies.
select n.nspname as schema_name,
       c.relname as table_name,
       t.tgname as trigger_name,
       p.proname as function_name,
       pn.nspname as function_schema,
       p.prosecdef as security_definer,
       t.tgenabled as trigger_enabled_mode,
       md5(pg_catalog.pg_get_triggerdef(t.oid)) as trigger_ddl_hash,
       md5(pg_catalog.pg_get_functiondef(p.oid)) as function_body_hash
from pg_catalog.pg_trigger t
join pg_catalog.pg_class c on c.oid=t.tgrelid
join pg_catalog.pg_namespace n on n.oid=c.relnamespace
join pg_catalog.pg_proc p on p.oid=t.tgfoid
join pg_catalog.pg_namespace pn on pn.oid=p.pronamespace
where n.nspname='public' and not t.tgisinternal
  and c.relname like 'alpha_hunter_%'
order by c.relname,t.tgname;

-- 3. Failed promotion guard (should both be FALSE until independent approval).
select pg_catalog.to_regprocedure('public.alpha_hunter_commit_core_scan_v01(jsonb,jsonb,jsonb,jsonb,jsonb)') is not null
         as atomic_core_rpc_installed,
       pg_catalog.to_regclass('public.idx_ah_payoff_geometry_percentiles_candidate_v01') is not null
         as candidate_percentile_index_installed;
