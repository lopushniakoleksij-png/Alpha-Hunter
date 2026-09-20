-- Alpha Hunter multi-timeframe geometry research v0.3
-- Read-only exploratory screen of alternative observable structural geometry.
--
-- Purpose:
--   Compare the existing 1H-stop/1H-target geometry with three observable
--   multi-timeframe variants using only levels that were present in the frozen
--   source payload at observation time:
--     * 1H stop  -> 1H target  (current structural baseline)
--     * 15m stop -> 1H target  (local invalidation)
--     * 15m stop -> 4H target  (local invalidation / wider structural target)
--     * 1H stop  -> 4H target  (wider structural target)
--
-- Scientific boundary:
--   This is a retrospective exploratory variant screen over already-observed
--   shadow evidence. It may diagnose geometry failure modes, but it must not
--   derive/activate thresholds, authorize T0/T1/T2, grant trade permission,
--   or promote any variant. A separately preregistered prospective holdout is
--   required before any production change.
--
-- Execution boundary:
--   Views only. No writer, cron, exchange/order call, risk/leverage change,
--   stage mutation, or production permission path is introduced.

create or replace view public.alpha_hunter_geometry_multitimeframe_observations_v03
with (security_invoker=true)
as
with source_rows as (
  select
    g.diagnostic_id,
    g.run_id,
    g.source_signal_id,
    g.captured_at_utc,
    g.symbol,
    g.candidate_direction as direction,
    g.explicit_entry as entry_price,
    g.classification as source_geometry_classification,
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
      when (sf.source_payload#>>'{timeframes,1H,support}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,1H,support}')::double precision
    end as support_1h,
    case
      when (sf.source_payload#>>'{timeframes,1H,resistance}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,1H,resistance}')::double precision
    end as resistance_1h,
    case
      when (sf.source_payload#>>'{timeframes,4H,support}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,4H,support}')::double precision
    end as support_4h,
    case
      when (sf.source_payload#>>'{timeframes,4H,resistance}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,4H,resistance}')::double precision
    end as resistance_4h,
    case
      when (sf.source_payload#>>'{behaviour,spread_pct}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{behaviour,spread_pct}')::double precision
    end as spread_pct,
    case
      when (sf.source_payload#>>'{timeframes,15m,indicators,atr_pct}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,15m,indicators,atr_pct}')::double precision
    end as atr_15m_pct,
    case
      when (sf.source_payload#>>'{timeframes,1H,indicators,atr_pct}')
        ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
      then (sf.source_payload#>>'{timeframes,1H,indicators,atr_pct}')::double precision
    end as atr_1h_pct,
    sf.source_payload->>'market_phase' as market_phase,
    sf.source_payload->>'opportunity_timing' as opportunity_timing
  from public.alpha_hunter_geometry_diagnostics g
  left join public.alpha_hunter_signal_features sf
    on sf.signal_id=g.source_signal_id
  where g.model_version='geometry-diagnostics-v0.2.2-money-entry-scope-aligned'
    and g.shadow_only=true
    and g.trade_permission=false
),
variants as (
  select
    s.*,
    '1H_STOP_1H_TARGET'::text as research_variant,
    '1H'::text as stop_timeframe,
    '1H'::text as target_timeframe,
    case when s.direction='LONG' then s.support_1h else s.resistance_1h end as research_stop,
    case when s.direction='LONG' then s.resistance_1h else s.support_1h end as research_target
  from source_rows s

  union all

  select
    s.*,
    '15M_STOP_1H_TARGET'::text,
    '15m'::text,
    '1H'::text,
    case when s.direction='LONG' then s.support_15m else s.resistance_15m end,
    case when s.direction='LONG' then s.resistance_1h else s.support_1h end
  from source_rows s

  union all

  select
    s.*,
    '15M_STOP_4H_TARGET'::text,
    '15m'::text,
    '4H'::text,
    case when s.direction='LONG' then s.support_15m else s.resistance_15m end,
    case when s.direction='LONG' then s.resistance_4h else s.support_4h end
  from source_rows s

  union all

  select
    s.*,
    '1H_STOP_4H_TARGET'::text,
    '1H'::text,
    '4H'::text,
    case when s.direction='LONG' then s.support_1h else s.resistance_1h end,
    case when s.direction='LONG' then s.resistance_4h else s.support_4h end
  from source_rows s
),
geometry as (
  select
    v.*,
    (
      v.entry_price is not null
      and v.entry_price>0
      and v.research_stop is not null
      and v.research_target is not null
      and (
        (v.direction='LONG' and v.research_stop<v.entry_price and v.research_target>v.entry_price)
        or
        (v.direction='SHORT' and v.research_stop>v.entry_price and v.research_target<v.entry_price)
      )
    ) as geometry_valid,
    case
      when v.entry_price is not null and v.entry_price>0 and v.research_stop is not null
      then abs(v.entry_price-v.research_stop)/v.entry_price*100.0
    end as stop_distance_pct,
    case
      when v.entry_price is not null and v.entry_price>0 and v.research_target is not null
      then abs(v.research_target-v.entry_price)/v.entry_price*100.0
    end as target_distance_pct,
    case
      when v.entry_price is not null
       and v.research_stop is not null
       and v.research_target is not null
       and abs(v.entry_price-v.research_stop)>0
       and (
         (v.direction='LONG' and v.research_stop<v.entry_price and v.research_target>v.entry_price)
         or
         (v.direction='SHORT' and v.research_stop>v.entry_price and v.research_target<v.entry_price)
       )
      then abs(v.research_target-v.entry_price)/abs(v.entry_price-v.research_stop)
    end as research_rr
  from variants v
),
contextualized as (
  select
    g.*,
    case
      when g.stop_distance_pct is not null and g.spread_pct is not null and g.spread_pct>0
      then g.stop_distance_pct/g.spread_pct
    end as stop_to_spread_multiple,
    case
      when g.stop_distance_pct is not null and g.atr_15m_pct is not null and g.atr_15m_pct>0
      then g.stop_distance_pct/g.atr_15m_pct
    end as stop_to_atr_15m_multiple,
    case
      when g.stop_distance_pct is not null and g.atr_1h_pct is not null and g.atr_1h_pct>0
      then g.stop_distance_pct/g.atr_1h_pct
    end as stop_to_atr_1h_multiple
  from geometry g
),
scorecard_bound as (
  select
    g.*,
    c.scorecard_id,
    c.candidate_at_utc as scorecard_candidate_at_utc,
    c.geometry_valid as scanner_geometry_valid,
    c.model_version as scorecard_model_version
  from contextualized g
  left join lateral (
    select c.*
    from public.alpha_hunter_big_mover_money_scorecard_candidates c
    where c.run_id=g.run_id
      and c.symbol=g.symbol
      and c.direction=g.direction
      and c.shadow_only=true
      and c.trade_permission=false
    order by c.created_at desc
    limit 1
  ) c on true
),
outcome_joined as (
  select
    b.*,
    o.horizon_hours,
    o.horizon_due_at_utc,
    o.evaluation_status,
    o.evaluated_at_utc,
    o.mfe_pct,
    o.mae_pct,
    o.direction_adjusted_close_return_pct,
    o.realistic_net_r,
    o.realistic_net_r_status
  from scorecard_bound b
  left join public.alpha_hunter_big_mover_money_scorecard_outcomes o
    on o.scorecard_id=b.scorecard_id
   and o.shadow_only=true
   and o.trade_permission=false
)
select
  j.diagnostic_id,
  j.run_id,
  j.source_signal_id,
  j.captured_at_utc,
  j.symbol,
  j.direction,
  j.research_variant,
  j.stop_timeframe,
  j.target_timeframe,
  j.entry_price,
  j.research_stop,
  j.research_target,
  j.geometry_valid,
  j.research_rr,
  j.stop_distance_pct,
  j.target_distance_pct,
  j.stop_to_spread_multiple,
  j.stop_to_atr_15m_multiple,
  j.stop_to_atr_1h_multiple,
  j.market_phase,
  j.opportunity_timing,
  j.scorecard_id,
  (j.scorecard_id is not null) as scorecard_bound,
  j.scorecard_candidate_at_utc,
  j.scanner_geometry_valid,
  j.scorecard_model_version,
  j.horizon_hours,
  j.horizon_due_at_utc,
  j.evaluation_status,
  j.evaluated_at_utc,
  j.mfe_pct,
  j.mae_pct,
  j.direction_adjusted_close_return_pct,
  j.realistic_net_r,
  j.realistic_net_r_status,
  case
    when j.geometry_valid and j.research_rr is not null
    then j.research_rr>=5.0
  end as rr_ge_5_current_reference_only,
  case
    when j.evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')
      and j.geometry_valid
      and j.mae_pct is not null
      and j.stop_distance_pct is not null
    then j.mae_pct>=j.stop_distance_pct
  end as research_stop_touched,
  case
    when j.evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')
      and j.geometry_valid
      and j.mfe_pct is not null
      and j.target_distance_pct is not null
    then j.mfe_pct>=j.target_distance_pct
  end as research_target_touched,
  case
    when j.scorecard_id is null then 'SCORECARD_UNAVAILABLE'
    when j.horizon_hours is null then 'OUTCOME_ROW_UNAVAILABLE'
    when j.evaluation_status in ('PENDING','RETRYABLE_ERROR') then 'OUTCOME_PENDING'
    when j.evaluation_status not in ('EVALUATED','AMBIGUOUS_INTRABAR') then 'OUTCOME_DATA_INSUFFICIENT'
    when j.geometry_valid is not true then 'GEOMETRY_INVALID'
    when j.mae_pct is null or j.mfe_pct is null
      or j.stop_distance_pct is null or j.target_distance_pct is null
      then 'PATH_DATA_INCOMPLETE'
    when j.mae_pct>=j.stop_distance_pct and j.mfe_pct>=j.target_distance_pct
      then 'BOTH_TOUCHED_PATH_ORDER_UNKNOWN'
    when j.mae_pct>=j.stop_distance_pct then 'STOP_TOUCHED_ONLY'
    when j.mfe_pct>=j.target_distance_pct then 'TARGET_TOUCHED_ONLY'
    else 'NEITHER_TOUCHED'
  end as research_geometry_path_class,
  'EXPLORATORY_RETROSPECTIVE_VARIANT_SCREEN'::text as scientific_role,
  'CURRENT_PRODUCTION_RR_REFERENCE_5_IS_DESCRIPTIVE_ONLY'::text as rr_reference_role,
  'MFE_MAE_TOUCH_TEST_REUSES_EXISTING_SCORECARD; BOTH_TOUCHED_HAS_UNKNOWN_ORDER'::text as path_method,
  false as exact_research_fill_claim_permitted,
  false as confirmatory_claim_permitted,
  false as threshold_derivation_permitted,
  false as t0_authorized,
  false as t1_authorized,
  false as t2_authorized,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission
from outcome_joined j;

revoke all on public.alpha_hunter_geometry_multitimeframe_observations_v03
  from public,anon,authenticated;
grant select on public.alpha_hunter_geometry_multitimeframe_observations_v03
  to service_role;


create or replace view public.alpha_hunter_geometry_multitimeframe_status_v03
with (security_invoker=true)
as
with base as (
  select *
  from public.alpha_hunter_geometry_multitimeframe_observations_v03
),
geometry_only as (
  select distinct on (diagnostic_id,research_variant)
    diagnostic_id,
    research_variant,
    geometry_valid,
    research_rr,
    stop_distance_pct,
    target_distance_pct,
    stop_to_spread_multiple,
    stop_to_atr_15m_multiple,
    stop_to_atr_1h_multiple
  from base
  order by diagnostic_id,research_variant,horizon_hours nulls first
),
geometry_stats as (
  select
    research_variant,
    count(*)::bigint as geometry_observations,
    count(*) filter (where geometry_valid)::bigint as valid_geometry_observations,
    percentile_cont(0.5) within group (order by research_rr)
      filter (where geometry_valid and research_rr is not null) as rr_median,
    percentile_cont(0.9) within group (order by research_rr)
      filter (where geometry_valid and research_rr is not null) as rr_p90,
    max(research_rr) filter (where geometry_valid and research_rr is not null) as rr_max,
    count(*) filter (
      where geometry_valid and research_rr>=5.0
    )::bigint as rr_ge_5_current_reference_observations,
    avg(stop_distance_pct) filter (where geometry_valid) as avg_stop_distance_pct,
    avg(target_distance_pct) filter (where geometry_valid) as avg_target_distance_pct,
    avg(stop_to_spread_multiple) filter (where geometry_valid) as avg_stop_to_spread_multiple,
    avg(stop_to_atr_15m_multiple) filter (where geometry_valid) as avg_stop_to_atr_15m_multiple,
    avg(stop_to_atr_1h_multiple) filter (where geometry_valid) as avg_stop_to_atr_1h_multiple
  from geometry_only
  group by research_variant
),
outcome_stats as (
  select
    research_variant,
    horizon_hours,
    count(*) filter (
      where geometry_valid
        and evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')
    )::bigint as matured_outcome_rows,
    count(*) filter (
      where geometry_valid
        and evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')
        and research_stop_touched is false
    )::bigint as stop_survived_rows,
    count(*) filter (
      where geometry_valid
        and evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')
        and research_target_touched is true
        and research_stop_touched is false
    )::bigint as target_touched_without_stop_rows,
    count(*) filter (
      where geometry_valid
        and research_geometry_path_class='TARGET_TOUCHED_ONLY'
    )::bigint as target_only_rows,
    count(*) filter (
      where geometry_valid
        and research_geometry_path_class='STOP_TOUCHED_ONLY'
    )::bigint as stop_only_rows,
    count(*) filter (
      where geometry_valid
        and research_geometry_path_class='BOTH_TOUCHED_PATH_ORDER_UNKNOWN'
    )::bigint as both_touched_unknown_order_rows,
    count(*) filter (
      where geometry_valid
        and research_geometry_path_class='NEITHER_TOUCHED'
    )::bigint as neither_touched_rows,
    avg(mfe_pct) filter (
      where geometry_valid
        and evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')
    ) as avg_mfe_pct,
    avg(mae_pct) filter (
      where geometry_valid
        and evaluation_status in ('EVALUATED','AMBIGUOUS_INTRABAR')
    ) as avg_mae_pct,
    max(evaluated_at_utc) as latest_evaluated_at_utc
  from base
  where horizon_hours in (1,4,12,24)
  group by research_variant,horizon_hours
)
select
  g.research_variant,
  o.horizon_hours,
  g.geometry_observations,
  g.valid_geometry_observations,
  g.rr_median,
  g.rr_p90,
  g.rr_max,
  g.rr_ge_5_current_reference_observations,
  case
    when g.valid_geometry_observations>0
    then round(
      100.0*g.rr_ge_5_current_reference_observations
      /g.valid_geometry_observations,
      2
    )
  end as rr_ge_5_current_reference_pct,
  g.avg_stop_distance_pct,
  g.avg_target_distance_pct,
  g.avg_stop_to_spread_multiple,
  g.avg_stop_to_atr_15m_multiple,
  g.avg_stop_to_atr_1h_multiple,
  o.matured_outcome_rows,
  o.stop_survived_rows,
  case
    when o.matured_outcome_rows>0
    then round(100.0*o.stop_survived_rows/o.matured_outcome_rows,2)
  end as stop_survival_pct,
  o.target_touched_without_stop_rows,
  case
    when o.matured_outcome_rows>0
    then round(
      100.0*o.target_touched_without_stop_rows/o.matured_outcome_rows,
      2
    )
  end as target_touched_without_stop_pct,
  o.target_only_rows,
  o.stop_only_rows,
  o.both_touched_unknown_order_rows,
  o.neither_touched_rows,
  o.avg_mfe_pct,
  o.avg_mae_pct,
  o.latest_evaluated_at_utc,
  'EXPLORATORY_RETROSPECTIVE_VARIANT_SCREEN'::text as scientific_state,
  'NO_VARIANT_PROMOTION_FROM_THIS_VIEW'::text as scientific_conclusion,
  'Use this screen to choose hypotheses only. Preregister a separate prospective holdout before changing entry, stop, target, RR, T0/T1/T2, risk, leverage, or production permission.'::text as next_gate,
  false as confirmatory_claim_permitted,
  false as threshold_derivation_permitted,
  false as t0_authorized,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission
from geometry_stats g
join outcome_stats o using (research_variant)
order by o.horizon_hours,g.research_variant;

revoke all on public.alpha_hunter_geometry_multitimeframe_status_v03
  from public,anon,authenticated;
grant select on public.alpha_hunter_geometry_multitimeframe_status_v03
  to service_role;
