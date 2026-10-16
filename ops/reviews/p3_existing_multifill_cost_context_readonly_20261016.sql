-- P3 descriptive multi-fill / fee / attribution acceptance audit.
-- SELECT ONLY; no venue order IDs, private fills, source mutation or backfill.
-- These counts are historical venue evidence, NOT verified Alpha Hunter executions.
WITH order_fragments AS (
  SELECT order_id, count(*) AS fill_count,
         count(DISTINCT trade_id) AS distinct_trade_ids,
         count(DISTINCT upper(coalesce(fee_coin,''))) AS fee_currency_count,
         bool_and(cost_fields_complete) AS all_cost_fields_marked_complete
  FROM public.alpha_hunter_fill_evidence
  WHERE order_id IS NOT NULL
  GROUP BY order_id
), fragmentation AS (
  SELECT count(*) AS venue_orders,
         count(*) FILTER (WHERE fill_count>1) AS multi_fill_orders,
         coalesce(max(fill_count),0) AS max_fills_one_order,
         coalesce(sum(fill_count) FILTER (WHERE fill_count>1),0) AS fills_inside_multi_orders,
         count(*) FILTER (WHERE distinct_trade_ids<>fill_count) AS duplicate_trade_id_orders,
         count(*) FILTER (WHERE fee_currency_count>1) AS mixed_fee_currency_orders,
         count(*) FILTER (WHERE not all_cost_fields_marked_complete) AS incomplete_cost_label_orders
  FROM order_fragments
), fee_state AS (
  SELECT count(*) AS venue_fill_rows,
         count(*) FILTER (WHERE fee_coin='USDT') AS usdt_fee_labeled_rows,
         count(*) FILTER (WHERE coalesce(cost_fields_complete,false)) AS basic_cost_fields_complete,
         count(*) FILTER (WHERE fee_coin IS NULL OR fee_amount IS NULL) AS missing_fee_fields
  FROM public.alpha_hunter_fill_evidence
), candidates AS (
  SELECT count(*) AS heuristic_pairs,
         count(*) FILTER (WHERE candidate_status='UNIQUE_EVIDENCE_COMPLETE_MATCH') AS unique_heuristic_pairs_unverified,
         count(*) FILTER (WHERE candidate_status='AMBIGUOUS_EVIDENCE_COMPLETE_MATCH') AS ambiguous_heuristic_pairs,
         count(*) FILTER (WHERE action='PLACE_LIMIT' AND order_type='MARKET') AS limit_signal_market_order_conflicts,
         count(*) FILTER (WHERE attribution_claim_permitted) AS pairs_with_attribution_authority
  FROM public.alpha_hunter_execution_fill_confirmation_candidates_v01
), binding AS (
  SELECT count(*) AS exact_fill_bindings,
         count(*) FILTER (WHERE explicit_user_confirmation) AS owner_confirmed_bindings
  FROM public.alpha_hunter_execution_fill_bindings_v01
), exact AS (
  SELECT count(*) FILTER (WHERE verified_alpha_hunter_execution) AS verified_ah_execution_rows
  FROM public.alpha_hunter_verified_execution_attribution_v01
), cost AS (
  SELECT benchmark_rows, realized_fee_rows,verified_execution_rows,
         verified_exit_slippage_rows,verified_post_fill_markout_rows,
         active_validated_model_rows,realistic_net_r_claim_permitted,
         coarse_benchmark_is_slippage,trade_permission
  FROM public.alpha_hunter_execution_cost_validation_readiness_v04
)
SELECT now() AS read_at_utc, fragmentation.*,fee_state.*,candidates.*,
       binding.*,exact.*,cost.*,
       'DESCRIPTIVE_HISTORICAL_VENUE_ONLY_NOT_EXECUTION_ATTRIBUTION'::text AS evidence_class,
       false AS realistic_cost_validation_permitted_by_this_audit
FROM fragmentation CROSS JOIN fee_state CROSS JOIN candidates
CROSS JOIN binding CROSS JOIN exact CROSS JOIN cost;
