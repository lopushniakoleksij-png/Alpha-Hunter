-- Alpha Hunter execution cost floor status v0.1
--
-- Purpose:
--   Expose a descriptive, observed lower-bound execution-friction surface from
--   contemporaneous scanner bid/ask snapshots plus realized account fee evidence.
--
-- Claim ceiling:
--   This is NOT a validated slippage model, NOT a realistic net-R model, and
--   NOT Alpha Hunter execution-performance evidence. External/human fills are
--   used only to measure realized fee rates.
--
-- Taker floor assumption:
--   two observed taker fees + one round-trip spread crossing
--   (two half-spread crossings). Slippage beyond top-of-book, latency, market
--   impact, adverse selection, funding, and fill probability are excluded.

create or replace view public.alpha_hunter_execution_cost_floor_status_v01
with (security_invoker=true,security_barrier=true)
as
with fee as (
  select
    max(median_realized_fee_bps) filter(where trade_scope='MAKER') as maker_fee_bps,
    max(median_realized_fee_bps) filter(where trade_scope='TAKER') as taker_fee_bps,
    sum(observed_fill_count) filter(where trade_scope='MAKER') as maker_fee_fill_count,
    sum(observed_fill_count) filter(where trade_scope='TAKER') as taker_fee_fill_count
  from public.alpha_hunter_realized_fee_status_v01
),
base as (
  select
    coalesce(liquidity_state,'UNKNOWN') as liquidity_state,
    captured_at_utc,
    bid_price,ask_price,mid_price,observed_spread_abs,observed_spread_pct,
    funding_rate,quote_volume_24h,
    case
      when bid_price is not null and ask_price is not null
       and bid_price>0 and ask_price>=bid_price and mid_price>0
      then true else false
    end as valid_quote,
    case
      when mid_price>0 and observed_spread_pct is not null
      then abs(observed_spread_pct-(observed_spread_abs/mid_price*100.0))
    end as spread_pct_reconstruction_abs_diff
  from public.alpha_hunter_execution_cost_evidence
),
scopes as (
  select liquidity_state as cost_scope,* from base
  union all
  select 'ALL'::text as cost_scope,* from base
),
agg as (
  select
    cost_scope,
    count(*)::bigint as snapshot_rows,
    min(captured_at_utc) as first_snapshot_at_utc,
    max(captured_at_utc) as last_snapshot_at_utc,
    count(*) filter(where valid_quote)::bigint as valid_quote_rows,
    count(*) filter(where funding_rate is not null)::bigint as funding_observed_rows,
    count(*) filter(where quote_volume_24h is not null)::bigint as volume_observed_rows,
    count(*) filter(
      where spread_pct_reconstruction_abs_diff is not null
        and spread_pct_reconstruction_abs_diff<=0.01
    )::bigint as spread_reconstruction_consistent_rows,
    percentile_cont(0.5) within group(order by observed_spread_pct) * 100.0
      as median_spread_bps,
    percentile_cont(0.9) within group(order by observed_spread_pct) * 100.0
      as p90_spread_bps,
    percentile_cont(0.95) within group(order by observed_spread_pct) * 100.0
      as p95_spread_bps
  from scopes
  where observed_spread_pct is not null and observed_spread_pct>=0
  group by cost_scope
)
select
  a.cost_scope,
  a.snapshot_rows,
  a.first_snapshot_at_utc,
  a.last_snapshot_at_utc,
  a.valid_quote_rows,
  a.funding_observed_rows,
  a.volume_observed_rows,
  a.spread_reconstruction_consistent_rows,
  case when a.snapshot_rows>0 then 100.0*a.valid_quote_rows/a.snapshot_rows end
    as valid_quote_pct,
  case when a.snapshot_rows>0 then
    100.0*a.spread_reconstruction_consistent_rows/a.snapshot_rows
  end as spread_reconstruction_consistent_pct,
  a.median_spread_bps,
  a.p90_spread_bps,
  a.p95_spread_bps,
  f.maker_fee_bps as observed_maker_fee_bps,
  f.taker_fee_bps as observed_taker_fee_bps,
  f.maker_fee_fill_count,
  f.taker_fee_fill_count,
  case when f.taker_fee_bps is not null then 2.0*f.taker_fee_bps end
    as taker_round_trip_fee_bps,
  case when f.taker_fee_bps is not null then
    2.0*f.taker_fee_bps+a.median_spread_bps
  end as observable_taker_round_trip_floor_median_bps,
  case when f.taker_fee_bps is not null then
    2.0*f.taker_fee_bps+a.p90_spread_bps
  end as observable_taker_round_trip_floor_p90_bps,
  case when f.taker_fee_bps is not null then
    2.0*f.taker_fee_bps+a.p95_spread_bps
  end as observable_taker_round_trip_floor_p95_bps,
  'TWO_TAKER_FEES_PLUS_ONE_ROUND_TRIP_SPREAD_CROSSING'::text
    as floor_assumption,
  false as slippage_included,
  false as latency_included,
  false as market_impact_included,
  false as funding_included,
  false as adverse_selection_included,
  false as cost_model_validated,
  false as cost_model_activation_permitted,
  false as realistic_net_r_claim_permitted,
  'DESCRIPTIVE_OBSERVED_COST_FLOOR_ONLY'::text as scientific_status,
  'FORWARD_DECISION_TO_FILL_BENCHMARK_AND_SLIPPAGE_VALIDATION'::text
    as next_gate,
  true as shadow_only,
  false as trade_permission,
  'execution-cost-floor-status-v0.1'::text as model_version
from agg a
cross join fee f;

revoke all on public.alpha_hunter_execution_cost_floor_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_execution_cost_floor_status_v01
  to service_role;
