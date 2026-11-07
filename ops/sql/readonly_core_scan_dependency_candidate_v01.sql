-- ALPHA HUNTER / ISOLATED REPAIR - PRODUCTION READ-ONLY GRAPH LEADS V01
-- SQL only reads PostgreSQL catalogs. Do not run EXPLAIN ANALYZE here.
-- It does NOT reproduce an executable trigger graph or a private clone.
-- Lexical references can include SELECT-only tables, comments or false matches;
-- dynamic SQL, nested function calls, cross-schema objects and extensions may
-- be missed. Treat results as DBA review leads, NOT release acceptance.
-- No private function bodies, secrets, row data or DDL in the output.
WITH RECURSIVE
roots(name) AS (
  VALUES ('alpha_hunter_snapshots'::text),
         ('alpha_hunter_symbol_snapshots'),
         ('alpha_hunter_signals'),
         ('alpha_hunter_signal_features'),
         ('alpha_hunter_readiness_observations_v01')
),
tr AS (
  SELECT c.relname::text AS source_table, t.tgname::text AS trigger_name,
         p.oid AS function_oid, lower(pg_get_functiondef(p.oid)) AS definition
  FROM pg_trigger t
  JOIN pg_class c ON c.oid=t.tgrelid
  JOIN pg_namespace n ON n.oid=c.relnamespace
  JOIN pg_proc p ON p.oid=t.tgfoid
  WHERE n.nspname='public' AND NOT t.tgisinternal
),
rels AS (
  SELECT c.relname::text AS relname
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND c.relname LIKE 'alpha_hunter_%'
    AND c.relkind IN ('r','p','v','m')
),
links AS (
  SELECT DISTINCT tr.source_table,rels.relname AS target_table
  FROM tr JOIN rels ON position(lower(rels.relname) in tr.definition)>0
  WHERE rels.relname <> tr.source_table
),
walk(table_name, depth, path) AS (
  SELECT name COLLATE "C",0,ARRAY[name COLLATE "C"] FROM roots
  UNION ALL
  SELECT l.target_table COLLATE "C", w.depth+1,
         w.path||(l.target_table COLLATE "C")
  FROM walk w JOIN links l ON l.source_table=w.table_name
  WHERE w.depth<5 AND NOT(l.target_table=ANY(w.path))
),
reached AS (SELECT DISTINCT table_name FROM walk)
SELECT w.depth,
       count(DISTINCT w.table_name) AS candidate_tables_at_depth,
       (SELECT count(*) FROM reached) AS total_unique_candidate_relations,
       (SELECT count(DISTINCT (tr.source_table,tr.trigger_name))
          FROM tr JOIN reached r ON r.table_name=tr.source_table) AS candidate_triggers,
       (SELECT count(DISTINCT tr.function_oid)
          FROM tr JOIN reached r ON r.table_name=tr.source_table) AS candidate_trigger_functions,
       string_agg(DISTINCT w.table_name, ', ' ORDER BY w.table_name) AS candidate_table_names
FROM walk w
GROUP BY w.depth ORDER BY w.depth;
-- IMPORTANT: the production-equivalent PostgreSQL 17 clone is NOT established.
-- Full acceptance requires private logical schema export, roles, extensions,
-- transitive dynamic-SQL/side-effect inspection, and benchmark on that clone.
