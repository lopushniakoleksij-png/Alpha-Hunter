-- Alpha Hunter P0.1 DBA evidence — READ ONLY in approved role.
-- Unaltered source tables/views; no new policy, trading, orders or migration.
-- Scientific activation rows remain immutable. Do not backfill or "fix".
SELECT cost_scope, snapshot_rows, valid_quote_rows,
       observed_taker_fee_bps, median_spread_bps,
       observable_taker_round_trip_floor_median_bps,
       cost_model_validated, cost_model_activation_permitted,
       realistic_net_r_claim_permitted, trade_permission
FROM public.alpha_hunter_execution_cost_floor_status_v01
ORDER BY cost_scope
LIMIT 10;

-- Fail-closed independent decision: no cost-model promotion is eligible
-- if ANY published scope claims live authority or a validated cost model.
SELECT COUNT(*) AS cost_scopes,
       COUNT(*) FILTER(
         WHERE cost_model_validated IS TRUE
            OR cost_model_activation_permitted IS TRUE
            OR realistic_net_r_claim_permitted IS TRUE
            OR trade_permission IS TRUE
       ) AS unauthorized_cost_promotion_scopes
FROM public.alpha_hunter_execution_cost_floor_status_v01;

-- Versions/hash of the three exact guard routines, no mutation.
SELECT p.proname AS guard_name,
       MD5(pg_get_functiondef(p.oid)) AS current_source_md5
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='private'
  AND p.proname IN(
     'alpha_hunter_guard_r8_profitability_activation_v01',
     'alpha_hunter_guard_r9_activation_v01',
     'alpha_hunter_guard_r10_profitability_activation_v01')
ORDER BY p.proname;
