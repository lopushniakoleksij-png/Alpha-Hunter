-- Read-only retrospective failure diagnosis of the preregistered 2026-10-08/09 pilot.
-- This was authored AFTER maturity: never treat it as a new holdout.
-- No threshold selection, backfill, trading authority, deployment or test restart.
WITH scope AS (
 SELECT timestamptz '2026-10-08 12:00:00+00' starts_at_utc,
        timestamptz '2026-10-09 12:00:00+00' ends_at_utc,
        '50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834'::text frozen_fingerprint
),
canonical AS (
 SELECT s.run_id,s.collected_at_utc FROM public.alpha_hunter_snapshots s CROSS JOIN scope t
 WHERE s.collected_at_utc >= t.starts_at_utc AND s.collected_at_utc < t.ends_at_utc
 AND s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
 AND s.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
 AND s.payload->'validation_identity'->>'scientific_fingerprint_sha256'=t.frozen_fingerprint
),
raw_attempts AS (
 SELECT a.symbol,a.direction,a.source_run_id,a.observed_at_utc,a.entry_order_id,
 CASE WHEN a.direction='LONG' THEN a.best_bid_size ELSE a.best_ask_size END exit_top_size,
 CASE WHEN a.best_bid>0 AND a.best_ask>=a.best_bid
           AND a.best_bid_size>0 AND a.best_ask_size>0 THEN 1 ELSE 0 END valid_book,
 COALESCE(NULLIF(BTRIM(a.evidence->>'quote_source'),''),'SOURCE_NOT_LABELED_IN_ATTEMPT') quote_source,
 a.best_bid,a.best_ask,a.best_bid_size,a.best_ask_size
 FROM public.alpha_hunter_paper_exit_attempts_v04 a
 JOIN canonical c ON c.run_id=a.source_run_id CROSS JOIN scope t
 WHERE a.direction IN ('LONG','SHORT')
 AND a.observed_at_utc>=t.starts_at_utc AND a.observed_at_utc<t.ends_at_utc
 AND a.exchange_authority IS FALSE AND a.trade_permission IS FALSE
),
run_rollup AS (
 SELECT symbol,direction,source_run_id,COUNT(*) order_attempts,
 COUNT(DISTINCT (best_bid,best_ask,best_bid_size,best_ask_size)) distinct_books,
 COUNT(*) FILTER(WHERE valid_book=0) invalid_books,
 COUNT(*) FILTER(WHERE quote_source='SOURCE_NOT_LABELED_IN_ATTEMPT') unlabelled_attempts,
 COUNT(DISTINCT quote_source) distinct_source_labels,
 MIN(observed_at_utc) observed_at_utc,
 MIN(exit_top_size) exit_top_size
 FROM raw_attempts GROUP BY symbol,direction,source_run_id
),
numbered AS (
 SELECT r.*,ROW_NUMBER() OVER(PARTITION BY symbol,direction ORDER BY observed_at_utc,source_run_id) n,
 LAG(observed_at_utc) OVER(PARTITION BY symbol,direction ORDER BY observed_at_utc,source_run_id) previous_at_utc
 FROM run_rollup r
),
per_series AS (
 SELECT symbol,direction,COUNT(*) observed_scans,SUM(order_attempts) raw_attempts,
 COUNT(*) FILTER(WHERE order_attempts>1) duplicate_order_scan_groups,
 MIN(observed_at_utc) first_at_utc,MAX(observed_at_utc) last_at_utc,
 MAX(observed_at_utc-previous_at_utc) worst_observed_gap,
 MAX(exit_top_size) FILTER(WHERE n=1) first_exit_size,
 MIN(exit_top_size) FILTER(WHERE n>1) future_min_exit_size,
 SUM(invalid_books) invalid_attempt_books,
 COUNT(*) FILTER(WHERE distinct_books>1) conflicting_book_scans,
 COUNT(*) FILTER(WHERE distinct_source_labels>1) mixed_source_scans,
 COUNT(*) FILTER(WHERE unlabelled_attempts>0) unlabelled_scans
 FROM numbered GROUP BY symbol,direction
),
classified AS (
 SELECT s.*,s.observed_scans>=2 enough_samples,
 s.first_at_utc<=t.starts_at_utc+interval '35 minutes' timely_start,
 s.last_at_utc>=t.ends_at_utc-interval '35 minutes' timely_finish,
 COALESCE(s.worst_observed_gap<=interval '35 minutes',FALSE) gap_within_35m,
 s.invalid_attempt_books=0 AND s.conflicting_book_scans=0
 AND s.mixed_source_scans=0 consistent_book_and_source,
 s.unlabelled_scans=0 fully_labelled_source
 FROM per_series s CROSS JOIN scope t
)
SELECT symbol,direction,observed_scans,raw_attempts,duplicate_order_scan_groups,
 first_at_utc,last_at_utc,worst_observed_gap,
 unlabelled_scans,invalid_attempt_books,conflicting_book_scans,mixed_source_scans,
 (enough_samples AND timely_start AND timely_finish AND gap_within_35m) original_time_complete,
 (enough_samples AND timely_start AND timely_finish AND gap_within_35m
 AND consistent_book_and_source AND fully_labelled_source
 AND clock_timestamp()>=(SELECT ends_at_utc FROM scope)) strict_quality_complete,
 ARRAY_REMOVE(ARRAY[
 CASE WHEN NOT enough_samples THEN 'LESS_THAN_TWO_SCANS' END,
 CASE WHEN NOT timely_start THEN 'START_BOUNDARY_MISSING' END,
 CASE WHEN NOT timely_finish THEN 'END_BOUNDARY_MISSING' END,
 CASE WHEN NOT gap_within_35m THEN 'GAP_OVER_35_MINUTES' END,
 CASE WHEN NOT consistent_book_and_source THEN 'QUOTE_CONFLICT_OR_INVALID' END,
 CASE WHEN NOT fully_labelled_source THEN 'QUOTE_SOURCE_UNLABELLED' END,
 CASE WHEN clock_timestamp()<(SELECT ends_at_utc FROM scope) THEN 'PILOT_NOT_MATURE' END
 ]::text[],NULL) blockers
FROM classified ORDER BY symbol,direction;
