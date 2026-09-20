-- Alpha Hunter account-observed realized fee evidence v0.1
--
-- Purpose:
--   Derive descriptive, account-observed fee-rate evidence from immutable
--   canonical Bitget fill rows. This does NOT activate a cost model, infer
--   slippage, authorize realistic net-R, or grant execution permission.
--
-- Evidence boundary:
--   Only fills with complete cost fields, positive quote volume, a non-null fee,
--   and USDT fee denomination are eligible for realized fee-bps calculation.
--   Fee sign is not interpreted as direction; absolute fee amount is used.
--
-- Scientific boundary:
--   These views are descriptive fee evidence only. They may support a future
--   preregistered cost-model validation, but cannot independently validate or
--   activate a production cost model.

create or replace view public.alpha_hunter_realized_fee_observations_v01
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
  f.position_mode,
  f.trade_scope,
  f.price,
  f.base_volume,
  f.quote_volume,
  f.fee_amount,
  f.fee_coin,
  f.cost_fields_complete,
  case
    when f.cost_fields_complete=true
      and f.quote_volume is not null
      and f.quote_volume>0
      and f.fee_amount is not null
      and upper(coalesce(f.fee_coin,''))='USDT'
    then abs(f.fee_amount)/f.quote_volume*10000.0
  end as realized_fee_bps,
  case
    when f.cost_fields_complete is not true then 'COST_FIELDS_INCOMPLETE'
    when f.quote_volume is null or f.quote_volume<=0 then 'QUOTE_VOLUME_INVALID'
    when f.fee_amount is null then 'FEE_AMOUNT_MISSING'
    when upper(coalesce(f.fee_coin,''))<>'USDT' then 'NON_USDT_FEE_DENOMINATION'
    when upper(coalesce(f.trade_scope,''))='TAKER' then 'ACCOUNT_OBSERVED_TAKER_FEE'
    when upper(coalesce(f.trade_scope,''))='MAKER' then 'ACCOUNT_OBSERVED_MAKER_FEE'
    else 'ACCOUNT_OBSERVED_FEE_SCOPE_OTHER'
  end as fee_evidence_class,
  'DESCRIPTIVE_ACCOUNT_OBSERVED_FEE_ONLY'::text as scientific_role,
  false as cost_model_validated,
  false as cost_model_activation_permitted,
  false as slippage_inference_permitted,
  false as realistic_net_r_claim_permitted,
  f.shadow_only,
  f.trade_permission
from public.alpha_hunter_fill_evidence f;


create or replace view public.alpha_hunter_realized_fee_status_v01
with (security_invoker=true,security_barrier=true)
as
with eligible as (
  select *
  from public.alpha_hunter_realized_fee_observations_v01
  where realized_fee_bps is not null
)
select
  trade_scope,
  fee_coin,
  count(*)::bigint as observed_fill_count,
  count(distinct symbol)::bigint as distinct_symbols,
  min(fill_time_utc) as first_fill_time_utc,
  max(fill_time_utc) as last_fill_time_utc,
  min(realized_fee_bps) as min_realized_fee_bps,
  percentile_cont(0.5) within group(order by realized_fee_bps) as median_realized_fee_bps,
  max(realized_fee_bps) as max_realized_fee_bps,
  stddev_pop(realized_fee_bps) as realized_fee_bps_stddev,
  avg(realized_fee_bps) as mean_realized_fee_bps,
  'DESCRIPTIVE_ONLY_NOT_A_VALIDATED_COST_MODEL'::text as scientific_status,
  'REQUIRES_SEPARATE_SLIPPAGE_AND_OUTCOME_VALIDATION'::text as next_gate,
  false as cost_model_validated,
  false as cost_model_activation_permitted,
  false as realistic_net_r_claim_permitted,
  true as shadow_only,
  false as trade_permission
from eligible
group by trade_scope,fee_coin;

revoke all on public.alpha_hunter_realized_fee_observations_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_realized_fee_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_realized_fee_observations_v01
  to service_role;
grant select on public.alpha_hunter_realized_fee_status_v01
  to service_role;
