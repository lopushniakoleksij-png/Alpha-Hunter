-- Alpha Hunter round-trip outcome evidence v0.1
--
-- Purpose:
--   Reconstruct flat-to-flat hedge-mode position episodes from immutable
--   canonical Bitget fill evidence. This is descriptive historical account
--   evidence only.
--
-- Exchange semantics validated against recovered fills:
--   hedge_mode + side=BUY  => LONG position side
--   hedge_mode + side=SELL => SHORT position side
--   trade_side=OPEN        => inventory increases
--   trade_side=CLOSE       => inventory decreases
--
-- Claim ceiling:
--   * Bitget fill "profit" is preserved as the exchange profit field.
--   * Signed fill fees are summed separately.
--   * profit + signed fees is labeled fee-adjusted EXCLUDING funding/other bills.
--   * Full economic net PnL is prohibited until account-bill cashflows are bound.
--   * Manual iOS / exchange SYS fills are not Alpha Hunter executions.

create or replace view public.alpha_hunter_roundtrip_order_events_v01
with (security_invoker=true,security_barrier=true)
as
select
  f.symbol,
  case
    when f.side='BUY' then 'LONG'
    when f.side='SELL' then 'SHORT'
  end as direction,
  f.trade_side,
  encode(
    extensions.digest(f.order_id,'sha256'),
    'hex'
  ) as order_identity_sha256,
  min(f.fill_time_utc) as event_at_utc,
  sum(f.base_volume) as base_qty,
  sum(f.quote_volume) as quote_volume,
  sum(f.price*f.base_volume)/nullif(sum(f.base_volume),0) as vwap_price,
  sum(coalesce(f.profit,0)) as profit_field_sum,
  sum(coalesce(f.fee_amount,0)) as signed_fee_sum,
  count(*)::bigint as constituent_fill_count,
  array_agg(
    distinct coalesce(f.enter_point_source,'<NULL>')
    order by coalesce(f.enter_point_source,'<NULL>')
  ) as origin_set,
  bool_or(lower(coalesce(f.enter_point_source,''))='ios')
    as contains_ios_origin,
  bool_or(lower(coalesce(f.enter_point_source,''))='sys')
    as contains_sys_origin,
  bool_or(lower(coalesce(f.enter_point_source,''))='api')
    as contains_api_origin,
  bool_or(
    lower(coalesce(f.enter_point_source,'')) not in ('ios','sys','api')
  ) as contains_other_origin,
  bool_or(nullif(trim(coalesce(f.enter_point_source,'')),'') is null)
    as contains_unknown_origin,
  true as shadow_only,
  false as trade_permission
from public.alpha_hunter_fill_evidence f
where f.position_mode='hedge_mode'
  and f.side in ('BUY','SELL')
  and f.trade_side in ('OPEN','CLOSE')
group by
  f.symbol,
  f.side,
  f.trade_side,
  f.order_id;


