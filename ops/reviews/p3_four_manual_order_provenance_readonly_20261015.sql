-- P3 four named historical frozen-decision / venue-order provenance audit.
-- READ ONLY. Never bind/relabel a fill. A single time+symbol+side candidate is
-- NOT proof the manually placed order was made BECAUSE of Alpha Hunter.
-- Values are literal frozen evidence timestamps, not position IDs or user secrets.
WITH requested(symbol,direction,action,frozen_at_utc) AS (
  VALUES
   ('ALGOUSDT'::text,'SHORT'::text,'EXECUTE_NOW'::text,'2026-10-08T09:43:27.104652+00'::timestamptz),
   ('MYXUSDT','LONG','PLACE_LIMIT','2026-10-10T06:23:30.108448+00'::timestamptz),
   ('SAFEUSDT','SHORT','EXECUTE_NOW','2026-10-12T09:43:36.071720+00'::timestamptz),
   ('WLDUSDT','SHORT','PLACE_LIMIT','2026-10-12T11:43:33.982301+00'::timestamptz)
)
SELECT
 now() AS reviewed_at_utc,
 r.symbol,
 r.direction,
 r.action AS frozen_intent,
 r.frozen_at_utc,
 c.order_created_at_utc,
 c.fill_time_utc,
 round(c.freeze_to_order_seconds / 60,3) AS freeze_to_order_minutes,
 c.candidate_status,
 c.fill_candidate_count,
 c.event_candidate_count,
 c.trace_complete,
 c.trace_schema_validated,
 c.origin_consistent,
 o.fill_origin_class,
 o.order_enter_point_source,
 o.order_source,
 o.order_type,
 o.order_state,
 c.trade_scope,
 f.trade_side AS fill_trade_side,
 o.client_oid_present AS opaque_client_oid_was_observed,
 o.raw_client_oid_persisted_here,
 o.raw_order_id_persisted_here,
 (f.evidence->>'order_write_path_present')::boolean AS observed_alpha_hunter_order_write_path,
 (o.evidence->>'private_endpoint_is_get_only')::boolean AS recorded_private_order_detail_get_only,
 d.shadow_only AS frozen_shadow_only,
 d.trade_permission AS freeze_trade_permission,
 d.evidence->>'automatic_decision_freeze' AS freeze_was_automatic,
 d.evidence->>'explicit_exact_fill_binding_required' AS freeze_requires_explicit_binding,
 c.explicit_user_confirmation_required,
 c.automatic_binding_permitted,
 c.attribution_claim_permitted,
 EXISTS (
   SELECT 1 FROM public.alpha_hunter_execution_fill_bindings_v01 b
   WHERE b.execution_event_id=c.execution_event_id
     AND b.fill_evidence_id=c.fill_evidence_id
     AND b.explicit_user_confirmation
 ) AS this_exact_pair_explicitly_confirmed,
 EXISTS (
   SELECT 1 FROM public.alpha_hunter_verified_execution_attribution_v01 v
   WHERE v.execution_event_id=c.execution_event_id
     AND v.fill_evidence_id=c.fill_evidence_id
     AND v.verified_alpha_hunter_execution
 ) AS this_exact_pair_verified_execution,
 CASE
   WHEN c.execution_event_id IS NULL THEN 'NO_HEURISTIC_CANDIDATE'
   WHEN c.candidate_status <> 'UNIQUE_EVIDENCE_COMPLETE_MATCH'
     THEN 'NONUNIQUE_MATCH_NO_ATTRIBUTION'
   WHEN r.action='PLACE_LIMIT' AND c.order_type='MARKET'
     THEN 'LIMIT_INTENT_MARKET_EXECUTION_CONFLICT_NOT_VERIFIED'
   WHEN r.action='EXECUTE_NOW' AND c.order_type='MARKET'
     THEN 'EXECUTE_NOW_AND_MARKET_COMPATIBLE_CAUSALITY_NOT_VERIFIED'
   ELSE 'INTENT_EXECUTION_METHOD_NOT_VERIFIED'
 END AS historical_method_screen,
 false AS authorization_to_bind_or_restate_scientific_outcome
FROM requested r
LEFT JOIN public.alpha_hunter_execution_fill_confirmation_candidates_v01 c
  ON c.symbol=r.symbol AND c.direction=r.direction
  AND c.action=r.action AND c.frozen_at_utc=r.frozen_at_utc
LEFT JOIN public.alpha_hunter_execution_decision_freezes_v01 d
  ON d.execution_event_id=c.execution_event_id
LEFT JOIN public.alpha_hunter_fill_evidence f
  ON f.fill_evidence_id=c.fill_evidence_id
LEFT JOIN public.alpha_hunter_execution_order_evidence_v01 o
  ON o.fill_evidence_id=c.fill_evidence_id
ORDER BY r.frozen_at_utc,c.fill_time_utc;
