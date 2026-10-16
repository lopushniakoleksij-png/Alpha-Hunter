-- P3 exact decision -> venue-fill attribution read-only forensic audit.
-- SELECT-only, no account credentials/side effects/backfill/automatic binding.
-- A unique time+symbol+side candidate is NOT independently confirmed execution.
-- P2 live monitoring and P3 actual cost-model activation remain BLOCKED.
WITH frozen AS (
  SELECT count(*) AS n,
         count(*) FILTER (WHERE shadow_only AND NOT trade_permission) AS shadow_disabled,
         count(*) FILTER (
           WHERE evidence->>'automatic_fill_binding_permitted' = 'false'
             AND evidence->>'explicit_exact_fill_binding_required' = 'true'
         ) AS explicit_only
  FROM public.alpha_hunter_execution_decision_freezes_v01
),
real_fills AS (
  SELECT count(*) AS n,
         count(DISTINCT trade_id) AS unique_trade_ids,
         count(DISTINCT order_id) AS unique_order_ids,
         count(*) FILTER (WHERE NULLIF(trade_id,'') IS NULL
                            OR NULLIF(order_id,'') IS NULL) AS missing_venue_identity
  FROM public.alpha_hunter_fill_evidence
),
order_details AS (
  SELECT count(*) AS n,
         count(*) FILTER (WHERE client_oid_present) AS client_oid_present,
         count(*) FILTER (WHERE order_identity_sha256 IS NOT NULL) AS order_hash_present,
         count(*) FILTER (WHERE origin_consistent) AS origin_consistent,
         count(*) FILTER (WHERE alpha_hunter_execution_claim_permitted) AS order_claim_allowed
  FROM public.alpha_hunter_execution_order_evidence_v01
),
candidate AS (
  SELECT count(*) AS n,
         count(DISTINCT c.execution_event_id) AS candidate_frozen_events,
         count(DISTINCT c.fill_evidence_id) AS candidate_fills,
         count(*) FILTER (WHERE c.candidate_status = 'UNIQUE_EVIDENCE_COMPLETE_MATCH') AS unique_pairs,
         count(*) FILTER (WHERE c.candidate_status = 'AMBIGUOUS_EVIDENCE_COMPLETE_MATCH') AS ambiguous_pairs,
         count(*) FILTER (
           WHERE c.candidate_status = 'UNIQUE_EVIDENCE_COMPLETE_MATCH'
             AND c.action = 'PLACE_LIMIT'
             AND c.order_type = 'MARKET'
         ) AS unique_limit_signal_market_order_conflicts,
         count(*) FILTER (WHERE c.attribution_claim_permitted) AS attributable_candidates,
         count(*) FILTER (WHERE c.automatic_binding_permitted) AS auto_bind_allowed
  FROM public.alpha_hunter_execution_fill_confirmation_candidates_v01 c
),
bindings AS (
  SELECT count(*) AS n,
         count(*) FILTER (WHERE explicit_user_confirmation) AS confirmed
  FROM public.alpha_hunter_execution_fill_bindings_v01
),
verified AS (
  SELECT count(*) AS n,
         count(*) FILTER (WHERE verified_alpha_hunter_execution) AS verified
  FROM public.alpha_hunter_verified_execution_attribution_v01
)
SELECT now() AS read_at_utc,
       frozen.n AS frozen_decisions,
       frozen.shadow_disabled AS shadow_only_decisions,
       frozen.explicit_only AS exact_binding_required_decisions,
       real_fills.n AS historical_venue_fills,
       real_fills.unique_trade_ids AS unique_venue_trade_ids,
       real_fills.unique_order_ids AS unique_venue_order_ids,
       real_fills.missing_venue_identity AS missing_venue_fill_ids,
       order_details.n AS venue_order_detail_rows,
       order_details.client_oid_present AS order_client_oid_present,
       order_details.order_hash_present AS order_identity_hash_present,
       order_details.origin_consistent AS source_order_origin_consistent,
       order_details.order_claim_allowed AS order_details_with_alpha_hunter_claim,
       candidate.n AS heuristic_candidate_pairs,
       candidate.candidate_frozen_events,
       candidate.candidate_fills,
       candidate.unique_pairs AS unique_heuristic_pairs_NOT_verified,
       candidate.ambiguous_pairs,
       candidate.unique_limit_signal_market_order_conflicts,
       candidate.attributable_candidates,
       candidate.auto_bind_allowed,
       bindings.n AS explicit_bindings,
       bindings.confirmed AS explicit_user_confirmed_bindings,
       verified.n AS verified_attribution_view_rows,
       verified.verified AS verified_alpha_hunter_executions,
       CASE WHEN bindings.confirmed > 0 AND verified.verified > 0
         THEN 'EXPLICIT_BINDINGS_EXIST_REQUIRE_INDEPENDENT_ROW_AUDIT'
         ELSE 'NO_VERIFIED_EXACT_DECISION_TO_VENUE_FILL_ATTRIBUTION'
       END AS forensic_verdict,
       false AS model_validation_or_trading_permission_from_this_audit
FROM frozen CROSS JOIN real_fills CROSS JOIN order_details
CROSS JOIN candidate CROSS JOIN bindings CROSS JOIN verified;
