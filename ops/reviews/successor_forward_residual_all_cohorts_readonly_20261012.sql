-- SELECT-ONLY forensic predecessor to a prospective, independently committed
-- position-inventory source receipt. NEVER backfills or certifies an old cycle.
-- Uses every paper entry/exit fill across ALL cohorts (not protection_open).
-- This is a retrospective view of currently available rows; not an immutable
-- consistent AS-OF source snapshot from the historical scan time.
WITH latest AS (
 SELECT run_id,collected_at_utc FROM public.alpha_hunter_snapshots
 WHERE payload->'validation_identity'->>'run_source'='RENDER_CRON'
 AND payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
 ORDER BY collected_at_utc DESC LIMIT 1
), entry_f AS (
 SELECT f.order_id,sum(f.quantity) entered,
 count(*) FILTER (WHERE nullif(f.source_run_id,'') IS NULL) missing_source_run_ids
 FROM public.alpha_hunter_paper_fills_v02 f CROSS JOIN latest l
 WHERE f.filled_at_utc<=l.collected_at_utc
  AND f.created_at<=l.collected_at_utc
 GROUP BY f.order_id
), exit_f AS (
 SELECT f.entry_order_id,sum(f.quantity) exited
 FROM public.alpha_hunter_paper_exit_fills_v04 f CROSS JOIN latest l
 WHERE f.filled_at_utc<=l.collected_at_utc
  AND f.created_at<=l.collected_at_utc
 GROUP BY f.entry_order_id
), residual AS (
 SELECT o.order_id,o.symbol,o.direction,ef.entered-coalesce(x.exited,0) remaining,
 ef.missing_source_run_ids,
 CASE WHEN EXISTS(
  SELECT 1 FROM public.alpha_hunter_paper_protection_open_v04 op
  WHERE op.entry_order_id=o.order_id
 ) THEN 'CURRENT_MANAGED_VIEW' ELSE 'NOT_CURRENT_MANAGED_VIEW' END management
 FROM public.alpha_hunter_paper_orders_v02 o
 JOIN entry_f ef ON ef.order_id=o.order_id
 LEFT JOIN exit_f x ON x.entry_order_id=o.order_id
 CROSS JOIN latest l
 WHERE o.created_at<=l.collected_at_utc
   AND ef.entered-coalesce(x.exited,0)>0.000000000001
)
SELECT (SELECT run_id FROM latest) scanned_run,
 (SELECT collected_at_utc FROM latest) scan_utc,
 count(*) total_residual_orders,
 count(*) FILTER (WHERE management='CURRENT_MANAGED_VIEW') managed,
 count(*) FILTER (WHERE management='NOT_CURRENT_MANAGED_VIEW') outside_managed_view,
 count(*) FILTER (WHERE symbol='NMRUSDT') nmr_residual_count,
 max(remaining) FILTER(WHERE symbol='NMRUSDT') nmr_residual_quantity,
 count(*) FILTER (WHERE missing_source_run_ids>0) entries_with_missing_source_run,
 'RETROSPECTIVE_READONLY_NOT_PROSPECTIVE_SOURCE_ATTESTATION'::text evidence_type
FROM residual;
