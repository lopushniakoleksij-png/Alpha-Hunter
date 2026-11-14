-- ALPHA HUNTER PHASE 2 — EXACT 175-ROW SIGNAL SNAPSHOT EXPORT
-- Read-only SELECT: never execute migration/INSERT/UPDATE/DELETE.
-- Cohort UTC Nov 8 inclusive to Nov 9 exclusive; 3 research symbols.
-- Use psql client-side \\copy to save private local CSV, from an
-- authorised READ-ONLY connection. Never put DB credentials in Git or chat.
-- In psql (not Supabase SQL Editor), with private output directory available:
-- \\copy (SELECT signal_id,symbol,detected_at_utc,created_at,state,direction,trade_permission,entry_price,stop_loss,take_profit,reference_price,huge_rr_score,confidence_estimate_pct,reward_risk FROM public.alpha_hunter_signals WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT') AND detected_at_utc >= '2026-11-08T00:00:00Z' AND detected_at_utc < '2026-11-09T00:00:00Z' ORDER BY symbol,detected_at_utc,signal_id) TO '/absolute/private/path/pilot_signals_20261108.csv' WITH (FORMAT CSV, HEADER TRUE)
-- After local export, separately verify 175 rows, unique signal IDs, all blocked, source file SHA-256. Do not publish the CSV.

SELECT signal_id,symbol,detected_at_utc,created_at,state,direction,
       trade_permission,entry_price,stop_loss,take_profit,reference_price,
       huge_rr_score,confidence_estimate_pct,reward_risk
FROM public.alpha_hunter_signals
WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT')
  AND detected_at_utc >= '2026-11-08T00:00:00Z'
  AND detected_at_utc < '2026-11-09T00:00:00Z'
ORDER BY symbol,detected_at_utc,signal_id;