create or replace view public.alpha_hunter_roundtrip_episodes_v01
with (security_invoker=true,security_barrier=true)
as
with running as (
  select
    e.*,
    case
      when e.trade_side='OPEN' then e.base_qty
      else -e.base_qty
    end as inventory_delta,
    sum(
      case
        when e.trade_side='OPEN' then e.base_qty
        else -e.base_qty
      end
    ) over (
      partition by e.symbol,e.direction
      order by e.event_at_utc,e.order_identity_sha256
      rows between unbounded preceding and current row
    ) as running_inventory
  from public.alpha_hunter_roundtrip_order_events_v01 e
),
lagged as (
  select
    r.*,
    lag(r.running_inventory,1,0.0) over (
      partition by r.symbol,r.direction
      order by r.event_at_utc,r.order_identity_sha256
    ) as previous_running_inventory
  from running r
),
segmented as (
  select
    l.*,
    sum(
      case
        when l.trade_side='OPEN'
          and abs(l.previous_running_inventory)<=1e-8
        then 1
        else 0
      end
    ) over (
      partition by l.symbol,l.direction
      order by l.event_at_utc,l.order_identity_sha256
      rows between unbounded preceding and current row
    ) as episode_no
  from lagged l
),
episode_rollup as (
  select
    s.symbol,
    s.direction,
    s.episode_no,
    min(s.event_at_utc) as opened_or_first_seen_at_utc,
    max(s.event_at_utc) as closed_or_last_seen_at_utc,
    count(*)::bigint as order_event_count,
    sum(s.constituent_fill_count)::bigint as constituent_fill_count,
    count(*) filter(where s.trade_side='OPEN')::bigint as open_order_count,
    count(*) filter(where s.trade_side='CLOSE')::bigint as close_order_count,
    sum(case when s.trade_side='OPEN' then s.base_qty else 0 end)
      as opened_qty,
    sum(case when s.trade_side='CLOSE' then s.base_qty else 0 end)
      as closed_qty,
    min(s.running_inventory) as min_running_inventory,
    max(s.running_inventory) as max_running_inventory,
    sum(s.profit_field_sum) as profit_field_sum,
    sum(s.signed_fee_sum) as signed_trading_fee_sum,
    sum(s.profit_field_sum)+sum(s.signed_fee_sum)
      as fee_adjusted_profit_ex_funding,
    sum(s.quote_volume) as total_turnover_quote,
    sum(s.vwap_price*s.base_qty)
      filter(where s.trade_side='OPEN')
      /nullif(sum(s.base_qty) filter(where s.trade_side='OPEN'),0)
      as opening_vwap,
    sum(s.vwap_price*s.base_qty)
      filter(where s.trade_side='CLOSE')
      /nullif(sum(s.base_qty) filter(where s.trade_side='CLOSE'),0)
      as closing_vwap,
    array_remove(
      array[
        case when bool_or(s.contains_ios_origin) then 'ios' end,
        case when bool_or(s.contains_sys_origin) then 'sys' end,
        case when bool_or(s.contains_api_origin) then 'api' end,
        case when bool_or(s.contains_other_origin) then 'other' end,
        case when bool_or(s.contains_unknown_origin) then 'unknown' end
      ],
      null
    ) as origin_set,
    bool_or(s.contains_ios_origin) as contains_ios_origin,
    bool_or(s.contains_sys_origin) as contains_sys_origin,
    bool_or(s.contains_api_origin) as contains_api_origin,
    bool_or(s.contains_other_origin) as contains_other_origin,
    bool_or(s.contains_unknown_origin) as contains_unknown_origin
  from segmented s
  group by
    s.symbol,
    s.direction,
    s.episode_no
),
classified as (
  select
    e.*,
    greatest(1e-9,abs(e.opened_qty)*1e-8) as quantity_tolerance,
    case
      when e.episode_no=0 then 'PREWINDOW_POSITION_REQUIRED'
      when e.min_running_inventory
        < -greatest(1e-9,abs(e.opened_qty)*1e-8)
        then 'INVENTORY_NEGATIVE'
      when abs(e.opened_qty-e.closed_qty)
        <= greatest(1e-9,abs(e.opened_qty)*1e-8)
        then 'COMPLETE_FLAT_TO_FLAT'
      else 'OPEN_OR_INCOMPLETE'
    end as reconstruction_status
  from episode_rollup e
)
select
  encode(
    extensions.digest(
      concat_ws(
        '|',
        'roundtrip-outcome-v0.1',
        c.symbol,
        c.direction,
        c.episode_no::text,
        c.opened_or_first_seen_at_utc::text
      ),
      'sha256'
    ),
    'hex'
  ) as roundtrip_episode_id,
  c.symbol,
  c.direction,
  c.episode_no,
  c.reconstruction_status,
  c.opened_or_first_seen_at_utc,
  case
    when c.reconstruction_status='COMPLETE_FLAT_TO_FLAT'
    then c.closed_or_last_seen_at_utc
  end as closed_at_utc,
  c.closed_or_last_seen_at_utc,
  c.order_event_count,
  c.constituent_fill_count,
  c.open_order_count,
  c.close_order_count,
  c.opened_qty,
  c.closed_qty,
  c.quantity_tolerance,
  c.min_running_inventory,
  c.max_running_inventory,
  c.opening_vwap,
  c.closing_vwap,
  c.total_turnover_quote,
  c.profit_field_sum,
  c.signed_trading_fee_sum,
  c.fee_adjusted_profit_ex_funding,
  case
    when c.reconstruction_status<>'COMPLETE_FLAT_TO_FLAT'
      then 'INCOMPLETE'
    when c.profit_field_sum>0 then 'PROFIT_POSITIVE'
    when c.profit_field_sum<0 then 'PROFIT_NEGATIVE'
    else 'PROFIT_FLAT'
  end as exchange_profit_class,
  c.origin_set,
  c.contains_ios_origin,
  c.contains_sys_origin,
  c.contains_api_origin,
  c.contains_other_origin,
  c.contains_unknown_origin,
  false as verified_alpha_hunter_execution,
  false as alpha_hunter_execution_claim_permitted,
  false as funding_bound,
  false as full_economic_pnl_claim_permitted,
  false as realistic_net_r_claim_permitted,
  'DESCRIPTIVE_FLAT_TO_FLAT_ACCOUNT_OUTCOME_EX_FUNDING'::text
    as scientific_role,
  'roundtrip-outcome-v0.1'::text as model_version,
  true as shadow_only,
  false as trade_permission
