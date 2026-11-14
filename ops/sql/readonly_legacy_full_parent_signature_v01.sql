-- ALPHA HUNTER P0 — READ-ONLY LEGACY FULL-PARENT WRITER SIGNATURE V01.
-- Detects obsolete storage format from metadata/JSON field presence only.
-- No private row values, function bodies, IP addresses or credentials returned.
-- A matched source claim is NOT independently authenticated.
-- Inspect a bounded 48h cohort; never mutate/repair old evidence in this query.
WITH recent AS (
  SELECT run_id, collected_at_utc, created_at, symbol_count,
         payload,
         CASE
           WHEN NOT (payload ? '_storage_contract')
             AND NOT (payload ? 'validation_identity')
             AND jsonb_typeof(payload->'symbols'->0) = 'object'
             AND (payload->'symbols'->0) ? 'intelligence'
             THEN 'LEGACY_FULL_PARENT_UNATTRIBUTED'
           WHEN payload->>'_storage_contract' = 'snapshot-parent-v0.2'
             AND nullif(payload->'validation_identity'->>'run_source','') IS NOT NULL
             AND nullif(payload->'validation_identity'->>'runtime_role','') IS NOT NULL
             AND NOT coalesce((payload->'symbols'->0) ? 'intelligence', false)
             THEN 'MODERN_COMPACT_CLAIM_NOT_AUTHENTICATED'
           ELSE 'OTHER_SOURCE_OR_FORMAT_UNVERIFIED'
         END AS signature
  FROM public.alpha_hunter_snapshots
  WHERE collected_at_utc >= now() - interval '48 hours'
  ORDER BY collected_at_utc DESC
  LIMIT 250
), readiness AS (
  SELECT r.signature, r.collected_at_utc, r.created_at, r.symbol_count,
         (SELECT count(*)
          FROM public.alpha_hunter_readiness_observations_v01 o
          WHERE o.run_id = r.run_id) AS readiness_rows
  FROM recent r
)
SELECT signature,
       count(*) AS parent_scans,
       count(*) FILTER (WHERE symbol_count > 0 AND readiness_rows = 0) AS missing_all_readiness,
       count(*) FILTER (WHERE readiness_rows = symbol_count) AS readiness_counts_match,
       min(collected_at_utc) AS first_collected_utc,
       max(collected_at_utc) AS last_collected_utc
FROM readiness
GROUP BY signature
ORDER BY signature;
