-- P0 successor paper-position safety + canonical persistence diagnostic.
-- RESEARCH/DRAFT ONLY. One SELECT; never create/alter rows, policies, roles,
-- alerts, orders, R10 status, monitoring limits, or historical fill bindings.
-- Critical distinction: modeled paper residuals and completed parent-child
-- SCAN intervals are not independently authenticated per-position monitoring.
WITH entry_totals AS (
 SELECT order_id,sum(quantity) AS entered_qty,min(filled_at_utc) AS first_fill_at_utc
 FROM public.alpha_hunter_paper_fills_v02 GROUP BY order_id
), exit_totals AS (
 SELECT entry_order_id,sum(quantity) AS exited_qty
 FROM public.alpha_hunter_paper_exit_fills_v04 GROUP BY entry_order_id
), all_order_residuals AS (
 SELECT o.symbol,o.direction,o.submitted_at_utc,o.paper_only,
        e.first_fill_at_utc,
        o.quantity AS order_qty,
        coalesce(e.entered_qty,0::numeric) AS entry_qty,
        coalesce(x.exited_qty,0::numeric) AS exit_qty,
        coalesce(e.entered_qty,0::numeric)-coalesce(x.exited_qty,0::numeric) AS residual_qty,
        (m.entry_order_id IS NOT NULL) AS managed,
        (m.entry_order_id IS NOT NULL AND m.protection_count>=2
          AND m.stop_protective_order_id IS NOT NULL
          AND m.target_protective_order_id IS NOT NULL) AS two_recorded_legs,
        (eq.order_id IS NOT NULL OR xq.entry_order_id IS NOT NULL
          OR rq.order_id IS NOT NULL) AS quarantined,
        (SELECT count(*) FROM public.alpha_hunter_paper_protective_orders_v03 p
         WHERE p.entry_order_id=o.order_id) AS raw_protection_count,
        (SELECT count(*) FROM public.alpha_hunter_paper_exit_attempts_v04 a
         WHERE a.entry_order_id=o.order_id) AS source_exit_attempt_count
 FROM public.alpha_hunter_paper_orders_v02 o
 LEFT JOIN entry_totals e ON e.order_id=o.order_id
 LEFT JOIN exit_totals x ON x.entry_order_id=o.order_id
 LEFT JOIN public.alpha_hunter_paper_protection_open_v04 m ON m.entry_order_id=o.order_id
 LEFT JOIN public.alpha_hunter_paper_entry_quarantine_v06 eq ON eq.order_id=o.order_id
 LEFT JOIN public.alpha_hunter_paper_exit_quarantine_v04 xq ON xq.entry_order_id=o.order_id
 LEFT JOIN public.alpha_hunter_paper_reconciliation_quarantine_v04 rq ON rq.order_id=o.order_id
), residuals AS (
 SELECT *,CASE
    WHEN managed THEN 'MANAGED_VIEW'
    WHEN quarantined THEN 'QUARANTINED_UNRESOLVED'
    ELSE 'UNEXPLAINED_UNMANAGED'
 END AS incident_disposition
 FROM all_order_residuals WHERE residual_qty>0
), parent AS (
 SELECT run_id,collected_at_utc,symbol_count
 FROM public.alpha_hunter_snapshots
 WHERE collected_at_utc>=now()-interval '24 hours'
   AND payload->'validation_identity'->>'run_source'='RENDER_CRON'
), child AS (
 SELECT s.run_id,count(*) AS child_rows
 FROM public.alpha_hunter_symbol_snapshots s JOIN parent p ON p.run_id=s.run_id
 GROUP BY s.run_id
), attempt AS (
 SELECT a.source_run_id AS run_id,count(*) AS attempts
 FROM public.alpha_hunter_paper_exit_attempts_v04 a
 JOIN parent p ON p.run_id=a.source_run_id GROUP BY a.source_run_id
), cycles AS (
 SELECT p.collected_at_utc,p.symbol_count,
        coalesce(c.child_rows,0) AS child_rows,
        coalesce(a.attempts,0) AS exit_attempt_rows,
        (p.symbol_count>0 AND coalesce(c.child_rows,0)=p.symbol_count) AS child_complete
 FROM parent p LEFT JOIN child c USING(run_id)
 LEFT JOIN attempt a USING(run_id)
), complete_intervals AS (
 SELECT collected_at_utc,
    extract(epoch FROM collected_at_utc-lag(collected_at_utc)
      OVER (ORDER BY collected_at_utc)) AS completed_scan_gap_seconds
 FROM cycles WHERE child_complete
)
SELECT now() AS read_at_utc,
  (SELECT count(*) FROM all_order_residuals) AS all_paper_order_rows,
  (SELECT count(*) FROM all_order_residuals WHERE residual_qty<0) AS negative_residual_orders,
  (SELECT count(*) FROM residuals) AS positive_residual_orders,
  (SELECT count(*) FROM residuals WHERE incident_disposition='MANAGED_VIEW') AS currently_managed,
  (SELECT count(*) FROM residuals WHERE incident_disposition='QUARANTINED_UNRESOLVED') AS quarantined,
  (SELECT count(*) FROM residuals WHERE incident_disposition='UNEXPLAINED_UNMANAGED') AS unexplained_unmanaged,
  (SELECT count(*) FROM residuals WHERE managed AND NOT two_recorded_legs) AS managed_without_two_recorded_legs,
  (SELECT count(*) FROM residuals WHERE NOT paper_only) AS anomalous_paper_only_flag,
  (SELECT jsonb_agg(jsonb_build_object('symbol',symbol,'direction',direction,
                  'order_quantity',order_qty,'entry_quantity',entry_qty,
                  'exit_quantity',exit_qty,'residual_quantity',residual_qty,
                  'first_fill_at_utc',first_fill_at_utc,
                  'source_protective_rows',raw_protection_count,
                  'source_exit_attempt_rows',source_exit_attempt_count)
             ORDER BY submitted_at_utc)
   FROM residuals WHERE incident_disposition='UNEXPLAINED_UNMANAGED') AS unresolved_position_details,
  (SELECT count(*) FROM cycles) AS last_24h_canonical_parents,
  (SELECT count(*) FROM cycles WHERE child_complete) AS last_24h_child_complete,
  (SELECT count(*) FROM cycles WHERE NOT child_complete) AS last_24h_child_incomplete,
  (SELECT count(*) FROM cycles WHERE exit_attempt_rows=0) AS last_24h_without_exit_attempts,
  (SELECT count(*) FROM complete_intervals WHERE completed_scan_gap_seconds>2100)
       AS completed_scan_gaps_over_frozen_35m,
  (SELECT round(max(completed_scan_gap_seconds)::numeric,1) FROM complete_intervals)
       AS max_child_complete_scan_gap_seconds,
  CASE WHEN
   (SELECT count(*) FROM all_order_residuals)=0
   OR (SELECT count(*) FROM cycles)=0
     THEN 'UNKNOWN_SOURCE_OR_PARENT_EMPTY_FAIL_CLOSED'
   WHEN (SELECT count(*) FROM residuals WHERE incident_disposition='UNEXPLAINED_UNMANAGED')>0
   OR (SELECT count(*) FROM residuals WHERE managed AND NOT two_recorded_legs)>0
   OR (SELECT count(*) FROM cycles WHERE NOT child_complete)>0
   OR (SELECT count(*) FROM cycles WHERE exit_attempt_rows=0)>0
   OR (SELECT count(*) FROM complete_intervals WHERE completed_scan_gap_seconds>2100)>0
     THEN 'FAIL_CLOSED_RESIDUAL_OR_SCAN_EVIDENCE_INCOMPLETE'
   ELSE 'SOURCE_COUNTS_STRUCTURALLY_RECONCILED_NOT_LIVE_MONITORING_PROOF'
  END AS structural_diagnostic,
  2100 AS frozen_monitor_maximum_seconds,
  false AS independent_live_source_or_quote_authenticated,
  false AS all_cohort_continuous_monitoring_proven,
  false AS scientific_pass_or_admissions_permitted,
  false AS permission_to_change_r10_or_start_pilot;
