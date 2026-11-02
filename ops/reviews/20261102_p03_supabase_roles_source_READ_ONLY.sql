-- ALPHA HUNTER P0.3 -- DBA/SECURITY PRODUCTION READ-ONLY CATALOG REVIEW
-- Date: 2026-11-02 UTC. SELECT ONLY. No role switches, DDL, DML, live orders,
-- index changes, policy changes, key reads, secrets, or migrations.
-- Execute only with independent reviewer-authorized read-only privileges.

-- 1. SQL roles do not equal actual Data API JWT impersonation.
SELECT rolname,rolcanlogin,rolbypassrls,rolsuper
FROM pg_roles
WHERE rolname IN ('anon','authenticated','authenticator','service_role','postgres')
ORDER BY rolname;

-- 2. Explicit grants AND RLS policy count on sensitive real tables.
SELECT c.relname, c.relrowsecurity AS rls_enabled,
  c.relforcerowsecurity AS force_rls,
  (SELECT count(*) FROM pg_policies p
    WHERE p.schemaname='public' AND p.tablename=c.relname) AS policy_count,
  has_table_privilege('anon',c.oid,'SELECT') AS anon_sql_select_grant,
  has_table_privilege('anon',c.oid,'INSERT') AS anon_sql_insert_grant,
  has_table_privilege('authenticated',c.oid,'SELECT') AS authenticated_sql_select_grant,
  has_table_privilege('authenticated',c.oid,'INSERT') AS authenticated_sql_insert_grant,
  has_table_privilege('service_role',c.oid,'SELECT') AS service_sql_select_grant,
  has_table_privilege('service_role',c.oid,'INSERT') AS service_sql_insert_grant
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='r'
  AND c.relname IN (
    'alpha_hunter_snapshots','alpha_hunter_symbol_snapshots',
    'alpha_hunter_paper_exit_attempts_v04',
    'alpha_hunter_profitability_test_activations_v01',
    'alpha_hunter_account_state_snapshots','alpha_hunter_open_position_snapshots',
    'alpha_hunter_execution_decision_freezes_v01')
ORDER BY c.relname;

-- 3. PUBLIC functions that might bypass RLS. Metadata not a penetration test.
SELECT n.nspname,p.proname,p.prosecdef,
  p.proowner::regrole AS owner,p.proconfig AS search_path_config,
  has_function_privilege('anon',p.oid,'EXECUTE') AS anon_sql_execute,
  has_function_privilege('authenticated',p.oid,'EXECUTE') AS authenticated_sql_execute,
  has_function_privilege('service_role',p.oid,'EXECUTE') AS service_sql_execute
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname IN ('public','private')
  AND p.proname LIKE 'alpha_hunter_%'
  AND p.prosecdef
ORDER BY n.nspname,p.proname LIMIT 150;

-- 4. Sensitive invoker views must not bypass table policies.
SELECT c.relname,c.reloptions,
  has_table_privilege('anon',c.oid,'SELECT') AS anon_sql_select,
  has_table_privilege('authenticated',c.oid,'SELECT') AS auth_sql_select
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='v' AND c.relname IN (
  'alpha_hunter_execution_cost_floor_status_v01',
  'alpha_hunter_paper_protection_horizon_open_v09')
ORDER BY c.relname;

-- 5. Previously recorded source evidence is not independently authenticated.
WITH recent AS (
 SELECT a.entry_order_id,a.source_run_id,a.observed_at_utc,a.evidence,
        p.run_id AS parent_id,
        p.payload->>'_canonical_publication_state' AS publication_state
 FROM public.alpha_hunter_paper_exit_attempts_v04 a
 LEFT JOIN public.alpha_hunter_snapshots p ON p.run_id=a.source_run_id
 WHERE a.observed_at_utc >= timestamptz '2026-11-01 00:00+00'
)
SELECT count(*) AS recent_receipts,
 count(*) FILTER (WHERE parent_id IS NOT NULL) AS parent_linked,
 count(*) FILTER (WHERE publication_state='VERIFIED') AS verified_parents,
 count(*) FILTER (WHERE evidence->>'captured_quote_only'='true') AS public_quote_only,
 count(*) FILTER (WHERE evidence->>'quote_source' IS NULL) AS missing_source_label,
 count(*) FILTER (WHERE evidence ? 'provider_signature') AS claimed_provider_signature
FROM recent;

-- 6. Research note: no live signed exchange HTTP headers, keys or quote
-- content should be exported to GitHub. Independent time/source custody must
-- be built prospectively on an authorized, isolated producer.
