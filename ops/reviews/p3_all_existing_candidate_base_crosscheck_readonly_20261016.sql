-- P3 cross-examine *underlying source tables* for every historical heuristic candidate.
-- READ ONLY. No source ID, venue order/trade ID, private account identifiers,
-- credentials or raw client OID in output. No binding, scientific attribution,
-- backfill or runtime action. View supplies candidate PAIRING ONLY; original
-- freeze/fill/private GET/trace/binding sources independently re-read here.
WITH original AS (
 SELECT c.execution_event_id,c.fill_evidence_id,c.order_id,c.candidate_status,
        c.action,c.order_type,
        (d.execution_event_id IS NOT NULL
         AND d.symbol=c.symbol AND d.direction=c.direction
         AND d.action=c.action AND d.frozen_at_utc=c.frozen_at_utc)
           AS frozen_identity_match,
        (f.fill_evidence_id IS NOT NULL AND f.trade_id=c.trade_id
         AND f.order_id=c.order_id AND f.symbol=c.symbol
         AND f.trade_side='OPEN') AS venue_fill_identity_match,
        (o.order_evidence_id IS NOT NULL AND o.fill_evidence_id=f.fill_evidence_id
         AND o.order_type=c.order_type AND o.origin_consistent
         AND o.read_only_get AND NOT o.alpha_hunter_execution_claim_permitted)
           AS venue_order_provenance_consistent,
        (t.traceability_run_id IS NOT NULL AND t.complete
         AND t.schema_validated AND f.source_run_id=t.source_run_id)
           AS trace_source_consistent,
        (d.shadow_only AND NOT d.trade_permission
         AND NOT d.production_promotion_permitted AND d.order_path='NONE')
           AS freeze_non_authorized,
        (NOT coalesce((f.evidence->>'order_write_path_present')::boolean,false))
           AS no_ah_order_writer,
        (NOT c.attribution_claim_permitted AND NOT c.automatic_binding_permitted
         AND c.explicit_user_confirmation_required)
           AS requires_explicit_identity_link,
        (b.binding_id IS NULL) AS no_binding,
        c.fill_candidate_count,c.event_candidate_count
 FROM public.alpha_hunter_execution_fill_confirmation_candidates_v01 c
 LEFT JOIN public.alpha_hunter_execution_decision_freezes_v01 d
   ON d.execution_event_id=c.execution_event_id
 LEFT JOIN public.alpha_hunter_fill_evidence f
   ON f.fill_evidence_id=c.fill_evidence_id
 LEFT JOIN public.alpha_hunter_execution_order_evidence_v01 o
   ON o.fill_evidence_id=c.fill_evidence_id
 LEFT JOIN public.alpha_hunter_fill_traceability_runs t
   ON t.traceability_run_id=f.traceability_run_id
 LEFT JOIN public.alpha_hunter_execution_fill_bindings_v01 b
   ON b.execution_event_id=c.execution_event_id
  AND b.fill_evidence_id=c.fill_evidence_id
)
SELECT now() AS read_at_utc,candidate_status,
       count(*) AS candidate_pairs,
       count(DISTINCT execution_event_id) AS distinct_frozen_events,
       count(DISTINCT fill_evidence_id) AS distinct_venue_fill_rows,
       count(DISTINCT order_id) AS distinct_venue_orders,
       count(*) FILTER(WHERE frozen_identity_match) AS source_freezes_matching,
       count(*) FILTER(WHERE venue_fill_identity_match) AS source_fills_matching,
       count(*) FILTER(WHERE venue_order_provenance_consistent) AS order_get_consistent,
       count(*) FILTER(WHERE trace_source_consistent) AS trace_source_consistent,
       count(*) FILTER(WHERE freeze_non_authorized) AS source_shadow_no_trade_authority,
       count(*) FILTER(WHERE no_ah_order_writer) AS no_ah_order_writer,
       count(*) FILTER(WHERE requires_explicit_identity_link) AS no_auto_binding,
       count(*) FILTER(WHERE no_binding) AS no_exact_binding,
       count(*) FILTER(WHERE action='PLACE_LIMIT' AND order_type='MARKET')
          AS limit_signal_vs_actual_market_pairs,
       count(DISTINCT order_id) FILTER(
         WHERE action='PLACE_LIMIT' AND order_type='MARKET')
          AS distinct_orders_with_limit_market_candidate,
       count(*) FILTER(WHERE fill_candidate_count>1) AS pair_fill_has_multiple_freezes,
       count(*) FILTER(WHERE event_candidate_count>1) AS pair_freeze_has_multiple_fills,
       count(*) FILTER(WHERE fill_candidate_count>1 AND event_candidate_count>1)
          AS many_to_many_candidate_pairs,
       false AS attribution_or_cost_validation_permitted
FROM original
GROUP BY candidate_status ORDER BY candidate_status;
