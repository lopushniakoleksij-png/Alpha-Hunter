-- ALPHA HUNTER V1.3 — AUTHORISED READ-ONLY EXISTING-SCANNER SOURCE AUDIT
-- Template date is the first prospective UTC day; substitute ONLY the two
-- frozen UTC-day bounds during the 30-day observation window.
-- No DDL, DML, migrations, cron or duplicate universe scan.
-- Run source must remain the original Alpha Hunter scanner, not this query.
-- The P0 writer is NOT yet certified; missing evidence means UNKNOWN.
-- Do not commit query outputs containing private signal rows to public GitHub.

WITH cohort AS (
 SELECT signal_id,run_id,symbol,detected_at_utc,created_at,
        direction,entry_price,stop_loss,take_profit,trade_permission,
        payload->'execution_setup'->'checks' AS original_checks,
        payload->>'trade_permission_reason' AS original_reason,
        payload->'decision_trace'->>'blocking_gate' AS blocking_gate
 FROM public.alpha_hunter_signals
 WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT')
   AND detected_at_utc >= '2026-11-15T00:00:00Z'
   AND detected_at_utc < '2026-11-16T00:00:00Z'
), scan_parent AS (
 SELECT DISTINCT run_id FROM public.alpha_hunter_snapshots
), symbol_child AS (
 SELECT DISTINCT run_id,symbol FROM public.alpha_hunter_symbol_snapshots
)
SELECT s.symbol, COUNT(*) AS signal_records,
       COUNT(DISTINCT s.signal_id) AS unique_signal_ids,
       COUNT(DISTINCT s.run_id) AS distinct_run_ids,
       COUNT(*) FILTER(WHERE s.created_at IS NULL) AS missing_created_at,
       COUNT(*) FILTER(WHERE s.created_at < s.detected_at_utc) AS impossible_creation_time,
       COUNT(*) FILTER(WHERE s.direction IN ('LONG','SHORT')) AS directional,
       COUNT(*) FILTER(
          WHERE s.direction IN ('LONG','SHORT')
          AND s.entry_price > 0 AND s.stop_loss > 0 AND s.take_profit > 0
          AND ((s.direction='SHORT' AND s.take_profit<s.entry_price AND s.entry_price<s.stop_loss)
            OR (s.direction='LONG' AND s.stop_loss<s.entry_price AND s.entry_price<s.take_profit))
          AND s.created_at >= s.detected_at_utc
          AND s.created_at <= date_trunc('hour',s.detected_at_utc)+interval '1 hour'
       ) AS asof_complete_geometry,
       COUNT(*) FILTER(WHERE s.trade_permission IS TRUE) AS trade_permission_true,
       COUNT(*) FILTER(WHERE sp.run_id IS NULL) AS missing_parent_references,
       COUNT(*) FILTER(WHERE sc.run_id IS NULL) AS missing_symbol_child_references,
       COUNT(*) FILTER(WHERE s.original_checks IS NULL) AS missing_execution_checks
FROM cohort s
LEFT JOIN scan_parent sp ON sp.run_id=s.run_id
LEFT JOIN symbol_child sc ON sc.run_id=s.run_id AND sc.symbol=s.symbol
GROUP BY s.symbol ORDER BY s.symbol;

-- Detailed frozen-source extraction for the private QA folder:
-- Query returns ONLY the original scanner evidence; no user-defined trades.
-- Filter each UTC day and archive a SHA-256 signal snapshot privately,
-- BEFORE using any completed outcome data for that day.
SELECT signal_id,run_id,symbol,detected_at_utc,created_at,direction,
       entry_price,stop_loss,take_profit,trade_permission,
       payload->'execution_setup'->'checks' AS original_checks,
       payload->>'trade_permission_reason' AS original_reason,
       payload->'decision_trace'->>'blocking_gate' AS blocking_gate
FROM public.alpha_hunter_signals
WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT')
  AND detected_at_utc >= '2026-11-15T00:00:00Z'
  AND detected_at_utc < '2026-11-16T00:00:00Z'
ORDER BY detected_at_utc,signal_id;
