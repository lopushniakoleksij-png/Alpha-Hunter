-- Alpha Hunter direction confirmation tax v0.1
--
-- Purpose:
--   Measure decision-time price/RR deterioration between an EARLY parent-aligned
--   candidate reference and the first later full scanner-direction alignment.
--
-- This is descriptive confirmation-tax evidence only.
-- It uses no future market outcome, no sealed holdout outcome, no order path,
-- and cannot authorize T0/T1/T2 or change the 5R requirement.
--
-- Candidate overlap rule:
--   Reuse the preregistered geometry holdout's exact 24H symbol-direction
--   cooldown. This is an episode-deduplication rule, not a trading threshold.

create or replace view public.alpha_hunter_direction_confirmation_tax_pairs_v01
with (security_invoker=true,security_barrier=true)
as
with recursive source_rows as (
  select
    g.diagnostic_id,
    g.captured_at_utc,
    g.symbol,
    g.candidate_direction as direction,
    g.scanner_direction,
    g.explicit_entry as entry_price,
    g.evidence->>'parent_direction_12h' as parent_12h,
    g.evidence->>'parent_direction_1d' as parent_1d,
    g.evidence->>'opportunity_timing' as opportunity_timing,
    g.evidence->>'market_phase' as market_phase,
    sf.source_payload,
    case
      when (sf.source_payload#>>'{timeframes,15m,support}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,15m,support}')::double precision
    end as support_15m,
    case
      when (sf.source_payload#>>'{timeframes,15m,resistance}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,15m,resistance}')::double precision
    end as resistance_15m,
    case
      when (sf.source_payload#>>'{timeframes,4H,support}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,4H,support}')::double precision
    end as support_4h,
    case
      when (sf.source_payload#>>'{timeframes,4H,resistance}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,4H,resistance}')::double precision
    end as resistance_4h
  from public.alpha_hunter_geometry_diagnostics g
  join public.alpha_hunter_signal_features sf
    on sf.signal_id=g.source_signal_id
  where g.shadow_only=true
    and g.trade_permission=false
    and g.explicit_entry>0
    and g.candidate_direction in ('LONG','SHORT')
),
geometry as (
  select
    s.*,
    case
      when s.direction='LONG'
       and s.support_15m<s.entry_price
       and s.resistance_4h>s.entry_price
      then abs(s.resistance_4h-s.entry_price)
        /nullif(abs(s.entry_price-s.support_15m),0)
      when s.direction='SHORT'
       and s.resistance_15m>s.entry_price
       and s.support_4h<s.entry_price
      then abs(s.entry_price-s.support_4h)
        /nullif(abs(s.resistance_15m-s.entry_price),0)
    end as rr_15m_stop_4h_target,
    (
      (s.direction='LONG'
       and s.parent_12h='BULLISH'
       and s.parent_1d='BULLISH')
      or
      (s.direction='SHORT'
       and s.parent_12h='BEARISH'
       and s.parent_1d='BEARISH')
    ) as parent_12h_1d_aligned
  from source_rows s
),
early_eligible as (
  select g.*
  from geometry g
  where g.parent_12h_1d_aligned=true
    and g.opportunity_timing='EARLY'
    and g.rr_15m_stop_4h_target is not null
    and g.scanner_direction is distinct from g.direction
),
seed as (
  select distinct on (e.symbol,e.direction)
    e.*
  from early_eligible e
  order by e.symbol,e.direction,e.captured_at_utc,e.diagnostic_id
),
cooldown_selected as (
  select
    s.*
  from seed s

  union all

  select
    n.*
  from cooldown_selected p
  join lateral (
    select e.*
    from early_eligible e
    where e.symbol=p.symbol
      and e.direction=p.direction
      and e.captured_at_utc>=p.captured_at_utc+interval '24 hours'
    order by e.captured_at_utc,e.diagnostic_id
    limit 1
  ) n on true
),
paired as (
  select
    e.diagnostic_id as early_diagnostic_id,
    e.symbol,
    e.direction,
    e.captured_at_utc as early_at_utc,
    e.entry_price as early_entry,
    e.rr_15m_stop_4h_target as early_rr,
    e.parent_12h,
    e.parent_1d,
    e.opportunity_timing as early_opportunity_timing,
    e.market_phase as early_market_phase,
    s.diagnostic_id as scanner_diagnostic_id,
    s.captured_at_utc as scanner_aligned_at_utc,
    s.entry_price as scanner_entry,
    s.rr_15m_stop_4h_target as scanner_rr
  from cooldown_selected e
  left join lateral (
    select g.*
    from geometry g
    where g.symbol=e.symbol
      and g.direction=e.direction
      and g.scanner_direction=e.direction
      and g.captured_at_utc>=e.captured_at_utc
      and g.captured_at_utc<=e.captured_at_utc+interval '24 hours'
      and g.rr_15m_stop_4h_target is not null
    order by g.captured_at_utc,g.diagnostic_id
    limit 1
  ) s on true
)
select
  p.early_diagnostic_id,
  p.scanner_diagnostic_id,
  p.symbol,
  p.direction,
  p.early_at_utc,
  p.scanner_aligned_at_utc,
  p.early_entry,
  p.scanner_entry,
  p.early_rr,
  p.scanner_rr,
  p.parent_12h,
  p.parent_1d,
  p.early_opportunity_timing,
  p.early_market_phase,
  case
    when p.scanner_aligned_at_utc is not null
    then extract(
      epoch from (p.scanner_aligned_at_utc-p.early_at_utc)
    )/3600.0
  end as confirmation_delay_hours,
  case
    when p.scanner_entry is null then null
    when p.direction='LONG'
      then (p.scanner_entry/p.early_entry-1.0)*100.0
    when p.direction='SHORT'
      then (p.early_entry/p.scanner_entry-1.0)*100.0
  end as confirmation_price_tax_pct,
  case
    when p.scanner_rr is not null
    then p.early_rr-p.scanner_rr
  end as confirmation_rr_tax,
  (p.early_rr>=5.0) as early_rr5,
  case when p.scanner_rr is not null then p.scanner_rr>=5.0 end
    as scanner_rr5,
  case
    when p.scanner_rr is null then 'NO_SCANNER_ALIGNMENT_WITHIN_24H'
    when p.early_rr>=5.0 and p.scanner_rr<5.0 then 'LOST_RR5'
    when p.early_rr>=5.0 and p.scanner_rr>=5.0 then 'RETAINED_RR5'
    when p.early_rr<5.0 and p.scanner_rr>=5.0 then 'GAINED_RR5'
    else 'NEVER_RR5'
  end as rr5_transition,
  24::integer as cooldown_hours,
  'GEOMETRY_HOLDOUT_OVERLAP_RULE_REUSED'::text as cooldown_rule_source,
  '15M_STOP_4H_TARGET'::text as geometry_variant,
  false as outcome_evidence_used,
  false as sealed_holdout_outcome_read,
  false as t0_authorized,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  'DESCRIPTIVE_DECISION_TIME_CONFIRMATION_TAX_ONLY'::text
    as scientific_role,
  true as shadow_only,
  false as trade_permission,
  'direction-confirmation-tax-v0.1'::text as model_version
from paired p;


create or replace view public.alpha_hunter_direction_confirmation_tax_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  count(*)::bigint as early_episode_anchors,
  count(*) filter(
    where scanner_aligned_at_utc is not null
  )::bigint as paired_scanner_confirmations,
  count(*) filter(
    where scanner_aligned_at_utc is null
  )::bigint as no_scanner_alignment_within_24h,
  count(*) filter(where early_rr5)::bigint as early_rr5_episodes,
  count(*) filter(where scanner_rr5 is true)::bigint
    as scanner_rr5_episodes,
  count(*) filter(where rr5_transition='LOST_RR5')::bigint
    as lost_rr5_after_confirmation,
  count(*) filter(where rr5_transition='RETAINED_RR5')::bigint
    as retained_rr5_after_confirmation,
  count(*) filter(where rr5_transition='GAINED_RR5')::bigint
    as gained_rr5_after_confirmation,
  percentile_cont(0.5) within group(
    order by confirmation_delay_hours
  ) filter(where confirmation_delay_hours is not null)
    as median_confirmation_delay_hours,
  percentile_cont(0.5) within group(
    order by confirmation_price_tax_pct
  ) filter(where confirmation_price_tax_pct is not null)
    as median_confirmation_price_tax_pct,
  percentile_cont(0.9) within group(
    order by confirmation_price_tax_pct
  ) filter(where confirmation_price_tax_pct is not null)
    as p90_confirmation_price_tax_pct,
  percentile_cont(0.5) within group(
    order by early_rr
  ) as median_early_rr,
  percentile_cont(0.5) within group(
    order by scanner_rr
  ) filter(where scanner_rr is not null)
    as median_scanner_rr,
  percentile_cont(0.5) within group(
    order by confirmation_rr_tax
  ) filter(where confirmation_rr_tax is not null)
    as median_confirmation_rr_tax,
  percentile_cont(0.9) within group(
    order by confirmation_rr_tax
  ) filter(where confirmation_rr_tax is not null)
    as p90_confirmation_rr_tax,
  false as outcome_evidence_used,
  false as sealed_holdout_outcome_read,
  false as t0_authorized,
  false as threshold_change_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission
from public.alpha_hunter_direction_confirmation_tax_pairs_v01;


revoke all on public.alpha_hunter_direction_confirmation_tax_pairs_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_direction_confirmation_tax_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_direction_confirmation_tax_pairs_v01
  to service_role;
grant select on public.alpha_hunter_direction_confirmation_tax_status_v01
  to service_role;
