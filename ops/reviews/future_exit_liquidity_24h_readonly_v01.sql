-- FUTURE successor liquidity telemetry, read-only. NEVER merge/deploy in frozen R10.
-- Captures only forward quotes from an independently fixed future window;
-- does not compute profitability, trigger an order, modify historical evidence,
-- or choose a trading threshold.
-- Pilot: 2026-10-08 12:00Z to 2026-10-09 12:00Z, 24h.
-- Correct grain: symbol + direction + canonical run, NOT entry order id.
WITH scope AS (
  SELECT
    timestamptz '2026-10-08 12:00:00+00' AS starts_at_utc,
    timestamptz '2026-10-09 12:00:00+00' AS ends_at_utc,
    '50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834'::text AS frozen_fingerprint
),
canonical AS (
  SELECT s.run_id, s.collected_at_utc
  FROM public.alpha_hunter_snapshots s
  CROSS JOIN scope t
  WHERE s.collected_at_utc >= t.starts_at_utc
    AND s.collected_at_utc < t.ends_at_utc
    AND s.payload->'validation_identity'->>'run_source' = 'RENDER_CRON'
    AND s.payload->'validation_identity'->>'runtime_role' = 'RENDER_CRON'
    AND s.payload->'validation_identity'->>'scientific_fingerprint_sha256' = t.frozen_fingerprint
),
unique_quotes AS (
  SELECT DISTINCT ON (a.symbol, a.direction, a.source_run_id)
    a.symbol, a.direction, a.source_run_id, a.observed_at_utc,
    CASE WHEN a.direction='LONG' THEN a.best_bid_size ELSE a.best_ask_size END AS exit_top_size,
    CASE WHEN a.direction='LONG' THEN a.best_ask_size ELSE a.best_bid_size END AS entry_top_size,
    COALESCE(a.evidence->>'quote_source','SOURCE_NOT_LABELED_IN_ATTEMPT') AS quote_source
  FROM public.alpha_hunter_paper_exit_attempts_v04 a
  JOIN canonical c ON c.run_id = a.source_run_id
  WHERE a.direction IN ('LONG','SHORT')
    AND a.best_bid > 0 AND a.best_ask >= a.best_bid
    AND a.best_bid_size > 0 AND a.best_ask_size > 0
    AND a.observed_at_utc >= (SELECT starts_at_utc FROM scope)
    AND a.observed_at_utc < (SELECT ends_at_utc FROM scope)
    AND a.exchange_authority IS FALSE AND a.trade_permission IS FALSE
  ORDER BY a.symbol, a.direction, a.source_run_id, a.observed_at_utc, a.entry_order_id
),
numbered AS (
  SELECT q.*,
    row_number() OVER (PARTITION BY q.symbol, q.direction ORDER BY q.observed_at_utc, q.source_run_id) AS observation_number,
    lag(q.observed_at_utc) OVER (PARTITION BY q.symbol, q.direction ORDER BY q.observed_at_utc, q.source_run_id) AS previous_at_utc
  FROM unique_quotes q
),
per_series AS (
  SELECT symbol, direction,
    count(*) AS observed_scans,
    min(observed_at_utc) AS first_at_utc,
    max(observed_at_utc) AS last_at_utc,
    max(exit_top_size) FILTER (WHERE observation_number=1) AS initial_exit_top_size,
    min(exit_top_size) FILTER (WHERE observation_number>1) AS minimum_future_exit_top_size,
    max(observed_at_utc - previous_at_utc) AS worst_observed_gap,
    count(*) FILTER (WHERE quote_source='SOURCE_NOT_LABELED_IN_ATTEMPT') AS unlabelled_source_samples
  FROM numbered GROUP BY symbol, direction
),
classified AS (
  SELECT s.*,
    (s.observed_scans >= 2
      AND s.first_at_utc <= t.starts_at_utc + interval '35 minutes'
      AND s.last_at_utc >= t.ends_at_utc - interval '35 minutes'
      AND s.worst_observed_gap <= interval '35 minutes') AS complete_24h_window
  FROM per_series s CROSS JOIN scope t
)
SELECT CASE WHEN clock_timestamp() < (SELECT starts_at_utc FROM scope)
            THEN 'NOT_STARTED'
            WHEN clock_timestamp() < (SELECT ends_at_utc FROM scope)
            THEN 'IMMATURE_DO_NOT_SCORE'
            ELSE 'MATURE_DATA_CHECK_ONLY_NOT_TRADE_AUTHORITY' END AS pilot_status,
  (SELECT count(*) FROM canonical) AS canonical_runs,
  count(*) AS symbol_direction_series,
  COALESCE(sum(observed_scans),0) AS deduplicated_quote_samples,
  count(*) FILTER (WHERE complete_24h_window) AS complete_24h_series,
  count(*) FILTER (WHERE NOT complete_24h_window) AS censored_or_incomplete_series,
  count(*) FILTER (WHERE complete_24h_window AND minimum_future_exit_top_size < initial_exit_top_size) AS complete_series_with_exit_depth_shrink,
  count(*) FILTER (WHERE complete_24h_window AND minimum_future_exit_top_size < initial_exit_top_size * 0.25) AS complete_series_below_quarter_initial_exit_depth,
  COALESCE(sum(unlabelled_source_samples),0) AS unlabelled_quote_source_samples
FROM classified;
