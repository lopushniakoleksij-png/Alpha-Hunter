-- ALPHA HUNTER / STAGE 2 — SAFE STRUCTURAL FINGERPRINTS v01
-- Read-only, metadata-only; contains no role passwords, row data or function bodies.
-- Execute this exact SQL on production AND on the private local Postgres 17 clone.
-- A matching result is NECESSARY but NOT SUFFICIENT for fidelity; confirm
-- permissions, SECURITY DEFINER ownership, all extensions, dynamic dependencies,
-- config/GUCs, sample historical-data shape and side effects separately.
with app_rels as (
  select c.oid, c.relname, c.relkind, c.relrowsecurity,
         c.relforcerowsecurity, c.relacl::text as rel_acl
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relname like 'alpha_hunter_%'
    and c.relkind in ('r','p')
),
columns_all as (
  select r.relname, a.attnum, a.attname,
         pg_catalog.format_type(a.atttypid,a.atttypmod) as data_type,
         a.attnotnull as not_null, a.attidentity, a.attgenerated,
         coalesce(pg_catalog.pg_get_expr(d.adbin,d.adrelid),'') as default_expr
  from app_rels r
  join pg_catalog.pg_attribute a on a.attrelid=r.oid
  left join pg_catalog.pg_attrdef d on d.adrelid=r.oid and d.adnum=a.attnum
  where a.attnum>0 and not a.attisdropped
),
idx as (
  select r.relname, ic.relname index_name,
         pg_catalog.pg_get_indexdef(i.indexrelid) as index_ddl
  from app_rels r
  join pg_catalog.pg_index i on i.indrelid=r.oid
  join pg_catalog.pg_class ic on ic.oid=i.indexrelid
),
trigs as (
  select c.relname, t.tgname, p.oid function_oid, p.prosecdef,
         pg_catalog.md5(pg_catalog.pg_get_triggerdef(t.oid)) as trig_hash,
         pg_catalog.md5(pg_catalog.pg_get_functiondef(p.oid)) as func_hash
  from pg_catalog.pg_trigger t
  join pg_catalog.pg_class c on c.oid=t.tgrelid
  join pg_catalog.pg_namespace n on n.oid=c.relnamespace
  join pg_catalog.pg_proc p on p.oid=t.tgfoid
  where n.nspname='public' and c.relname like 'alpha_hunter_%'
    and not t.tgisinternal
),
policies as (
  select r.relname, p.polname
  from app_rels r join pg_catalog.pg_policy p on p.polrelid=r.oid
)
select
  (select count(*) from app_rels) as application_tables,
  (select count(*) from app_rels where relrowsecurity) as rls_enabled_tables,
  (select count(*) from columns_all) as application_columns,
  (select count(*) from idx) as indexes,
  (select count(*) from policies) as policies,
  (select count(*) from trigs) as application_triggers,
  (select count(distinct relname) from trigs) as trigger_bearing_tables,
  (select count(distinct function_oid) from trigs) as distinct_trigger_functions,
  (select count(*) from trigs where prosecdef) as definer_trigger_call_sites,
  (select pg_catalog.md5(string_agg(
          relname||':'||attnum::text||':'||attname||':'||data_type||':'||
          not_null::text||':'||attidentity::text||':'||attgenerated::text||':'||default_expr,
          E'\n' order by relname,attnum)) from columns_all) as columns_fingerprint,
  (select pg_catalog.md5(string_agg(
          relname||':'||index_name||':'||index_ddl,E'\n' order by relname,index_name))
   from idx) as indexes_fingerprint,
  (select pg_catalog.md5(string_agg(
          relname||':'||tgname||':'||trig_hash||':'||func_hash,
          E'\n' order by relname,tgname))
   from trigs) as triggers_functions_fingerprint,
  (select pg_catalog.md5(string_agg(
          relname||':'||coalesce(rel_acl,'NULL')||':'||
          relrowsecurity::text||':'||relforcerowsecurity::text,
          E'\n' order by relname))
   from app_rels) as table_grants_rls_fingerprint;

-- Independent extensions inventory; versions and schemas must match or be
-- reviewed as genuine compatibility differences before any PASS.
select x.extname, x.extversion, n.nspname as extension_schema
from pg_catalog.pg_extension x
join pg_catalog.pg_namespace n on n.oid=x.extnamespace
order by x.extname;