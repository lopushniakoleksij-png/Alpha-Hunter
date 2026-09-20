-- Alpha Hunter fill-origin attribution guard v0.1
--
-- Purpose:
--   Make fill provenance explicit so external/manual trades cannot be mistaken
--   for Alpha Hunter executions in evidence analysis.
--
-- Attribution boundary:
--   * HUMAN UI sources (iOS/Android/Web/App/Mobile) are external to Alpha Hunter.
--   * API origin is only heuristic-eligible; API origin alone is NOT proof that
--     Alpha Hunter created the order.
--   * Verified Alpha Hunter execution requires a later deterministic identity
--     binding (for example, a system clientOid / TradeIntent identity).
--
-- Safety:
--   Read-only views only. No order path, no permission change, no production
--   execution authority.

create or replace view public.alpha_hunter_fill_origin_attribution_v01
with (security_invoker=true,security_barrier=true)
as
select
  f.fill_evidence_id,
  f.traceability_run_id,
  f.source_run_id,
  f.fill_time_utc,
  f.symbol,
  f.side,
  f.trade_side,
  f.trade_scope,
  f.enter_point_source,
  case
    when upper(coalesce(f.enter_point_source,''))='API'
      then 'API_ORIGIN_UNVERIFIED'
    when upper(coalesce(f.enter_point_source,'')) in (
      'IOS','ANDROID','WEB','APP','MOBILE'
    )
      then 'HUMAN_UI_EXTERNAL'
    when nullif(trim(coalesce(f.enter_point_source,'')),'') is null
      then 'UNKNOWN_ORIGIN'
    else 'NON_API_EXTERNAL'
  end as origin_class,
  (
    upper(coalesce(f.enter_point_source,''))='API'
  ) as heuristic_signal_attribution_eligible,
  false as verified_alpha_hunter_execution,
  false as alpha_hunter_execution_claim_permitted,
  'DETERMINISTIC_SYSTEM_ORDER_IDENTITY_NOT_YET_BOUND'::text
    as verification_status,
  'ORIGIN_GUARD_ONLY'::text as scientific_role,
  f.shadow_only,
  f.trade_permission
from public.alpha_hunter_fill_evidence f;


create or replace view public.alpha_hunter_fill_origin_attribution_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  origin_class,
  coalesce(enter_point_source,'<NULL>') as enter_point_source,
  count(*)::bigint as fill_count,
  count(distinct symbol)::bigint as distinct_symbols,
  min(fill_time_utc) as first_fill_time_utc,
  max(fill_time_utc) as last_fill_time_utc,
  bool_and(heuristic_signal_attribution_eligible)
    as heuristic_signal_attribution_eligible,
  bool_and(verified_alpha_hunter_execution)
    as verified_alpha_hunter_execution,
  false as production_execution_claim_permitted,
  true as shadow_only,
  false as trade_permission
from public.alpha_hunter_fill_origin_attribution_v01
group by origin_class,enter_point_source;

revoke all on public.alpha_hunter_fill_origin_attribution_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_fill_origin_attribution_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_fill_origin_attribution_v01
  to service_role;
grant select on public.alpha_hunter_fill_origin_attribution_status_v01
  to service_role;
