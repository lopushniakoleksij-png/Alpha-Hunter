-- Alpha Hunter Money Economic Ledger v0.1
--
-- Objective:
--   Make economic truth the primary production measurement layer.
--
-- Principles:
--   * account economics and Alpha-Hunter-attributable economics are separated;
--   * unresolved funding is never silently treated as zero;
--   * no profitable-system claim is permitted from unattributed/manual trades;
--   * realized R is exposed only when planned risk was actually persisted;
--   * management-challenger evidence remains descriptive/shadow-only;
--   * this file is read-only analytics: no exchange calls and no trading authority.

create or replace view public.alpha_hunter_economic_trade_ledger_v01
with (security_invoker=true,security_barrier=true)
as
with base as (
  select
    r.roundtrip_episode_id,
    r.symbol,
    r.direction,
    r.opened_or_first_seen_at_utc,
    r.closed_at_utc,
    extract(epoch from (r.closed_at_utc-r.opened_or_first_seen_at_utc))/60.0
      as duration_minutes,
    r.opening_vwap,
    r.closing_vwap,
    r.opened_qty,
    r.profit_field_sum as gross_realized_pnl_usdt,
    r.signed_trading_fee_sum as trading_fee_account_effect_usdt,
    r.fee_adjusted_profit_ex_funding as fee_adjusted_pnl_ex_funding_usdt,
    r.bound_funding_bill_count,
    r.bound_funding_account_effect as bound_funding_account_effect_usdt,
    r.economic_pnl_after_fees_and_bound_funding
      as economic_pnl_after_fees_and_bound_funding_usdt,
    r.funding_coverage_complete,
    r.funding_coverage_status,
    r.full_economic_pnl_claim_permitted,
    r.realistic_net_r_claim_permitted,
    r.verified_alpha_hunter_execution,
    r.alpha_hunter_execution_claim_permitted,
    r.scientific_role as roundtrip_scientific_role
  from public.alpha_hunter_roundtrip_economic_outcome_v01 r
  where r.closed_at_utc is not null
),
first_position as (
  select distinct on (b.roundtrip_episode_id)
    b.roundtrip_episode_id,
    p.position_snapshot_id as first_position_snapshot_id,
    p.captured_at_utc as first_position_observed_at_utc,
    p.average_entry as first_position_average_entry,
    p.mark_price as first_position_mark_price,
    p.structural_stop_price as first_structural_stop_price,
    p.planned_risk_usdt as first_planned_risk_usdt,
    p.strategy_event_id as first_strategy_event_id,
    p.source_order_intent_id as first_source_order_intent_id,
    nullif(btrim(coalesce(
      p.evidence->>'exchange_stop_loss_observed',''
    )),'') as first_exchange_stop_loss_observed,
    nullif(btrim(coalesce(
      p.evidence->>'exchange_take_profit_observed',''
    )),'') as first_exchange_take_profit_observed,
    p.evidence->>'exchange_protection_observation_status'
      as first_protection_observation_status
  from base b
  left join public.alpha_hunter_open_position_snapshots p
    on p.symbol=b.symbol
   and p.direction=b.direction
   and p.captured_at_utc between
       b.opened_or_first_seen_at_utc and b.closed_at_utc
  order by b.roundtrip_episode_id,p.captured_at_utc,p.position_snapshot_id
),
last_position as (
  select distinct on (b.roundtrip_episode_id)
    b.roundtrip_episode_id,
    p.position_snapshot_id as last_position_snapshot_id,
    p.captured_at_utc as last_position_observed_at_utc,
    p.mark_price as last_position_mark_price,
    nullif(btrim(coalesce(
      p.evidence->>'exchange_stop_loss_observed',''
    )),'') as last_exchange_stop_loss_observed,
    nullif(btrim(coalesce(
      p.evidence->>'exchange_take_profit_observed',''
    )),'') as last_exchange_take_profit_observed,
    p.evidence->>'exchange_protection_observation_status'
      as last_protection_observation_status
  from base b
  left join public.alpha_hunter_open_position_snapshots p
    on p.symbol=b.symbol
   and p.direction=b.direction
   and p.captured_at_utc between
       b.opened_or_first_seen_at_utc and b.closed_at_utc
  order by b.roundtrip_episode_id,p.captured_at_utc desc,p.position_snapshot_id desc
),
entry_fill as (
  select distinct on (b.roundtrip_episode_id)
    b.roundtrip_episode_id,
    f.fill_time_utc as first_fill_time_utc,
    f.side as first_fill_side,
    f.trade_side as first_fill_trade_side,
    f.price as first_fill_price,
    f.base_volume as first_fill_base_volume,
    f.enter_point_source as first_fill_enter_point_source,
    f.cost_fields_complete as first_fill_cost_fields_complete
  from base b
  left join public.alpha_hunter_fill_evidence f
    on f.symbol=b.symbol
   and f.fill_time_utc between
       b.opened_or_first_seen_at_utc and b.closed_at_utc
  order by b.roundtrip_episode_id,f.fill_time_utc,f.fill_evidence_id
),
exit_fill as (
  select distinct on (b.roundtrip_episode_id)
    b.roundtrip_episode_id,
    f.fill_time_utc as last_fill_time_utc,
    f.side as last_fill_side,
    f.trade_side as last_fill_trade_side,
    f.price as last_fill_price,
    f.base_volume as last_fill_base_volume,
    f.enter_point_source as last_fill_enter_point_source,
    f.cost_fields_complete as last_fill_cost_fields_complete
  from base b
  left join public.alpha_hunter_fill_evidence f
    on f.symbol=b.symbol
   and f.fill_time_utc between
       b.opened_or_first_seen_at_utc and b.closed_at_utc
  order by b.roundtrip_episode_id,f.fill_time_utc desc,f.fill_evidence_id desc
),
retention as (
  select
    p.roundtrip_episode_id,
    p.observed_peak_at_utc,
    p.observed_peak_mark_price,
    p.observed_peak_unrealized_pnl_usdt,
    p.observed_peak_gross_capture_pct,
    p.observed_peak_gross_giveback_pct,
    p.observed_peak_fee_adjusted_capture_pct_ex_funding,
    p.exit_vs_last_stop_adverse_bps,
    p.observed_peak_to_stop_distance_pct,
    p.retention_evidence_status
  from public.alpha_hunter_profit_retention_lifecycle_v01 p
),
management_shadow as (
  select
    s.roundtrip_episode_id,
    jsonb_object_agg(
      s.policy_id,
      jsonb_build_object(
        'activation_favorable_pct',s.activation_favorable_pct,
        'lock_fraction',s.lock_fraction,
        'challenger_evidence_eligible',s.challenger_evidence_eligible,
        'shadow_policy_activated_at_utc',s.shadow_policy_activated_at_utc,
        'shadow_trigger_at_utc',s.shadow_trigger_at_utc,
        'shadow_exit_price',s.shadow_exit_price,
        'shadow_exit_reason',s.shadow_exit_reason,
        'shadow_gross_pnl',s.shadow_gross_pnl,
        'shadow_gross_delta_vs_actual',s.shadow_gross_delta_vs_actual,
        'counterfactual_net_pnl_claim_permitted',
          s.counterfactual_net_pnl_claim_permitted,
        'promotion_permitted',s.promotion_permitted
      )
      order by s.policy_id
    ) as management_shadow_evidence
  from public.alpha_hunter_profit_management_shadow_v01 s
  group by s.roundtrip_episode_id
)
select
  b.roundtrip_episode_id,
  b.symbol,
  b.direction,
  b.opened_or_first_seen_at_utc,
  b.closed_at_utc,
  b.duration_minutes,
  b.opening_vwap,
  b.closing_vwap,
  b.opened_qty,

  b.gross_realized_pnl_usdt,
  b.trading_fee_account_effect_usdt,
  b.fee_adjusted_pnl_ex_funding_usdt,
  b.bound_funding_bill_count,
  b.bound_funding_account_effect_usdt,
  b.economic_pnl_after_fees_and_bound_funding_usdt,
  b.funding_coverage_complete,
  b.funding_coverage_status,
  b.full_economic_pnl_claim_permitted,

  case
    when b.full_economic_pnl_claim_permitted
      then b.economic_pnl_after_fees_and_bound_funding_usdt
    else b.fee_adjusted_pnl_ex_funding_usdt
  end as currently_claimable_pnl_usdt,

  case
    when b.full_economic_pnl_claim_permitted
      then 'FEES_AND_BOUND_FUNDING'
    else 'FEES_ONLY_FUNDING_INCOMPLETE'
  end as currently_claimable_pnl_basis,

  case
    when b.fee_adjusted_pnl_ex_funding_usdt > 0 then 'WIN'
    when b.fee_adjusted_pnl_ex_funding_usdt < 0 then 'LOSS'
    else 'BREAKEVEN'
  end as fee_adjusted_outcome_ex_funding,

  fp.first_position_snapshot_id,
  fp.first_position_observed_at_utc,
  fp.first_position_average_entry,
  fp.first_position_mark_price,
  fp.first_structural_stop_price,
  fp.first_planned_risk_usdt,
  fp.first_strategy_event_id,
  fp.first_source_order_intent_id,
  fp.first_exchange_stop_loss_observed,
  fp.first_exchange_take_profit_observed,
  fp.first_protection_observation_status,

  lp.last_position_snapshot_id,
  lp.last_position_observed_at_utc,
  lp.last_position_mark_price,
  lp.last_exchange_stop_loss_observed,
  lp.last_exchange_take_profit_observed,
  lp.last_protection_observation_status,

  ef.first_fill_time_utc,
  ef.first_fill_side,
  ef.first_fill_trade_side,
  ef.first_fill_price,
  ef.first_fill_base_volume,
  ef.first_fill_enter_point_source,
  ef.first_fill_cost_fields_complete,

  xf.last_fill_time_utc,
  xf.last_fill_side,
  xf.last_fill_trade_side,
  xf.last_fill_price,
  xf.last_fill_base_volume,
  xf.last_fill_enter_point_source,
  xf.last_fill_cost_fields_complete,

  case
    when fp.first_planned_risk_usdt is not null
      and fp.first_planned_risk_usdt > 0
      then b.fee_adjusted_pnl_ex_funding_usdt/fp.first_planned_risk_usdt
    else null
  end as realized_r_ex_funding_if_planned_risk_observed,

  case
    when fp.first_planned_risk_usdt is not null
      and fp.first_planned_risk_usdt > 0
      then true
    else false
  end as realized_r_observation_available,

  rt.observed_peak_at_utc,
  rt.observed_peak_mark_price,
  rt.observed_peak_unrealized_pnl_usdt,
  rt.observed_peak_gross_capture_pct,
  rt.observed_peak_gross_giveback_pct,
  rt.observed_peak_fee_adjusted_capture_pct_ex_funding,
  rt.exit_vs_last_stop_adverse_bps,
  rt.observed_peak_to_stop_distance_pct,
  rt.retention_evidence_status,

  ms.management_shadow_evidence,

  b.verified_alpha_hunter_execution,
  b.alpha_hunter_execution_claim_permitted,
  case
    when b.verified_alpha_hunter_execution
      and b.alpha_hunter_execution_claim_permitted
      then 'ATTRIBUTABLE_TO_ALPHA_HUNTER'
    when b.verified_alpha_hunter_execution
      and not b.alpha_hunter_execution_claim_permitted
      then 'VERIFIED_EXECUTION_CLAIM_BLOCKED'
    else 'NOT_ATTRIBUTABLE_TO_ALPHA_HUNTER'
  end as alpha_hunter_attribution_status,

  (
    b.verified_alpha_hunter_execution
    and b.alpha_hunter_execution_claim_permitted
    and b.full_economic_pnl_claim_permitted
  ) as alpha_hunter_full_economic_claim_permitted,

  b.realistic_net_r_claim_permitted,
  b.roundtrip_scientific_role,

  true as account_economic_observation,
  false as profitability_claim_from_unattributed_trade_permitted,
  false as management_change_permitted,
  false as threshold_change_permitted,
  false as promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from base b
