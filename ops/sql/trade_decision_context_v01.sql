-- Alpha Hunter manual/external trade decision-context audit v0.1
--
-- Purpose:
--   Separate Alpha Hunter strategy economics from manual/external account trades.
--   This is CONTEXT attribution, not causal attribution.
--
-- Freshness contract:
--   The production canonical scanner runs on an approximately 20-minute cadence.
--   A pre-entry signal is considered fresh here only when observed no more than
--   30 minutes before the trade/open-position observation.
--
-- Safety:
--   read-only analytics; no trade permission, no order path, no strategy mutation.

create or replace view public.alpha_hunter_trade_decision_context_v01
with (security_invoker=true,security_barrier=true)
as
select
  l.roundtrip_episode_id,
  l.symbol,
  l.direction as trade_direction,
  l.opened_or_first_seen_at_utc,
  l.closed_at_utc,
  l.fee_adjusted_pnl_ex_funding_usdt,
  l.currently_claimable_pnl_usdt,
  l.currently_claimable_pnl_basis,
  l.alpha_hunter_attribution_status,
  l.first_fill_enter_point_source,
  l.first_fill_time_utc,

  s.signal_id as preentry_signal_id,
  s.detected_at_utc as preentry_signal_detected_at_utc,
  case
    when s.detected_at_utc is null then null
    else extract(epoch from (
      l.opened_or_first_seen_at_utc-s.detected_at_utc
    ))/60.0
  end as preentry_signal_lag_minutes,
  s.state as preentry_signal_state,
  s.direction as preentry_signal_direction,
  s.trade_permission as preentry_signal_trade_permission,
  s.confidence_estimate_pct as preentry_signal_confidence_estimate_pct,
  s.reward_risk as preentry_signal_reward_risk,
  s.entry_price as preentry_signal_entry_price,
  s.stop_loss as preentry_signal_stop_loss,
  s.take_profit as preentry_signal_take_profit,
  s.payload->'decision_trace'->>'decision_stage'
    as preentry_decision_stage,
  s.payload->'decision_trace'->>'candidate_quality_status'
    as preentry_candidate_quality_status,
  s.payload->'decision_trace'->>'blocking_gate'
    as preentry_blocking_gate,
  s.payload->'decision_trace'->>'opportunity_timing'
    as preentry_opportunity_timing,
  case
    when lower(coalesce(
      s.payload->'decision_trace'->>'execution_permission',''
    )) in ('true','false')
      then (s.payload->'decision_trace'->>'execution_permission')::boolean
    when lower(coalesce(
      s.payload->'execution_setup'->>'permission',''
    )) in ('true','false')
      then (s.payload->'execution_setup'->>'permission')::boolean
    else s.trade_permission
  end as preentry_execution_permission,

  (
    s.signal_id is not null
    and s.detected_at_utc <= l.opened_or_first_seen_at_utc
    and l.opened_or_first_seen_at_utc-s.detected_at_utc
      <= interval '30 minutes'
  ) as fresh_preentry_signal_context,

  (
    s.signal_id is not null
    and upper(coalesce(s.direction,''))=upper(coalesce(l.direction,''))
  ) as direction_aligned_with_preentry_signal,

  case
    when l.alpha_hunter_attribution_status='ATTRIBUTABLE_TO_ALPHA_HUNTER'
      then 'ALPHA_HUNTER_EXECUTION_ATTRIBUTABLE'

    when s.signal_id is null
      or s.detected_at_utc > l.opened_or_first_seen_at_utc
      or l.opened_or_first_seen_at_utc-s.detected_at_utc
         > interval '30 minutes'
      then 'NO_FRESH_PREENTRY_SIGNAL_CONTEXT'

    when upper(coalesce(s.direction,''))
         <> upper(coalesce(l.direction,''))
      then 'NON_AH_CONTRARY_TO_FRESH_SIGNAL_DIRECTION'

    when upper(coalesce(s.direction,''))
         = upper(coalesce(l.direction,''))
      and (
        upper(coalesce(
          s.payload->'decision_trace'->>'decision_stage',''
        ))='REJECTED'
        or upper(coalesce(
          s.payload->'decision_trace'->>'candidate_quality_status',''
        ))='REJECT'
      )
      then 'NON_AH_ALIGNED_WITH_REJECTED_SIGNAL'

    when upper(coalesce(s.direction,''))
         = upper(coalesce(l.direction,''))
      and coalesce(
        case
          when lower(coalesce(
            s.payload->'decision_trace'->>'execution_permission',''
          )) in ('true','false')
            then (s.payload->'decision_trace'->>'execution_permission')::boolean
          when lower(coalesce(
            s.payload->'execution_setup'->>'permission',''
          )) in ('true','false')
            then (s.payload->'execution_setup'->>'permission')::boolean
          else s.trade_permission
        end,
        false
      )=false
      then 'NON_AH_ALIGNED_NONEXECUTABLE_SIGNAL'

    when upper(coalesce(s.direction,''))
         = upper(coalesce(l.direction,''))
      then 'NON_AH_ALIGNED_EXECUTABLE_SIGNAL_CONTEXT'

    else 'NON_AH_SIGNAL_CONTEXT_UNCLASSIFIED'
  end as decision_context_class,

  false as causal_attribution_claim_permitted,
  false as alpha_hunter_execution_claim_inferred_from_context,
  false as profitability_claim_permitted,
  false as strategy_change_permitted,
  false as trade_permission,
  'NONE'::text as order_path
