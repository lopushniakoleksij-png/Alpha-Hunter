begin;

-- Alpha Hunter paper protective-exit observation-delay audit v0.1.
--
-- Problem:
-- protective exits are observed only when a later canonical quote is captured.
-- The raw paper model correctly preserves that later observed quote, but a
-- coarse observation interval can move the modeled exit far beyond the
-- protective trigger and therefore distort measured R.
--
-- This migration is audit-only:
-- * raw paper decisions, fills and exits remain immutable;
-- * no outcome is rewritten;
-- * a trigger-anchored counterfactual is exposed beside the observed result;
-- * the counterfactual is not a profitability claim and cannot grant authority.

create or replace view public.alpha_hunter_paper_exit_observation_delay_audit_v01
with (security_invoker=true,security_barrier=true)
as
with base as (
  select
    c.exit_fill_id,
    c.entry_order_id,
    c.decision_id,
    c.entry_decision_run_id,
    c.exit_source_run_id,
    c.symbol,
    c.direction,
    c.exit_reason,
    c.closed_at_utc,
    c.quantity,
    c.entry_average_fill_price,
    c.exit_price as observed_exit_price,
    c.paper_net_pnl_ex_funding as observed_net_pnl_ex_funding,
    c.net_r_ex_funding as observed_net_r_ex_funding,
    c.planned_risk_usdt,
    x.side as exit_side,
    x.slippage_bps,
    x.fee_bps,
    x.entry_costs_usdt,
    x.spread_cost_usdt as observed_spread_cost_usdt,
    x.slippage_cost_usdt as observed_slippage_cost_usdt,
    x.exit_costs_usdt as observed_exit_costs_usdt,
    p.trigger_price as protective_trigger_price,
    a.observed_at_utc as trigger_observed_at_utc,
    a.best_bid as trigger_observed_best_bid,
    a.best_ask as trigger_observed_best_ask,
    a.evidence->>'quote_source' as trigger_observed_quote_source,
    case
      when x.side='SELL'
        then p.trigger_price*(1.0-x.slippage_bps/10000.0)
      when x.side='BUY'
        then p.trigger_price*(1.0+x.slippage_bps/10000.0)
      else null
    end as trigger_anchored_exit_price
  from public.alpha_hunter_paper_completed_trades_valid_v05 c
  join public.alpha_hunter_paper_exit_fills_v04 x
    on x.exit_fill_id=c.exit_fill_id
  join public.alpha_hunter_paper_protective_orders_v03 p
    on p.protective_order_id=x.triggered_protective_order_id
  join public.alpha_hunter_paper_exit_attempts_v04 a
    on a.entry_order_id=c.entry_order_id
   and a.source_run_id=c.exit_source_run_id
   and a.triggered_protection_type=x.protection_type
   and a.outcome in ('STOP_TRIGGERED','TARGET_TRIGGERED')
),
counterfactual as (
  select
    b.*,
    case
      when b.direction='LONG'
        then (
          b.trigger_anchored_exit_price-b.entry_average_fill_price
        )*b.quantity
      when b.direction='SHORT'
        then (
          b.entry_average_fill_price-b.trigger_anchored_exit_price
        )*b.quantity
      else null
    end as trigger_anchored_gross_pnl_usdt,
    b.trigger_anchored_exit_price*b.quantity*b.fee_bps/10000.0
      as trigger_anchored_exit_fee_usdt,
    abs(
      b.trigger_anchored_exit_price-b.protective_trigger_price
    )*b.quantity as trigger_anchored_slippage_cost_usdt
  from base b
),
economic as (
  select
    c.*,
    (
      c.trigger_anchored_gross_pnl_usdt
      - c.entry_costs_usdt
      - c.trigger_anchored_exit_fee_usdt
      - c.observed_spread_cost_usdt
      - c.trigger_anchored_slippage_cost_usdt
    ) as trigger_anchored_net_pnl_ex_funding
  from counterfactual c
)
select
  e.exit_fill_id,
  e.entry_order_id,
  e.decision_id,
  e.entry_decision_run_id,
  e.exit_source_run_id,
  e.symbol,
  e.direction,
  e.exit_reason,
  e.closed_at_utc,
  e.quantity,
  e.entry_average_fill_price,
  e.protective_trigger_price,
  e.observed_exit_price,
  e.trigger_anchored_exit_price,
  e.observed_net_pnl_ex_funding,
  e.trigger_anchored_net_pnl_ex_funding,
  e.planned_risk_usdt,
  e.observed_net_r_ex_funding,
  e.trigger_anchored_net_pnl_ex_funding/nullif(e.planned_risk_usdt,0)
    as trigger_anchored_net_r_ex_funding,
  (
    e.observed_net_r_ex_funding
    - e.trigger_anchored_net_pnl_ex_funding/nullif(e.planned_risk_usdt,0)
  ) as observation_delay_tax_r,
  (
    e.observed_exit_price-e.protective_trigger_price
  )/nullif(e.protective_trigger_price,0)*100.0
    as observed_exit_vs_trigger_pct,
  case
    when e.direction='LONG'
      then (
        e.protective_trigger_price-e.observed_exit_price
      )/nullif(e.protective_trigger_price,0)*100.0
    when e.direction='SHORT'
      then (
        e.observed_exit_price-e.protective_trigger_price
      )/nullif(e.protective_trigger_price,0)*100.0
    else null
  end as adverse_distance_from_trigger_pct,
  e.slippage_bps,
  e.fee_bps,
  e.entry_costs_usdt,
  e.observed_spread_cost_usdt,
  e.observed_slippage_cost_usdt,
  e.trigger_anchored_slippage_cost_usdt,
  e.observed_exit_costs_usdt,
  e.trigger_observed_at_utc,
  e.trigger_observed_best_bid,
  e.trigger_observed_best_ask,
  e.trigger_observed_quote_source,
  'OBSERVED_SPREAD_COST_REUSED_CONSERVATIVELY'::text
    as counterfactual_spread_assumption,
  true as counterfactual_only,
  false as profitability_claim_permitted,
  true as paper_only,
  false as exchange_authority,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from economic e;

revoke all on public.alpha_hunter_paper_exit_observation_delay_audit_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_exit_observation_delay_audit_v01
  to service_role;

create or replace view public.alpha_hunter_paper_exit_observation_delay_summary_v01
with (security_invoker=true,security_barrier=true)
as
select
  count(*)::integer as audited_valid_completed_trades,
  count(*) filter(where exit_reason='STOP_LOSS')::integer
    as stop_loss_trades,
  count(*) filter(where exit_reason='TAKE_PROFIT')::integer
    as take_profit_trades,
  avg(observed_net_r_ex_funding) as average_observed_net_r,
  avg(trigger_anchored_net_r_ex_funding) as average_trigger_anchored_net_r,
  sum(observation_delay_tax_r) as total_observation_delay_tax_r,
  avg(observation_delay_tax_r) as average_observation_delay_tax_r,
  max(abs(observation_delay_tax_r)) as maximum_absolute_observation_delay_tax_r,
  avg(adverse_distance_from_trigger_pct)
    as average_adverse_distance_from_trigger_pct,
  max(adverse_distance_from_trigger_pct)
    as maximum_adverse_distance_from_trigger_pct,
  true as counterfactual_only,
  false as profitability_claim_permitted,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_paper_exit_observation_delay_audit_v01;

revoke all on public.alpha_hunter_paper_exit_observation_delay_summary_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_exit_observation_delay_summary_v01
  to service_role;

commit;
