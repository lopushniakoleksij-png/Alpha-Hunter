-- Reproducible fixed-window EXPLORATORY audit only. Read-only; NOT a preregistered holdout.
-- Window chosen after PR #335 opened; these descriptive numbers MUST NEVER set trading thresholds.
-- Data is best quote sizes for already-filled paper positions, not order-book depth/real fills.
WITH canonical AS (
  SELECT s.run_id FROM public.alpha_hunter_snapshots s
  WHERE s.collected_at_utc >= timestamptz '2026-10-08 03:38:50+00'
    AND s.collected_at_utc < timestamptz '2026-10-08 08:27:38+00'
    AND s.payload->'validation_identity'->>'run_source' = 'RENDER_CRON'
    AND s.payload->'validation_identity'->>'runtime_role' = 'RENDER_CRON'
    AND s.payload->'validation_identity'->>'scientific_fingerprint_sha256'
      = '50068b1333a66c70e5413eacf35dda053a0b97f81d7e9e892c9e9a583619c834'
),
valid AS (
  SELECT DISTINCT ON (a.symbol, a.direction, a.source_run_id)
    a.symbol,a.direction,a.source_run_id,a.observed_at_utc,
    CASE WHEN a.direction = 'LONG' THEN a.best_bid_size ELSE a.best_ask_size END AS exit_top_size
  FROM public.alpha_hunter_paper_exit_attempts_v04 a
  JOIN canonical c ON c.run_id = a.source_run_id
  WHERE a.observed_at_utc >= timestamptz '2026-10-08 03:38:50+00'
    AND a.observed_at_utc < timestamptz '2026-10-08 08:27:38+00'
    AND a.direction IN ('LONG','SHORT')
    AND a.best_bid > 0 AND a.best_ask >= a.best_bid
    AND a.best_bid_size > 0 AND a.best_ask_size > 0
    AND a.exchange_authority = FALSE AND a.trade_permission = FALSE
  ORDER BY a.symbol,a.direction,a.source_run_id,a.observed_at_utc,a.entry_order_id
),
ranked AS (
  SELECT v.*,row_number() OVER (
    PARTITION BY symbol,direction ORDER BY observed_at_utc,source_run_id
  ) AS n FROM valid v
),
per_series AS (
  SELECT r.symbol,r.direction,count(*) AS samples,
    max(r.exit_top_size) FILTER (WHERE n=1) AS first_size,
    min(r.exit_top_size) FILTER (WHERE n>1) AS later_min_size
  FROM ranked r GROUP BY r.symbol,r.direction
)
SELECT (SELECT count(*) FROM canonical) AS canonical_scans,
  count(*) AS independent_symbol_direction_series,
  COALESCE(sum(samples),0) AS deduplicated_quote_samples,
  count(*) FILTER(WHERE later_min_size < first_size) AS shrunk,
  count(*) FILTER(WHERE later_min_size < first_size*0.5) AS below_half,
  count(*) FILTER(WHERE later_min_size < first_size*0.25) AS below_quarter,
  count(*) FILTER(WHERE later_min_size < first_size*0.1) AS below_tenth,
  round(min(later_min_size/nullif(first_size,0))::numeric,4) AS smallest_forward_size_ratio
FROM per_series;
