-- Alpha Hunter Phase 2 Scientific Validation V1.1
-- READ ONLY: exact frozen BTC/ETH/SOL signal cohort for 2026-11-08 UTC.
-- Does not use source credentials, DDL/DML or private evidence export.
-- 'execution_setup.checks' are Boolean execution gates and may overlap.
-- 'decision_trace.blocking_gate' is a separate discovery/stage gate.

WITH cohort AS (
 SELECT symbol,direction,trade_permission,reward_risk,
        payload->>'trade_permission_reason' AS trade_permission_reason,
        payload->'execution_setup'->'checks' AS checks,
        payload->'decision_trace'->>'blocking_gate' AS blocking_gate
 FROM public.alpha_hunter_signals
 WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT')
   AND detected_at_utc >= '2026-11-08T00:00:00Z'
   AND detected_at_utc < '2026-11-09T00:00:00Z'
)
SELECT symbol,COUNT(*) AS records,
       COUNT(*) FILTER(WHERE direction='SHORT') AS directional_short,
       COUNT(*) FILTER(WHERE direction IS NULL) AS no_direction,
       COUNT(*) FILTER(WHERE trade_permission IS TRUE) AS trade_permission_true,
       COUNT(*) FILTER(WHERE direction='SHORT'
         AND checks->>'rr_minimum_met'='false') AS rr_failed,
       COUNT(*) FILTER(WHERE direction='SHORT'
         AND checks->>'participation_confirmed'='false') AS participation_failed,
       COUNT(*) FILTER(WHERE direction='SHORT'
         AND checks->>'momentum_confirmed'='false') AS momentum_failed,
       COUNT(*) FILTER(WHERE direction='SHORT'
         AND checks->>'direction_aligned'='false') AS direction_failed,
       COUNT(*) FILTER(WHERE direction='SHORT'
         AND checks->>'structure_valid'='false') AS structure_failed,
       COUNT(*) FILTER(WHERE direction='SHORT'
         AND checks->>'funding_not_extreme'='false') AS funding_failed,
       COUNT(*) FILTER(WHERE direction='SHORT'
         AND checks->>'data_integrity_min_88'='false') AS integrity_failed,
       COUNT(*) FILTER(WHERE direction='SHORT'
         AND blocking_gate='DISCOVERY_SCORE') AS discovery_score_gate,
       COUNT(*) FILTER(WHERE direction='SHORT'
         AND blocking_gate='DIRECTION_PROOF') AS direction_proof_gate
FROM cohort GROUP BY symbol ORDER BY symbol;

WITH cohort AS (
 SELECT symbol,direction,payload->>'trade_permission_reason' AS reason
 FROM public.alpha_hunter_signals
 WHERE symbol IN ('BTCUSDT','ETHUSDT','SOLUSDT')
   AND detected_at_utc >= '2026-11-08T00:00:00Z'
   AND detected_at_utc < '2026-11-09T00:00:00Z'
)
SELECT direction,reason,COUNT(*) AS records
FROM cohort GROUP BY direction,reason ORDER BY direction,records DESC,reason;
