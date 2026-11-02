-- P2 READ-ONLY forensic cause of missing quote_source in modeled exit evidence.
-- This query only evaluates canonical run 403a... at 2026-10-12 14:43:39 UTC.
-- A numeric match is NOT independently authenticated venue provenance or an
-- authorization to update/relabel historical attempt rows.
WITH baseline AS (
 SELECT run_id,collected_at_utc FROM public.alpha_hunter_snapshots
 WHERE run_id='403a00517276c12e65a57b5760a5efb3'
), joined AS (
 SELECT a.entry_order_id,a.symbol,a.source_run_id,
 a.evidence->>'quote_source' quoted_label,
 c.payload->>'exchange_timestamp_ms' exchange_timestamp_ms,
 c.payload->>'collected_at_utc' child_collected_at,
 (a.best_bid=(c.payload->>'bid_price')::numeric
  AND a.best_ask=(c.payload->>'ask_price')::numeric
  AND a.best_bid_size=(c.payload->>'bid_size')::numeric
  AND a.best_ask_size=(c.payload->>'ask_size')::numeric
 ) top_book_exact_match,
 a.observed_at_utc,b.collected_at_utc scan_at
 FROM baseline b
 JOIN public.alpha_hunter_paper_exit_attempts_v04 a ON a.source_run_id=b.run_id
 LEFT JOIN public.alpha_hunter_symbol_snapshots c
   ON c.run_id=a.source_run_id AND c.symbol=a.symbol
)
SELECT clock_timestamp() checked_utc,
 count(*) total_position_attempts,
 count(*) FILTER(WHERE quoted_label IS NULL OR quoted_label='') missing_quote_source_labels,
 count(*) FILTER(WHERE (quoted_label IS NULL OR quoted_label='')
   AND top_book_exact_match IS TRUE) unlabeled_exact_top_book_matches_child,
 count(*) FILTER(WHERE (quoted_label IS NULL OR quoted_label='')
   AND exchange_timestamp_ms IS NOT NULL
   AND exchange_timestamp_ms<>'0') unlabeled_with_exchange_timestamps,
 count(*) FILTER(WHERE quoted_label IS NOT NULL AND quoted_label<>'') labeled_attempts,
 count(*) FILTER(WHERE abs(extract(epoch FROM(observed_at_utc-scan_at)))>30) offset_over_diagnostic_30s,
 max(abs(extract(epoch FROM(observed_at_utc-scan_at)))) maximum_parent_attempt_offset_s,
 'READONLY_CORRELATION_NOT_AUTHENTICATED_QUOTE_CAPTURE' proof_class
FROM joined;