from public.alpha_hunter_economic_trade_ledger_v01 l
left join lateral (
  select sig.*
  from public.alpha_hunter_signals sig
  where sig.symbol=l.symbol
    and sig.detected_at_utc <= l.opened_or_first_seen_at_utc
  order by sig.detected_at_utc desc,sig.signal_id desc
  limit 1
) s on true;


create or replace view public.alpha_hunter_trade_decision_context_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  decision_context_class,
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
  false as causal_attribution_claim_permitted,
  false as profitability_claim_permitted,
  false as strategy_change_permitted,
  false as trade_permission,
  'NONE'::text as order_path
from public.alpha_hunter_trade_decision_context_v01
group by decision_context_class;


create or replace view public.alpha_hunter_open_position_decision_context_v01
with (security_invoker=true,security_barrier=true)
as
with latest_position as (
  select distinct on (p.symbol,p.direction)
    p.position_snapshot_id,
    p.captured_at_utc,
    p.symbol,
    p.direction,
    p.quantity,
    p.average_entry,
    p.mark_price,
    p.unrealized_pnl_usdt,
    p.evidence->>'exchange_stop_loss_observed'
      as exchange_stop_loss_observed,
    p.evidence->>'exchange_take_profit_observed'
      as exchange_take_profit_observed
  from public.alpha_hunter_open_position_snapshots p
  join public.alpha_hunter_account_state_snapshots a
    on a.account_snapshot_id=p.account_snapshot_id
  where not exists (
    select 1
    from public.alpha_hunter_account_state_snapshots newer
    where newer.source=a.source
      and newer.captured_at_utc>a.captured_at_utc
  )
  order by p.symbol,p.direction,p.captured_at_utc desc,p.position_snapshot_id desc
)
select
  p.*,
  s.signal_id as latest_signal_id,
  s.detected_at_utc as latest_signal_detected_at_utc,
  case
    when s.detected_at_utc is null then null
    else extract(epoch from (
      p.captured_at_utc-s.detected_at_utc
    ))/60.0
  end as signal_lag_minutes,
  s.state as latest_signal_state,
  s.direction as latest_signal_direction,
  s.trade_permission as latest_signal_trade_permission,
  s.payload->'decision_trace'->>'decision_stage'
    as latest_decision_stage,
  s.payload->'decision_trace'->>'candidate_quality_status'
    as latest_candidate_quality_status,
  s.payload->'decision_trace'->>'blocking_gate'
    as latest_blocking_gate,
  (
    s.signal_id is not null
    and p.captured_at_utc-s.detected_at_utc <= interval '30 minutes'
  ) as fresh_signal_context,
  (
    s.signal_id is not null
    and upper(coalesce(s.direction,''))=upper(coalesce(p.direction,''))
  ) as direction_aligned_with_signal,
  case
    when s.signal_id is null
      or p.captured_at_utc-s.detected_at_utc > interval '30 minutes'
      then 'NO_FRESH_SIGNAL_CONTEXT'
    when upper(coalesce(s.direction,''))
         <> upper(coalesce(p.direction,''))
      then 'OPEN_POSITION_CONTRARY_TO_FRESH_SIGNAL_DIRECTION'
    when upper(coalesce(
      s.payload->'decision_trace'->>'decision_stage',''
    ))='REJECTED'
      or upper(coalesce(
        s.payload->'decision_trace'->>'candidate_quality_status',''
      ))='REJECT'
      then 'OPEN_POSITION_ALIGNED_WITH_REJECTED_SIGNAL'
    else 'OPEN_POSITION_ALIGNED_WITH_SIGNAL_CONTEXT'
  end as open_position_context_class,
  false as causal_attribution_claim_permitted,
  false as strategy_change_permitted,
  false as trade_permission,
  'NONE'::text as order_path
from latest_position p
left join lateral (
  select sig.*
  from public.alpha_hunter_signals sig
  where sig.symbol=p.symbol
    and sig.detected_at_utc<=p.captured_at_utc
  order by sig.detected_at_utc desc,sig.signal_id desc
  limit 1
) s on true;


revoke all on public.alpha_hunter_trade_decision_context_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_trade_decision_context_status_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_open_position_decision_context_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_trade_decision_context_v01
  to service_role;
grant select on public.alpha_hunter_trade_decision_context_status_v01
  to service_role;
grant select on public.alpha_hunter_open_position_decision_context_v01
  to service_role;