left join first_position fp using(roundtrip_episode_id)
left join last_position lp using(roundtrip_episode_id)
left join entry_fill ef using(roundtrip_episode_id)
left join exit_fill xf using(roundtrip_episode_id)
left join retention rt using(roundtrip_episode_id)
left join management_shadow ms using(roundtrip_episode_id);


create or replace view public.alpha_hunter_money_status_v01
with (security_invoker=true,security_barrier=true)
as
with ledger as (
  select *
  from public.alpha_hunter_economic_trade_ledger_v01
),
ordered as (
  select
    l.*,
    sum(l.fee_adjusted_pnl_ex_funding_usdt) over(
      order by l.closed_at_utc,l.roundtrip_episode_id
      rows between unbounded preceding and current row
    ) as cumulative_fee_adjusted_pnl_ex_funding
  from ledger l
),
drawdown as (
  select
    o.*,
    max(o.cumulative_fee_adjusted_pnl_ex_funding) over(
      order by o.closed_at_utc,o.roundtrip_episode_id
      rows between unbounded preceding and current row
    ) as running_peak_cumulative_pnl
  from ordered o
),
agg as (
  select
    count(*)::bigint as completed_trade_count,
    count(*) filter(
      where fee_adjusted_pnl_ex_funding_usdt>0
    )::bigint as winning_trade_count,
    count(*) filter(
      where fee_adjusted_pnl_ex_funding_usdt<=0
    )::bigint as nonwinning_trade_count,
    100.0*count(*) filter(
      where fee_adjusted_pnl_ex_funding_usdt>0
    )/nullif(count(*),0) as win_rate_pct_ex_funding,
    sum(fee_adjusted_pnl_ex_funding_usdt)
      as total_fee_adjusted_pnl_ex_funding_usdt,
    avg(fee_adjusted_pnl_ex_funding_usdt)
      as expectancy_usdt_per_trade_ex_funding,
    avg(fee_adjusted_pnl_ex_funding_usdt) filter(
      where fee_adjusted_pnl_ex_funding_usdt>0
    ) as average_win_usdt_ex_funding,
    avg(fee_adjusted_pnl_ex_funding_usdt) filter(
      where fee_adjusted_pnl_ex_funding_usdt<0
    ) as average_loss_usdt_ex_funding,
    sum(case
      when fee_adjusted_pnl_ex_funding_usdt>0
        then fee_adjusted_pnl_ex_funding_usdt
      else 0
    end)
    /
    nullif(abs(sum(case
      when fee_adjusted_pnl_ex_funding_usdt<0
        then fee_adjusted_pnl_ex_funding_usdt
      else 0
    end)),0) as profit_factor_ex_funding,

    count(*) filter(
      where full_economic_pnl_claim_permitted
    )::bigint as full_economic_trade_count,
    100.0*count(*) filter(
      where full_economic_pnl_claim_permitted
    )/nullif(count(*),0) as full_economic_coverage_pct,
    sum(economic_pnl_after_fees_and_bound_funding_usdt) filter(
      where full_economic_pnl_claim_permitted
    ) as total_full_economic_pnl_on_covered_trades_usdt,

    count(*) filter(
      where alpha_hunter_attribution_status='ATTRIBUTABLE_TO_ALPHA_HUNTER'
    )::bigint as alpha_hunter_attributable_trade_count,
    sum(fee_adjusted_pnl_ex_funding_usdt) filter(
      where alpha_hunter_attribution_status='ATTRIBUTABLE_TO_ALPHA_HUNTER'
    ) as alpha_hunter_attributable_fee_adjusted_pnl_ex_funding_usdt,

    count(*) filter(
      where alpha_hunter_full_economic_claim_permitted
    )::bigint as alpha_hunter_full_economic_trade_count,
    sum(economic_pnl_after_fees_and_bound_funding_usdt) filter(
      where alpha_hunter_full_economic_claim_permitted
    ) as alpha_hunter_full_economic_pnl_usdt,

    count(*) filter(
      where realized_r_observation_available
    )::bigint as planned_risk_observed_trade_count,
    100.0*count(*) filter(
      where realized_r_observation_available
    )/nullif(count(*),0) as planned_risk_coverage_pct,

    count(*) filter(
      where retention_evidence_status='MEASURED'
    )::bigint as profit_retention_measured_trade_count,
    avg(observed_peak_gross_capture_pct) filter(
      where retention_evidence_status='MEASURED'
    ) as average_observed_peak_gross_capture_pct,
    avg(observed_peak_gross_giveback_pct) filter(
      where retention_evidence_status='MEASURED'
    ) as average_observed_peak_gross_giveback_pct,

    min(
      cumulative_fee_adjusted_pnl_ex_funding-running_peak_cumulative_pnl
    ) as max_realized_drawdown_usdt_ex_funding
  from drawdown
)
select
  a.*,
  (a.total_fee_adjusted_pnl_ex_funding_usdt>0)
    as account_fee_adjusted_profit_positive,
  (a.profit_factor_ex_funding>1.0)
    as account_profit_factor_above_one,
  (a.alpha_hunter_attributable_trade_count>0)
    as alpha_hunter_attribution_sample_exists,
  (a.planned_risk_observed_trade_count>0)
    as realized_r_measurement_exists,
  case
    when a.alpha_hunter_attributable_trade_count=0
      then 'NO_ATTRIBUTABLE_ALPHA_HUNTER_CLOSED_TRADES'
    when a.alpha_hunter_full_economic_trade_count=0
      then 'ATTRIBUTABLE_TRADES_LACK_FULL_ECONOMIC_COVERAGE'
    else 'ATTRIBUTABLE_ECONOMICS_AVAILABLE'
  end as alpha_hunter_profitability_measurement_status,
  case
    when a.total_fee_adjusted_pnl_ex_funding_usdt>0
      and a.profit_factor_ex_funding>1.0
      then 'ACCOUNT_POSITIVE_EX_FUNDING'
    else 'ACCOUNT_NOT_POSITIVE_EX_FUNDING'
  end as account_money_status,
  false as alpha_hunter_profitability_claim_permitted,
  false as management_change_permitted,
  false as threshold_change_permitted,
  false as promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from agg a;