from classified c;


create or replace view public.alpha_hunter_roundtrip_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  count(*)::bigint as episode_rows,
  count(*) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
  )::bigint as complete_flat_to_flat_episodes,
  count(*) filter(
    where reconstruction_status<>'COMPLETE_FLAT_TO_FLAT'
  )::bigint as incomplete_episodes,
  count(*) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
      and exchange_profit_class='PROFIT_POSITIVE'
  )::bigint as profit_positive_episodes,
  count(*) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
      and exchange_profit_class='PROFIT_NEGATIVE'
  )::bigint as profit_negative_episodes,
  count(*) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
      and exchange_profit_class='PROFIT_FLAT'
  )::bigint as profit_flat_episodes,
  sum(profit_field_sum) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
  ) as total_profit_field_sum,
  sum(signed_trading_fee_sum) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
  ) as total_signed_trading_fee_sum,
  sum(fee_adjusted_profit_ex_funding) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
  ) as total_fee_adjusted_profit_ex_funding,
  min(opened_or_first_seen_at_utc) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
  ) as first_complete_episode_opened_at_utc,
  max(closed_at_utc) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
  ) as last_complete_episode_closed_at_utc,
  count(*) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
      and contains_sys_origin
  )::bigint as complete_episodes_with_sys_origin,
  count(*) filter(
    where reconstruction_status='COMPLETE_FLAT_TO_FLAT'
      and contains_api_origin
  )::bigint as complete_episodes_with_api_origin,
  false as funding_bound,
  false as full_economic_pnl_claim_permitted,
  false as alpha_hunter_execution_claim_permitted,
  'FEE_ADJUSTED_ONLY_FUNDING_AND_OTHER_BILLS_NOT_BOUND'::text
    as claim_ceiling,
  true as shadow_only,
  false as trade_permission
from public.alpha_hunter_roundtrip_episodes_v01;


revoke all on public.alpha_hunter_roundtrip_order_events_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_roundtrip_episodes_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_roundtrip_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_roundtrip_order_events_v01
  to service_role;
grant select on public.alpha_hunter_roundtrip_episodes_v01
  to service_role;
grant select on public.alpha_hunter_roundtrip_status_v01
  to service_role;
