-- Alpha Hunter profit-retention lifecycle audit v0.1
-- Descriptive/shadow-only measurement of how much observed open-position MFE
-- was retained at a completed flat-to-flat exit.
--
-- This view does NOT change stops, targets, leverage, orders, or trade permission.
-- It uses sampled canonical position snapshots, so "peak" means observed peak,
-- not guaranteed tick-level maximum favorable excursion.

create or replace view public.alpha_hunter_profit_retention_lifecycle_v01
with (security_invoker=true,security_barrier=true)
as
select
  r.roundtrip_episode_id,
  r.symbol,
  r.direction,
  r.opened_or_first_seen_at_utc,
  r.closed_at_utc,
  r.opening_vwap,
  r.closing_vwap,
  r.opened_qty,

  peak.captured_at_utc as observed_peak_at_utc,
  peak.mark_price as observed_peak_mark_price,
  peak.unrealized_pnl_usdt as observed_peak_unrealized_pnl_usdt,

  last_pos.captured_at_utc as last_position_observed_at_utc,
  last_pos.mark_price as last_position_mark_price,
  last_pos.stop_loss_observed as last_stop_loss_observed,
  last_pos.take_profit_observed as last_take_profit_observed,

  r.profit_field_sum as gross_realized_profit_field,
  r.signed_trading_fee_sum,
  r.fee_adjusted_profit_ex_funding,
  r.bound_funding_bill_count,
  r.bound_funding_account_effect,
  r.economic_pnl_after_fees_and_bound_funding,
  r.funding_coverage_complete,
  r.funding_coverage_status,
  r.full_economic_pnl_claim_permitted,

  case
    when peak.unrealized_pnl_usdt is null then null
    when peak.unrealized_pnl_usdt <= 0 then null
    else 100.0 * r.profit_field_sum / peak.unrealized_pnl_usdt
  end as observed_peak_gross_capture_pct,

  case
    when peak.unrealized_pnl_usdt is null then null
    when peak.unrealized_pnl_usdt <= 0 then null
    else 100.0 * (
      peak.unrealized_pnl_usdt - r.profit_field_sum
    ) / peak.unrealized_pnl_usdt
  end as observed_peak_gross_giveback_pct,

  case
    when peak.unrealized_pnl_usdt is null then null
    when peak.unrealized_pnl_usdt <= 0 then null
    else 100.0 * (
      r.fee_adjusted_profit_ex_funding
      / peak.unrealized_pnl_usdt
    )
  end as observed_peak_fee_adjusted_capture_pct_ex_funding,

  case
    when last_pos.stop_loss_numeric is null
      or r.closing_vwap is null
      or last_pos.stop_loss_numeric = 0
      then null
    when r.direction='LONG'
      then 10000.0 * (
        last_pos.stop_loss_numeric - r.closing_vwap
      ) / last_pos.stop_loss_numeric
    when r.direction='SHORT'
      then 10000.0 * (
        r.closing_vwap - last_pos.stop_loss_numeric
      ) / last_pos.stop_loss_numeric
    else null
  end as exit_vs_last_stop_adverse_bps,

  case
    when peak.mark_price is null
      or peak.stop_loss_numeric is null
      or peak.mark_price = 0
      then null
    when r.direction='LONG'
      then 100.0 * (
        peak.mark_price - peak.stop_loss_numeric
      ) / peak.mark_price
    when r.direction='SHORT'
      then 100.0 * (
        peak.stop_loss_numeric - peak.mark_price
      ) / peak.mark_price
    else null
  end as observed_peak_to_stop_distance_pct,

  case
    when peak.position_snapshot_id is null then 'NO_POSITION_SNAPSHOTS'
    when peak.unrealized_pnl_usdt is null then 'PEAK_PNL_UNAVAILABLE'
    when peak.unrealized_pnl_usdt <= 0 then 'NO_POSITIVE_OBSERVED_MFE'
    else 'MEASURED'
  end as retention_evidence_status,

  r.verified_alpha_hunter_execution,
  r.alpha_hunter_execution_claim_permitted,
  false as management_change_permitted,
  false as stop_change_permitted,
  false as target_change_permitted,
  'DESCRIPTIVE_OBSERVED_MFE_RETENTION_AUDIT'::text as scientific_role,
  'profit-retention-lifecycle-v0.1'::text as model_version,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path

from public.alpha_hunter_roundtrip_economic_outcome_v01 r

left join lateral (
  select
    p.position_snapshot_id,
    p.captured_at_utc,
    p.mark_price,
    p.unrealized_pnl_usdt,
    case
      when coalesce(p.evidence->>'exchange_stop_loss_observed','')
        ~ '^[+-]?[0-9]+([.][0-9]+)?$'
      then (p.evidence->>'exchange_stop_loss_observed')::double precision
      else null
    end as stop_loss_numeric
  from public.alpha_hunter_open_position_snapshots p
  where p.symbol=r.symbol
    and p.direction=r.direction
    and p.captured_at_utc >= r.opened_or_first_seen_at_utc
    and r.closed_at_utc is not null
    and p.captured_at_utc <= r.closed_at_utc
  order by p.unrealized_pnl_usdt desc nulls last,p.captured_at_utc desc
  limit 1
) peak on true

left join lateral (
  select
    p.captured_at_utc,
    p.mark_price,
    p.evidence->>'exchange_stop_loss_observed' as stop_loss_observed,
    p.evidence->>'exchange_take_profit_observed' as take_profit_observed,
    case
      when coalesce(p.evidence->>'exchange_stop_loss_observed','')
        ~ '^[+-]?[0-9]+([.][0-9]+)?$'
      then (p.evidence->>'exchange_stop_loss_observed')::double precision
      else null
    end as stop_loss_numeric
  from public.alpha_hunter_open_position_snapshots p
  where p.symbol=r.symbol
    and p.direction=r.direction
    and p.captured_at_utc >= r.opened_or_first_seen_at_utc
    and r.closed_at_utc is not null
    and p.captured_at_utc <= r.closed_at_utc
  order by p.captured_at_utc desc
  limit 1
) last_pos on true

where r.closed_at_utc is not null;


create or replace view public.alpha_hunter_profit_retention_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  count(*)::bigint as completed_episode_rows,
  count(*) filter(
    where retention_evidence_status='MEASURED'
  )::bigint as measured_positive_mfe_rows,
  avg(observed_peak_gross_capture_pct) filter(
    where retention_evidence_status='MEASURED'
  ) as average_observed_peak_gross_capture_pct,
  avg(observed_peak_gross_giveback_pct) filter(
    where retention_evidence_status='MEASURED'
  ) as average_observed_peak_gross_giveback_pct,
  avg(exit_vs_last_stop_adverse_bps) filter(
    where retention_evidence_status='MEASURED'
      and exit_vs_last_stop_adverse_bps is not null
  ) as average_exit_vs_last_stop_adverse_bps,
  false as management_change_permitted,
  false as stop_change_permitted,
  false as target_change_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from public.alpha_hunter_profit_retention_lifecycle_v01;


revoke all on public.alpha_hunter_profit_retention_lifecycle_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_profit_retention_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_profit_retention_lifecycle_v01
  to service_role;
grant select on public.alpha_hunter_profit_retention_status_v01
  to service_role;