create or replace view public.alpha_hunter_money_direction_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  direction,
  count(*)::bigint as completed_trade_count,
  count(*) filter(
    where fee_adjusted_pnl_ex_funding_usdt>0
  )::bigint as winning_trade_count,
  count(*) filter(
    where fee_adjusted_pnl_ex_funding_usdt<=0
  )::bigint as nonwinning_trade_count,
  100.0*count(*) filter(
    where fee_adjusted_pnl_ex_funding_usdt>0
  )/nullif(count(*),0) as win_rate_pct_ex_funding,
  sum(fee_adjusted_pnl_ex_funding_usdt)
    as total_fee_adjusted_pnl_ex_funding_usdt,
  avg(fee_adjusted_pnl_ex_funding_usdt)
    as expectancy_usdt_per_trade_ex_funding,
  sum(case
    when fee_adjusted_pnl_ex_funding_usdt>0
      then fee_adjusted_pnl_ex_funding_usdt
    else 0
  end)
  /
  nullif(abs(sum(case
    when fee_adjusted_pnl_ex_funding_usdt<0
      then fee_adjusted_pnl_ex_funding_usdt
    else 0
  end)),0) as profit_factor_ex_funding,
  count(*) filter(
    where alpha_hunter_attribution_status='ATTRIBUTABLE_TO_ALPHA_HUNTER'
  )::bigint as alpha_hunter_attributable_trade_count,
  false as profitability_claim_permitted,
  false as promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from public.alpha_hunter_economic_trade_ledger_v01
