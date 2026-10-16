-- P3 latest UNIQUE-*within-heuristic-window* historical candidates.
-- SELECT only; never imply executable Alpha Hunter strategy orders.
-- No raw venue order ID/trade ID/client OID, personal identifiers, credentials.
WITH unique_pairs AS (
 SELECT c.*,o.fill_origin_class,o.order_enter_point_source,o.order_source,
        o.read_only_get,o.client_oid_present,
        o.alpha_hunter_execution_claim_permitted,
        d.shadow_only AS frozen_shadow_only,
        d.trade_permission AS frozen_trade_permission,
        coalesce((f.evidence->>'order_write_path_present')::boolean,false)
          AS alpha_hunter_order_writer_present,
        EXISTS (SELECT 1 FROM public.alpha_hunter_execution_fill_bindings_v01 b
          WHERE b.execution_event_id=c.execution_event_id
            AND b.fill_evidence_id=c.fill_evidence_id
            AND b.explicit_user_confirmation) AS explicit_confirmed_pair
 FROM public.alpha_hunter_execution_fill_confirmation_candidates_v01 c
 JOIN public.alpha_hunter_execution_decision_freezes_v01 d
   ON d.execution_event_id=c.execution_event_id
 JOIN public.alpha_hunter_fill_evidence f
   ON f.fill_evidence_id=c.fill_evidence_id
 JOIN public.alpha_hunter_execution_order_evidence_v01 o
   ON o.fill_evidence_id=c.fill_evidence_id
 WHERE c.candidate_status='UNIQUE_EVIDENCE_COMPLETE_MATCH'
)
SELECT now() AS read_at_utc,symbol,direction,action AS frozen_intent,
       frozen_at_utc,order_created_at_utc,fill_time_utc,
       round(freeze_to_order_seconds/60,3) AS freeze_to_order_minutes,
       order_type,trade_scope AS fill_liquidity_role,
       fill_origin_class,order_enter_point_source,order_source,
       read_only_get,client_oid_present,
       frozen_shadow_only,frozen_trade_permission,
       alpha_hunter_order_writer_present,
       explicit_confirmed_pair,
       explicit_user_confirmation_required,automatic_binding_permitted,
       attribution_claim_permitted,
       CASE WHEN action='PLACE_LIMIT' AND order_type='MARKET'
          THEN 'LIMIT_MARKET_METHOD_CONFLICT_UNVERIFIED'
          WHEN action='EXECUTE_NOW' AND order_type='MARKET'
          THEN 'MARKET_METHOD_COMPATIBLE_CAUSALITY_UNVERIFIED'
          ELSE 'UNVERIFIED_METHOD_AND_CAUSALITY'
       END AS finding,
       false AS permission_to_bind_or_restate_r10_execution
FROM unique_pairs ORDER BY frozen_at_utc;
