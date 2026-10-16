-- P3 descriptive frozen-LIMIT vs later MARKET-fill PRICE COMPARISON.
-- NON-CAUSAL counterfactual arithmetic, NOT execution slippage, loss, R, or
-- profitability. A resting frozen LIMIT might never fill. 9–21m stale.
-- One SQL SELECT, no trade/order/client IDs, private data, writes or binding.
SELECT now() AS read_at_utc,symbol,direction,
       frozen_at_utc,order_created_at_utc,
       round(freeze_to_order_seconds/60,3) AS minutes_frozen_to_order,
       planned_entry_price AS earlier_frozen_limit_price,
       price::numeric AS later_market_fill_price,
       round(
         (CASE WHEN direction='LONG' THEN price::numeric-planned_entry_price
               WHEN direction='SHORT' THEN planned_entry_price-price::numeric
               ELSE NULL END)
         / NULLIF(planned_entry_price,0) * 10000,2
       ) AS directional_price_difference_bps_NOT_execution_slippage,
       action AS frozen_action,order_type AS venue_order_type,
       candidate_status,automatic_binding_permitted,
       attribution_claim_permitted,
       false AS alpha_hunter_verified_trade_or_cost_evidence,
       false AS limit_fill_counterfactual_proven
FROM public.alpha_hunter_execution_fill_confirmation_candidates_v01
WHERE candidate_status='UNIQUE_EVIDENCE_COMPLETE_MATCH'
  AND action='PLACE_LIMIT'
  AND order_type='MARKET'
ORDER BY frozen_at_utc;
