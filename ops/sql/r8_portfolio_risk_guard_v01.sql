begin;

-- R8 portfolio-risk observability v0.1.
-- Read-only guard for active filled/protected R8 paper positions.
-- This does not alter paper admission, strategy logic, scientific identity,
-- per-trade sizing, cadence, trade permission, promotion, or exchange paths.

create or replace view public.alpha_hunter_r8_portfolio_risk_guard_v01
with (security_invoker=true,security_barrier=true)
as
with active as (
  select
    a.order_id,
    a.decision_id,
    a.symbol,
    a.strategy_id,
    a.direction,
    a.exposure_started_at_utc,
    o.virtual_equity_usdt,
    o.planned_risk_usdt
  from public.alpha_hunter_paper_active_exposure_members_v08 a
  join public.alpha_hunter_paper_orders_v02 o
    on o.order_id=a.order_id
  where a.exposure_state='FILLED_PROTECTED_POSITION'
),
policy as (
  select
    count(*) filter(
      where status='ACTIVE'
        and validated_at_utc is not null
        and activated_at_utc is not null
    )::integer as active_validated_policy_count,
    max(risk_policy_id) filter(
      where status='ACTIVE'
        and validated_at_utc is not null
        and activated_at_utc is not null
    ) as active_validated_risk_policy_id,
    max(created_at) as latest_policy_recorded_at_utc
  from public.alpha_hunter_risk_policy_versions
),
summary as (
  select
    count(*)::integer as active_positions,
    count(*) filter(where direction='LONG')::integer as long_positions,
    count(*) filter(where direction='SHORT')::integer as short_positions,
    count(distinct symbol)::integer as distinct_symbols,
    coalesce(sum(planned_risk_usdt),0)::numeric as aggregate_planned_risk_usdt,
    max(virtual_equity_usdt)::numeric as virtual_equity_usdt,
    coalesce(
      100.0*sum(planned_risk_usdt)/nullif(max(virtual_equity_usdt),0),
      0
    )::numeric as aggregate_planned_risk_pct,
    coalesce(max(symbol_count),0)::integer as maximum_positions_same_symbol
  from (
    select a.*, count(*) over(partition by symbol) as symbol_count
    from active a
  ) x
)
select
  clock_timestamp() as checked_at_utc,
  s.active_positions,
  s.long_positions,
  s.short_positions,
  s.distinct_symbols,
  s.aggregate_planned_risk_usdt,
  s.virtual_equity_usdt,
  round(s.aggregate_planned_risk_pct,4) as aggregate_planned_risk_pct,
  s.maximum_positions_same_symbol,
  p.active_validated_policy_count,
  p.active_validated_risk_policy_id,
  case
    when p.active_validated_policy_count=0
      then 'NO_ACTIVE_VALIDATED_RISK_POLICY'
    when p.active_validated_policy_count=1
      then 'ACTIVE_VALIDATED_RISK_POLICY_PRESENT'
    else 'MULTIPLE_ACTIVE_VALIDATED_RISK_POLICIES'
  end as risk_policy_status,
  case
    when p.active_validated_policy_count=0
      then 'LIVE_READINESS_BLOCKED_NO_VALIDATED_RISK_POLICY'
    when p.active_validated_policy_count>1
      then 'LIVE_READINESS_BLOCKED_POLICY_AMBIGUITY'
    else 'PORTFOLIO_POLICY_LAYER_PRESENT'
  end as live_readiness_status,
  case
    when s.active_positions=0 then 'NO_ACTIVE_PAPER_POSITIONS'
    when s.long_positions=s.active_positions then 'ALL_LONG'
    when s.short_positions=s.active_positions then 'ALL_SHORT'
    else 'MIXED_DIRECTION'
  end as direction_concentration,
  p.latest_policy_recorded_at_utc,
  true as observation_only,
  true as paper_only,
  false as exchange_authority,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from summary s
cross join policy p;

revoke all on public.alpha_hunter_r8_portfolio_risk_guard_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r8_portfolio_risk_guard_v01
  to service_role;

commit;
