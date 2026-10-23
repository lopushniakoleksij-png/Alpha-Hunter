-- P0 review-only, catalog/pg_stat metadata. ONE READ-ONLY SELECT.
-- No EXPLAIN ANALYZE, lock injection, raw API SQL credentials, or db writes.
-- Snapshot statistics are approximate and NOT root-cause attribution.
WITH trigger_edges AS (
  SELECT c.relname AS source_relation,p.proname AS trigger_function,
         t.tgname AS trigger_name,t.tgenabled AS enabled
  FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace
    JOIN pg_proc p ON p.oid=t.tgfoid
  WHERE n.nspname='public' AND NOT t.tgisinternal
    AND c.relname IN ('alpha_hunter_symbol_snapshots',
                      'alpha_hunter_strategy_observations_v01',
                      'alpha_hunter_strategy_episodes_v01')
), relation_stats AS (
  SELECT c.relname AS relation,
         c.reltuples::bigint AS estimated_rows,
         pg_relation_size(c.oid) AS table_bytes,
         s.n_tup_ins AS insertion_counter_since_stats_reset,
         s.n_dead_tup AS dead_tuples_estimated,
         s.last_autoanalyze
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  LEFT JOIN pg_stat_user_tables s ON s.relid=c.oid
  WHERE n.nspname='public'
    AND c.relname IN ('alpha_hunter_symbol_snapshots',
                      'alpha_hunter_strategy_observations_v01',
                      'alpha_hunter_strategy_episodes_v01')
), role_limits AS (
  SELECT r.rolname AS role_name, cfg AS role_specific_timeout_setting
  FROM pg_db_role_setting d JOIN pg_roles r ON r.oid=d.setrole
  CROSS JOIN LATERAL unnest(d.setconfig) AS cfg
  WHERE r.rolname IN ('anon','authenticated','authenticator','service_role')
    AND cfg LIKE 'statement_timeout=%'
)
SELECT now() AS read_at_utc,
  current_setting('statement_timeout') AS catalog_reader_statement_timeout_not_api_role,
  (SELECT count(*) FROM trigger_edges
      WHERE source_relation='alpha_hunter_symbol_snapshots'
        AND trigger_function='alpha_hunter_capture_strategy_observations_v01'
        AND enabled='O') AS enabled_symbol_strategy_trigger_count,
  (SELECT coalesce(jsonb_agg(jsonb_build_object('table',source_relation,
       'trigger',trigger_name,'function',trigger_function,'enabled',enabled)
       ORDER BY source_relation,trigger_name),'[]'::jsonb) FROM trigger_edges)
       AS trigger_chain_metadata,
  (SELECT coalesce(jsonb_agg(jsonb_build_object('relation',relation,
       'estimated_rows',estimated_rows,'table_bytes',table_bytes,
       'insert_counter',insertion_counter_since_stats_reset,
       'dead_tuples_estimate',dead_tuples_estimated,
       'last_autoanalyze',last_autoanalyze) ORDER BY relation),'[]'::jsonb)
   FROM relation_stats) AS aggregate_relation_stats,
  (SELECT coalesce(jsonb_agg(jsonb_build_object(
     'role',role_name,'timeout',role_specific_timeout_setting)
     ORDER BY role_name),'[]'::jsonb) FROM role_limits) AS configured_role_timeouts,
  false AS exact_source_of_57014_proven,
  false AS authorization_to_change_timeout_or_trigger,
  false AS permission_to_deploy_successor;
