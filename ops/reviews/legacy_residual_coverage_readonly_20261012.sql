-- Read-only all-history exposure coverage audit. No cohort/date filter.
-- Never use results to fabricate fills, exits, protection or cohort membership.
WITH fills AS (
 SELECT order_id,sum(quantity) AS filled_quantity FROM public.alpha_hunter_paper_fills_v02 GROUP BY order_id
), exits AS (
 SELECT entry_order_id,sum(quantity) AS exited_quantity FROM public.alpha_hunter_paper_exit_fills_v04 GROUP BY entry_order_id
), protection AS (
 SELECT entry_order_id,count(*) FILTER (WHERE protection_type='STOP_LOSS') AS stop_records,
 count(*) FILTER (WHERE protection_type='TAKE_PROFIT') AS target_records
 FROM public.alpha_hunter_paper_protective_orders_v03 GROUP BY entry_order_id
), inventory AS (
 SELECT o.order_id,o.symbol,o.direction,o.submitted_at_utc,o.quantity AS ordered_quantity,
 f.filled_quantity,coalesce(x.exited_quantity,0) AS exited_quantity,
 f.filled_quantity-coalesce(x.exited_quantity,0) AS residual_quantity,
 l.state AS lifecycle_state,coalesce(p.stop_records,0) AS stop_records,
 coalesce(p.target_records,0) AS target_records,
 eq.reason AS entry_quarantine,q.reason AS exit_quarantine,rq.reason AS reconciliation_quarantine,
 EXISTS(SELECT 1 FROM public.alpha_hunter_paper_protection_open_v04 m WHERE m.entry_order_id=o.order_id) AS in_managed_protection,
 EXISTS(SELECT 1 FROM public.alpha_hunter_paper_reconciliation_inventory_v08 r WHERE r.order_id=o.order_id) AS in_reconciliation_inventory
 FROM public.alpha_hunter_paper_orders_v02 o JOIN fills f USING(order_id)
 LEFT JOIN exits x ON x.entry_order_id=o.order_id
 LEFT JOIN protection p ON p.entry_order_id=o.order_id
 LEFT JOIN public.alpha_hunter_paper_lifecycle_current_v01 l USING(decision_id)
 LEFT JOIN public.alpha_hunter_paper_entry_quarantine_v06 eq USING(order_id)
 LEFT JOIN public.alpha_hunter_paper_exit_quarantine_v04 q ON q.entry_order_id=o.order_id
 LEFT JOIN public.alpha_hunter_paper_reconciliation_quarantine_v04 rq USING(order_id)
 WHERE f.filled_quantity-coalesce(x.exited_quantity,0)>0.000000000001
)
SELECT *,CASE
 WHEN entry_quarantine IS NOT NULL OR exit_quarantine IS NOT NULL OR reconciliation_quarantine IS NOT NULL THEN 'QUARANTINED_RESIDUAL_PRESERVE_EVIDENCE'
 WHEN stop_records=0 OR target_records=0 THEN 'UNPROTECTED_RESIDUAL_REVIEW_REQUIRED'
 WHEN NOT in_managed_protection THEN 'PROTECTION_COVERAGE_GAP_REVIEW_REQUIRED'
 ELSE 'MANAGED_PROTECTION_RECORDS_PRESENT'
 END AS audit_status
FROM inventory ORDER BY audit_status,symbol,order_id;
