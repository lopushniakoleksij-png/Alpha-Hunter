-- ALPHA HUNTER P0 — READ-ONLY CROSS-SCHEMA FUNCTION CUSTODY FINGERPRINT.
-- Returns only counts and MD5 inventory digests: no private function bodies,
-- passwords, SQL snippets, data rows or encrypted Vault values.
-- Execute the same query on production and an authorized PRIVATE clone.
-- A matching digest is necessary, not proof of runtime/behavior equivalence.
WITH selected_functions AS (
 SELECT
   n.nspname AS schema_name, p.proname AS function_name,
   pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
   pg_catalog.pg_get_userbyid(p.proowner) AS owner_name,
   p.prokind, p.prosecdef, p.provolatile,
   coalesce(p.proconfig::text,'') AS runtime_settings,
   coalesce(p.proacl::text,'') AS acl_state,
   pg_catalog.md5(pg_catalog.pg_get_functiondef(p.oid)) AS body_digest
 FROM pg_catalog.pg_proc p
 JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
 WHERE (
       n.nspname='private'
    OR (n.nspname='public' AND p.proname LIKE 'alpha_hunter_%')
   )
   AND p.prokind IN ('f','p','w')
)
SELECT schema_name,
  count(*) AS functions,
  count(*) FILTER (WHERE prosecdef) AS security_definer_functions,
  count(*) FILTER (WHERE runtime_settings <> '') AS customized_runtime_settings,
  md5(string_agg(
       function_name||'('||arguments||')|'||owner_name||'|'||
       prokind::text||'|'||prosecdef::text||'|'||provolatile::text||'|'||
       runtime_settings||'|'||acl_state||'|'||body_digest,
       E'\n' ORDER BY function_name,arguments)) AS full_function_custody_fingerprint
FROM selected_functions
GROUP BY schema_name
ORDER BY schema_name;

-- Include all reachable trigger-bearing private schema tables, not merely
-- public.alpha_hunter_% objects already in the stage2 structural fingerprint.
WITH private_triggers AS (
 SELECT n.nspname,c.relname,t.tgname,t.tgenabled,
        pn.nspname AS function_schema, p.proname AS function_name,
        md5(pg_catalog.pg_get_triggerdef(t.oid)) AS trigger_def_digest,
        md5(pg_catalog.pg_get_functiondef(p.oid)) AS function_body_digest
 FROM pg_catalog.pg_trigger t
 JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
 JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
 WHERE n.nspname='private' AND NOT t.tgisinternal
)
SELECT count(*) AS private_schema_application_triggers,
       count(DISTINCT relname) AS private_trigger_tables,
       md5(string_agg(
           relname||'/'||tgname||'/'||tgenabled||'/'||
           function_schema||'.'||function_name||':'||
           trigger_def_digest||':'||function_body_digest,
           E'\n' ORDER BY relname,tgname)) AS private_trigger_fingerprint
FROM private_triggers;
