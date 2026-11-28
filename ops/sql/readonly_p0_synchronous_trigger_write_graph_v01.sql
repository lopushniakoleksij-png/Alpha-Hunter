-- ALPHA HUNTER P0 / HARADA A2 + B6: PRODUCTION READ-ONLY META INVENTORY.
-- NEVER returns private function bodies, credentials, rows or payloads.
-- Maps reached tables plus statically visible INSERT/UPDATE references only.
-- Dynamic EXECUTE/SQL, hidden referenced functions, extension side effects,
-- roles and runtime configuration are NOT proven by this inventory alone.
-- Execute read-only on production and on an authorized PRIVATE clone.
WITH triggers AS (
 SELECT n.nspname source_schema,c.relname source_table,
   t.tgname trigger_name,t.tgenabled trigger_enabled,
   pn.nspname function_schema,p.proname function_name,p.prosecdef security_definer,
   pg_catalog.md5(pg_catalog.pg_get_triggerdef(t.oid)) trigger_fingerprint,
   pg_catalog.md5(pg_catalog.pg_get_functiondef(p.oid)) function_fingerprint,
   pg_catalog.pg_get_functiondef(p.oid) definition
 FROM pg_catalog.pg_trigger t
 JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
 JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
 WHERE n.nspname IN ('public','private') AND NOT t.tgisinternal
   AND c.relname IN (
      'alpha_hunter_symbol_snapshots',
      'alpha_hunter_strategy_observations_v01',
      'alpha_hunter_strategy_episodes_v01',
      'alpha_hunter_shadow_decision_quotes_v01',
      'alpha_hunter_execution_decision_freezes_v01',
      'alpha_hunter_strategy_24h_outcome_queue_v01',
      'alpha_hunter_payoff_geometry_health_observations_v01',
      'alpha_hunter_calibrated_paper_orders_v01')
)
SELECT source_schema,source_table,trigger_name,trigger_enabled,
 function_schema||'.'||function_name AS function_name,
 security_definer,trigger_fingerprint,function_fingerprint,
 coalesce(array_agg(DISTINCT lower(m.hit[1]))
          FILTER(WHERE m.hit IS NOT NULL), ARRAY[]::text[]) AS static_write_references
FROM triggers t LEFT JOIN LATERAL
 pg_catalog.regexp_matches(t.definition,
 '(?i)(insert[[:space:]]+into[[:space:]]+(?:public|private)[.]alpha_hunter_[a-z0-9_]+|update[[:space:]]+(?:public|private)[.]alpha_hunter_[a-z0-9_]+)',
 'g') AS m(hit) ON true
GROUP BY source_schema,source_table,trigger_name,trigger_enabled,
 function_schema,function_name,security_definer,
 trigger_fingerprint,function_fingerprint
ORDER BY source_schema,source_table,trigger_name;

-- Sink check (optional second query to execute independently):
-- SELECT n.nspname,c.relname,
--   count(*) FILTER(WHERE NOT t.tgisinternal) AS application_triggers
-- FROM pg_catalog.pg_class c
-- JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
-- LEFT JOIN pg_catalog.pg_trigger t ON t.tgrelid=c.oid
-- WHERE n.nspname='private'
-- AND c.relname IN ('alpha_hunter_strategy_24h_outcome_queue_v01',
--                   'alpha_hunter_payoff_geometry_health_observations_v01',
--                   'alpha_hunter_calibrated_paper_orders_v01')
-- GROUP BY n.nspname,c.relname;
