-- Alpha Hunter P0: retrospective per-position 24h monitoring-boundary check.
-- READ ONLY / RESEARCH. Does not create alerts, certificates, scientific PASS,
-- database writes, real trade authority, test modifications or live monitoring.
-- Existing modeled-paper receipts have SELF-LABELED quotes (not authenticated).
-- In particular, the current 'now' edge and start-of-window edge cannot be
-- waived merely because the intervals BETWEEN persisted rows looked healthy.
WITH clock AS (
  SELECT now() AS asof_utc, now()-interval '24 hours' AS window_start_utc
), managed AS (
  SELECT entry_order_id,symbol,direction,
         row_number() OVER(PARTITION BY symbol,direction ORDER BY entry_order_id) AS position_slot
  FROM public.alpha_hunter_paper_protection_horizon_open_v09
), valid_run_attempts AS (
  SELECT a.entry_order_id,a.source_run_id,a.observed_at_utc,
         a.outcome,a.blockers,a.evidence,
         a.best_bid,a.best_ask,a.best_bid_size,a.best_ask_size,
         a.paper_only,a.trade_permission,a.exchange_authority,a.order_path,
         count(*) OVER (PARTITION BY a.entry_order_id,a.source_run_id) AS same_run_receipts
  FROM public.alpha_hunter_paper_exit_attempts_v04 a
  JOIN public.alpha_hunter_snapshots s ON s.run_id=a.source_run_id
  CROSS JOIN clock c
  WHERE s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
    AND s.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
    AND a.observed_at_utc <= c.asof_utc
    AND a.observed_at_utc >= c.window_start_utc - interval '35 minutes'
    AND s.collected_at_utc <= a.observed_at_utc
), recent AS (
  SELECT a.*,
    lag(a.observed_at_utc) OVER (
      PARTITION BY a.entry_order_id ORDER BY a.observed_at_utc,a.source_run_id
    ) AS previous_record_utc
  FROM valid_run_attempts a
), grouped AS (
  SELECT m.symbol,m.direction,m.position_slot,m.entry_order_id,
         count(r.observed_at_utc) FILTER (WHERE r.observed_at_utc>=c.window_start_utc) AS receipts_24h,
         count(r.observed_at_utc) FILTER (WHERE r.observed_at_utc>=c.window_start_utc AND
           ((r.outcome IS NULL OR r.outcome NOT IN ('NO_TRIGGER','STOP_TRIGGERED','TARGET_TRIGGERED','HORIZON_CLOSED'))
            OR r.blockers IS DISTINCT FROM '[]'::jsonb
            OR r.paper_only IS DISTINCT FROM true
            OR r.trade_permission IS DISTINCT FROM false
            OR r.exchange_authority IS DISTINCT FROM false
            OR r.order_path IS DISTINCT FROM 'NONE'
            OR r.best_bid IS NULL OR r.best_bid<=0
            OR r.best_ask IS NULL OR r.best_ask<r.best_bid
            OR r.best_bid_size IS NULL OR r.best_bid_size<=0
            OR r.best_ask_size IS NULL OR r.best_ask_size<=0
            OR NULLIF(r.evidence->>'quote_source','') IS NULL
            OR r.same_run_receipts IS DISTINCT FROM 1)) AS structurally_invalid_receipts,
         count(r.observed_at_utc) FILTER(WHERE r.observed_at_utc>=c.window_start_utc AND
           (NULLIF(r.evidence->>'raw_response_sha256','') IS NULL
            OR NULLIF(r.evidence->>'request_id','') IS NULL
            OR NULLIF(r.evidence->>'quote_receipt_digest','') IS NULL)) AS missing_independent_quote_receipt_link,
         count(r.observed_at_utc) FILTER(WHERE r.observed_at_utc>=c.window_start_utc
            AND r.previous_record_utc IS NULL) AS absent_prior_anchor_rows,
         count(r.observed_at_utc) FILTER(WHERE r.observed_at_utc>=c.window_start_utc
            AND r.previous_record_utc IS NOT NULL
            AND EXTRACT(EPOCH FROM r.observed_at_utc-r.previous_record_utc)>2100
         ) AS observed_gaps_over_35m,
         round(max(EXTRACT(EPOCH FROM r.observed_at_utc-r.previous_record_utc))
           FILTER(WHERE r.observed_at_utc>=c.window_start_utc)::numeric,1) AS longest_observed_gap_seconds,
         min(r.observed_at_utc) FILTER(WHERE r.observed_at_utc>=c.window_start_utc) AS first_24h_receipt,
         max(r.observed_at_utc) FILTER(WHERE r.observed_at_utc>=c.window_start_utc) AS latest_24h_receipt
  FROM managed m CROSS JOIN clock c
  LEFT JOIN recent r ON r.entry_order_id=m.entry_order_id
  GROUP BY m.entry_order_id,m.symbol,m.direction,m.position_slot
)
SELECT c.asof_utc,g.symbol,g.direction,g.position_slot,
       g.receipts_24h,g.structurally_invalid_receipts,g.missing_independent_quote_receipt_link,
       g.absent_prior_anchor_rows,g.observed_gaps_over_35m,
       g.longest_observed_gap_seconds,g.first_24h_receipt,g.latest_24h_receipt,
       round(EXTRACT(EPOCH FROM c.asof_utc-g.latest_24h_receipt)::numeric,1) AS current_observation_age_seconds,
       CASE
         WHEN g.receipts_24h=0 THEN 'FAIL_CLOSED_NO_POSITION_OBSERVATIONS_24H'
         WHEN g.absent_prior_anchor_rows>0 THEN 'FAIL_CLOSED_PRIOR_OBSERVATION_UNKNOWN'
         WHEN g.observed_gaps_over_35m>0 THEN 'FAIL_CLOSED_HISTORIC_35M_GAP'
         WHEN g.latest_24h_receipt < c.asof_utc-interval '35 minutes'
           THEN 'FAIL_CLOSED_CURRENT_POSITION_STALE'
         WHEN g.structurally_invalid_receipts>0 THEN 'FAIL_CLOSED_UNUSABLE_PAPER_RECEIPT'
         WHEN g.missing_independent_quote_receipt_link>0
           THEN 'FAIL_CLOSED_INDEPENDENT_QUOTE_CUSTODY_MISSING'
         ELSE 'SOURCE_ONLY_STRUCTURAL_CONTINUITY_NOT_INDEPENDENT_PROOF'
       END AS operational_evidence_verdict,
       false AS independent_quote_source_authenticated,
       false AS independently_custodied_asof_inventory_proven,
       false AS live_critical_alert_delivery_verified,
       false AS scientific_test_promotion_authorized,
       2100 AS frozen_observation_max_gap_seconds
FROM grouped g CROSS JOIN clock c
ORDER BY g.symbol,g.direction,g.position_slot;