-- P0.3 source census: SELECT-only, reproducible SHA256 of parent payload and ordered child symbol identities.
WITH parents AS MATERIALIZED (
 SELECT p.run_id,p.collected_at_utc,p.symbol_count,p.error_count,
 p.payload, COALESCE(p.payload->>'_canonical_publication_state','UNMARKED') AS pub
 FROM public.alpha_hunter_snapshots p
 WHERE p.collected_at_utc >= timestamptz '2026-10-04T00:00:00Z'
 AND p.collected_at_utc < timestamptz '2026-11-04T00:00:00Z'
 AND p.payload #>> '{validation_identity,run_source}' = 'RENDER_CRON'
), children AS (
 SELECT s.run_id, COUNT(*)::int AS child_count,
 encode(sha256(convert_to(string_agg(s.symbol, '|' ORDER BY s.symbol),'UTF8')),'hex') AS child_names_sha256
 FROM public.alpha_hunter_symbol_snapshots s JOIN parents p USING(run_id)
 GROUP BY s.run_id
), enriched AS (
 SELECT (p.collected_at_utc AT TIME ZONE 'UTC')::date AS day_utc,
 p.run_id,p.collected_at_utc,p.symbol_count,p.error_count,p.pub,
 COALESCE(c.child_count,0) AS child_count,COALESCE(c.child_names_sha256,'NONE') AS child_names_sha256,
 encode(sha256(convert_to(p.payload::text,'UTF8')),'hex') AS parent_payload_sha256
 FROM parents p LEFT JOIN children c USING(run_id)
)
SELECT statement_timestamp() AT TIME ZONE 'UTC' AS captured_at_utc,
 current_setting('server_version') AS pg_version, day_utc::text,
 COUNT(*)::int AS parent_runs,
 COUNT(*) FILTER (WHERE child_count=0)::int AS zero_child_runs,
 COUNT(*) FILTER (WHERE child_count<>symbol_count)::int AS incomplete_child_runs,
 SUM(symbol_count)::int AS advertised_symbols,SUM(child_count)::int AS saved_children,
 COUNT(*) FILTER (WHERE pub='VERIFIED')::int AS verified_pub_markers,
 COUNT(*) FILTER (WHERE error_count=0)::int AS zero_error_parents,
 encode(sha256(convert_to(string_agg(
 run_id || '|' || to_char(collected_at_utc AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
 || '|' || symbol_count || '|' || error_count || '|' || pub || '|' || child_count 
 || '|' || parent_payload_sha256 || '|' || child_names_sha256,
 E'\n' ORDER BY run_id),'UTF8')),'hex') AS census_sha256
FROM enriched
GROUP BY day_utc ORDER BY day_utc ASC;