group by direction;


create or replace view public.alpha_hunter_money_symbol_concentration_v01
with (security_invoker=true,security_barrier=true)
as
select
  symbol,
  count(*)::bigint as completed_trade_count,
  count(*) filter(
    where fee_adjusted_pnl_ex_funding_usdt>0
  )::bigint as winning_trade_count,
  count(*) filter(
    where fee_adjusted_pnl_ex_funding_usdt<=0
  )::bigint as nonwinning_trade_count,
  sum(fee_adjusted_pnl_ex_funding_usdt)
    as total_fee_adjusted_pnl_ex_funding_usdt,
  avg(fee_adjusted_pnl_ex_funding_usdt)
    as expectancy_usdt_per_trade_ex_funding,
  max(fee_adjusted_pnl_ex_funding_usdt)
    as best_trade_pnl_ex_funding_usdt,
  min(fee_adjusted_pnl_ex_funding_usdt)
    as worst_trade_pnl_ex_funding_usdt,
  false as profitability_claim_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from public.alpha_hunter_economic_trade_ledger_v01
group by symbol;


revoke all on public.alpha_hunter_economic_trade_ledger_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_money_status_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_money_direction_status_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_money_symbol_concentration_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_economic_trade_ledger_v01
  to service_role;
grant select on public.alpha_hunter_money_status_v01
  to service_role;
grant select on public.alpha_hunter_money_direction_status_v01
  to service_role;
grant select on public.alpha_hunter_money_symbol_concentration_v01
  to service_role;
