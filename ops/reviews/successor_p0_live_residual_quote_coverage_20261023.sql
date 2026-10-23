-- Alpha Hunter P0 read-only, forward-looking diagnostic (2026-10-23).
-- SELECT-only. ALL historical paper residuals across cohorts; no test reset,
-- database write, R10 admission, live order, backfill, monitoring change or DDL.
-- This is a retrospective read of currently held rows, NOT an independently
-- authenticated AS-OF live-source snapshot or a completed 35-minute receipt chain.
-- Recorded top-of-book and self-labeled source are NOT custody of raw venue bytes.
WITH latest AS (
 SELECT s.run_id,s.collected_at_utc,s.symbol_count
 FROM public.alpha_hunter_snapshots s
 WHERE s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
   AND s.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
 ORDER BY s.collected_at_utc DESC LIMIT 1
), parents_24h AS (
 SELECT s.run_id,s.collected_at_utc,s.symbol_count
 FROM public.alpha_hunter_snapshots s
 WHERE s.collected_at_utc>=now()-interval '24 hours'
   AND s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
   AND s.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
), child_count AS (
 SELECT c.run_id,count(*) n
 FROM public.alpha_hunter_symbol_snapshots c JOIN parents_24h p ON p.run_id=c.run_id
 GROUP BY c.run_id
), attempt_count AS (
 SELECT a.source_run_id AS run_id,count(*) n
 FROM public.alpha_hunter_paper_exit_attempts_v04 a
 JOIN parents_24h p ON p.run_id=a.source_run_id
 GROUP BY a.source_run_id
), scan_check AS (
 SELECT p.run_id,p.collected_at_utc,p.symbol_count,
        coalesce(c.n,0) AS children,
        coalesce(a.n,0) AS attempts,
        (p.symbol_count>0 AND coalesce(c.n,0)=p.symbol_count) AS child_complete
 FROM parents_24h p LEFT JOIN child_count c USING(run_id)
 LEFT JOIN attempt_count a USING(run_id)
), good_gaps AS (
 SELECT collected_at_utc,
        extract(epoch FROM collected_at_utc-
          lag(collected_at_utc) OVER(ORDER BY collected_at_utc)) AS gap_seconds
 FROM scan_check WHERE child_complete
), entered AS (
 SELECT order_id,sum(quantity) AS qty FROM public.alpha_hunter_paper_fills_v02 GROUP BY order_id
), exited AS (
 SELECT entry_order_id,sum(quantity) AS qty FROM public.alpha_hunter_paper_exit_fills_v04 GROUP BY entry_order_id
), positive_residuals AS (
 SELECT o.order_id,o.symbol,o.direction,e.qty-coalesce(x.qty,0) AS residual_qty,
        EXISTS(SELECT 1 FROM public.alpha_hunter_paper_protection_open_v04 m
               WHERE m.entry_order_id=o.order_id) AS managed,
        EXISTS(SELECT 1 FROM public.alpha_hunter_paper_entry_quarantine_v06 q
               WHERE q.order_id=o.order_id)
        OR EXISTS(SELECT 1 FROM public.alpha_hunter_paper_exit_quarantine_v04 q
                  WHERE q.entry_order_id=o.order_id)
        OR EXISTS(SELECT 1 FROM public.alpha_hunter_paper_reconciliation_quarantine_v04 q
                  WHERE q.order_id=o.order_id) AS quarantined,
        (SELECT count(*) FROM public.alpha_hunter_paper_protective_orders_v03 p
         WHERE p.entry_order_id=o.order_id AND p.status='ACTIVE_PAPER'
           AND p.reduce_only=true AND p.protection_type='STOP_LOSS') AS stop_legs,
        (SELECT count(*) FROM public.alpha_hunter_paper_protective_orders_v03 p
         WHERE p.entry_order_id=o.order_id AND p.status='ACTIVE_PAPER'
           AND p.reduce_only=true AND p.protection_type='TAKE_PROFIT') AS target_legs
 FROM public.alpha_hunter_paper_orders_v02 o JOIN entered e ON e.order_id=o.order_id
 LEFT JOIN exited x ON x.entry_order_id=o.order_id
 WHERE e.qty-coalesce(x.qty,0)>0
), managed_now AS (
 SELECT m.entry_order_id FROM public.alpha_hunter_paper_protection_horizon_open_v09 m
), latest_attempts AS (
 SELECT a.entry_order_id,a.source_run_id,a.symbol,a.direction,a.observed_at_utc,
        a.outcome,a.blockers,a.evidence,a.best_bid,a.best_ask,a.best_bid_size,a.best_ask_size,
        a.paper_only,a.exchange_authority,a.trade_permission,a.order_path
 FROM public.alpha_hunter_paper_exit_attempts_v04 a JOIN latest l ON a.source_run_id=l.run_id
), quote_verdict AS (
 SELECT count(*) AS attempts,
        count(*) FILTER(WHERE NULLIF(a.evidence->>'quote_source','') IS NOT NULL) AS source_labeled,
        count(*) FILTER(WHERE NULLIF(a.evidence->>'raw_response_sha256','') IS NOT NULL) AS raw_quote_sha,
        count(*) FILTER(WHERE NULLIF(a.evidence->>'request_id','') IS NOT NULL) AS request_ids,
        count(*) FILTER(WHERE NULLIF(a.evidence->>'quote_receipt_digest','') IS NOT NULL) AS receipt_digest_links,
        count(*) FILTER(WHERE a.best_bid>0 AND a.best_ask>=a.best_bid
                        AND a.best_bid_size>0 AND a.best_ask_size>0) AS positive_top_books,
        count(*) FILTER(WHERE a.outcome IN
                        ('NO_TRIGGER','STOP_TRIGGERED','TARGET_TRIGGERED','HORIZON_CLOSED')
                         AND a.blockers='[]'::jsonb AND a.paper_only=true
                         AND a.exchange_authority=false AND a.trade_permission=false
                         AND a.order_path='NONE') AS paper_only_unblocked,
        count(DISTINCT a.entry_order_id) AS distinct_position_attempts
 FROM latest_attempts a
), per_position_24h AS (
 SELECT a.entry_order_id,a.observed_at_utc,
        extract(epoch FROM a.observed_at_utc-
          lag(a.observed_at_utc) OVER (
             PARTITION BY a.entry_order_id ORDER BY a.observed_at_utc)) AS gap_seconds
 FROM public.alpha_hunter_paper_exit_attempts_v04 a
 JOIN parents_24h p ON p.run_id=a.source_run_id
), position_gaps AS (
 SELECT count(*) FILTER(WHERE gap_seconds>2100) AS gap_breaches,
        round(max(gap_seconds)::numeric,1) AS max_observed_gap_seconds
 FROM per_position_24h
)
SELECT now() AS audit_at_utc, l.run_id AS latest_canonical_run_id,
       l.collected_at_utc AS latest_scan_utc,l.symbol_count AS latest_declared_symbols,
       (SELECT count(*) FROM public.alpha_hunter_symbol_snapshots c
        WHERE c.run_id=l.run_id) AS latest_child_rows,
       (SELECT count(*) FROM positive_residuals) AS all_cohort_residual_count,
       (SELECT count(*) FROM positive_residuals WHERE managed) AS managed_from_fill_ledger,
       (SELECT count(*) FROM positive_residuals WHERE NOT managed AND quarantined) AS quarantined_outside_managed,
       (SELECT count(*) FROM positive_residuals WHERE NOT managed AND NOT quarantined) AS unexplained_unmanaged,
       (SELECT count(*) FROM positive_residuals WHERE stop_legs=0 OR target_legs=0) AS missing_recorded_stop_or_target,
       (SELECT jsonb_agg(jsonb_build_object('symbol',symbol,'direction',direction,
           'paper_residual_qty',residual_qty,'stop_rows',stop_legs,'target_rows',target_legs))
        FROM positive_residuals WHERE NOT managed AND NOT quarantined) AS unexplained_case_no_order_ids,
       (SELECT count(*) FROM managed_now) AS current_horizon_managed_positions,
       (SELECT count(*) FROM managed_now m WHERE NOT EXISTS
         (SELECT 1 FROM latest_attempts a WHERE a.entry_order_id=m.entry_order_id)) AS currently_managed_missing_latest_receipt,
       (SELECT count(*) FROM scan_check) AS canonical_parents_24h,
       (SELECT count(*) FROM scan_check WHERE NOT child_complete) AS missing_children_24h,
       (SELECT count(*) FROM scan_check WHERE attempts=0) AS missing_exit_attempts_24h,
       (SELECT count(*) FROM good_gaps WHERE gap_seconds>2100) AS good_scan_gaps_over_35m,
       (SELECT max(gap_seconds) FROM good_gaps) AS maximum_complete_scan_gap_seconds,
       q.*,g.gap_breaches AS position_observation_gaps_over_35m_24h,
       g.max_observed_gap_seconds AS maximum_position_observation_gap_seconds_24h,
       CASE WHEN (SELECT count(*) FROM positive_residuals)=0
         OR (SELECT count(*) FROM positive_residuals WHERE NOT managed AND NOT quarantined)>0
         OR (SELECT count(*) FROM positive_residuals WHERE stop_legs=0 OR target_legs=0)>0
         OR (SELECT count(*) FROM scan_check WHERE NOT child_complete)>0
         OR (SELECT count(*) FROM scan_check WHERE attempts=0)>0
         OR (SELECT count(*) FROM good_gaps WHERE gap_seconds>2100)>0
         OR (SELECT count(*) FROM managed_now m WHERE NOT EXISTS
           (SELECT 1 FROM latest_attempts a WHERE a.entry_order_id=m.entry_order_id))>0
         OR q.receipt_digest_links<>q.attempts OR q.raw_quote_sha<>q.attempts
         OR q.request_ids<>q.attempts OR g.gap_breaches>0
         THEN 'FAIL_CLOSED_UNVERIFIED_LEDGER_OR_MONITORING'
         ELSE 'STRUCTURAL_RECORDS_ONLY_INDEPENDENT_SOURCE_STILL_UNVERIFIED'
       END AS research_verdict,
       false AS independent_quote_bytes_authenticated,
       false AS immutable_asof_position_inventory_proven,
       false AS scientific_profitability_or_admission_authorized,
       2100 AS frozen_max_monitoring_gap_seconds
FROM latest l CROSS JOIN quote_verdict q CROSS JOIN position_gaps g;