begin;

-- Alpha Hunter verified execution slippage readiness v0.1.
--
-- Purpose:
--   Measure the real prospective frozen-decision -> exact Bitget fill sample
--   without promoting it into a validated cost model.
--
-- Pre-registered calibration floors for REVIEW readiness:
--   total verified executions >= 30
--   verified TAKER executions >= 20
--   verified MAKER executions >= 10
--   LONG and SHORT executions >= 5 each
--   all sample rows have arrival slippage and realized fee measurements
--
-- These floors do NOT validate or activate a cost model. Full validation still
-- requires exit slippage, adverse-selection/post-fill markouts, funding path,
-- missing-data policy and out-of-sample replication.

create or replace view public.alpha_hunter_verified_execution_slippage_status_v01
with (security_invoker=true,security_barrier=true)
as
with active as (
  select a.spec_id,a.started_at_utc
  from public.alpha_hunter_profitability_test_activations_v01 a
  order by a.started_at_utc desc,a.activated_at_utc desc
  limit 1
),
sample as (
  select v.*
  from public.alpha_hunter_verified_execution_attribution_v01 v
  join active a on a.spec_id=v.spec_id
  where v.verified_alpha_hunter_execution=true
    and v.frozen_at_utc>=a.started_at_utc
),
stats as (
  select
    count(*)::bigint as verified_execution_rows,
    count(*) filter(where upper(coalesce(trade_scope,''))='TAKER')::bigint
      as verified_taker_rows,
    count(*) filter(where upper(coalesce(trade_scope,''))='MAKER')::bigint
      as verified_maker_rows,
    count(*) filter(where direction='LONG')::bigint as verified_long_rows,
    count(*) filter(where direction='SHORT')::bigint as verified_short_rows,
    count(*) filter(where action='EXECUTE_NOW')::bigint
      as execute_now_rows,
    count(*) filter(where action='PLACE_LIMIT')::bigint
      as place_limit_rows,
    count(*) filter(where arrival_slippage_measured=true)::bigint
      as arrival_slippage_measured_rows,
    count(*) filter(where realized_fee_bps is not null)::bigint
      as realized_fee_measured_rows,
    min(frozen_at_utc) as first_verified_freeze_at_utc,
    max(frozen_at_utc) as latest_verified_freeze_at_utc,
    min(fill_time_utc) as first_verified_fill_at_utc,
    max(fill_time_utc) as latest_verified_fill_at_utc,

    avg(signed_adverse_arrival_to_fill_bps)
      filter(where signed_adverse_arrival_to_fill_bps is not null)
      as mean_signed_arrival_to_fill_bps,
    percentile_cont(0.5) within group(
      order by signed_adverse_arrival_to_fill_bps
    ) filter(where signed_adverse_arrival_to_fill_bps is not null)
      as median_signed_arrival_to_fill_bps,

    percentile_cont(0.5) within group(
      order by greatest(signed_adverse_arrival_to_fill_bps,0)
    ) filter(where signed_adverse_arrival_to_fill_bps is not null)
      as median_adverse_entry_slippage_bps,
    percentile_cont(0.9) within group(
      order by greatest(signed_adverse_arrival_to_fill_bps,0)
    ) filter(where signed_adverse_arrival_to_fill_bps is not null)
      as p90_adverse_entry_slippage_bps,
    percentile_cont(0.95) within group(
      order by greatest(signed_adverse_arrival_to_fill_bps,0)
    ) filter(where signed_adverse_arrival_to_fill_bps is not null)
      as p95_adverse_entry_slippage_bps,

    percentile_cont(0.5) within group(order by realized_fee_bps)
      filter(where realized_fee_bps is not null)
      as median_realized_fee_bps,
    percentile_cont(0.9) within group(order by realized_fee_bps)
      filter(where realized_fee_bps is not null)
      as p90_realized_fee_bps,

    percentile_cont(0.5) within group(order by freeze_to_order_seconds)
      filter(where freeze_to_order_seconds is not null)
      as median_freeze_to_order_seconds,
    percentile_cont(0.9) within group(order by freeze_to_order_seconds)
      filter(where freeze_to_order_seconds is not null)
      as p90_freeze_to_order_seconds,
    percentile_cont(0.5) within group(order by order_to_fill_seconds)
      filter(where order_to_fill_seconds is not null)
      as median_order_to_fill_seconds,
    percentile_cont(0.9) within group(order by order_to_fill_seconds)
      filter(where order_to_fill_seconds is not null)
      as p90_order_to_fill_seconds
  from sample
)
select
  a.spec_id,
  a.started_at_utc,
  s.*,

  30::integer as minimum_verified_execution_rows,
  20::integer as minimum_verified_taker_rows,
  10::integer as minimum_verified_maker_rows,
  5::integer as minimum_verified_long_rows,
  5::integer as minimum_verified_short_rows,

  (
    s.verified_execution_rows>=30
    and s.verified_taker_rows>=20
    and s.verified_maker_rows>=10
    and s.verified_long_rows>=5
    and s.verified_short_rows>=5
    and s.arrival_slippage_measured_rows=s.verified_execution_rows
    and s.realized_fee_measured_rows=s.verified_execution_rows
  ) as entry_slippage_calibration_sample_gate_met,

  0::bigint as verified_exit_slippage_rows,
  0::bigint as verified_post_fill_markout_rows,
  false as exit_slippage_sample_gate_met,
  false as adverse_selection_markout_gate_met,
  false as realized_funding_path_gate_met,
  false as missing_data_policy_frozen,
  false as out_of_sample_replication_gate_met,

  false as slippage_model_validated,
  false as cost_model_validated,
  false as cost_model_activation_permitted,
  false as realistic_net_r_claim_permitted,

  case
    when s.verified_execution_rows=0
      then 'WAITING_FOR_FIRST_EXPLICIT_CONFIRMED_REAL_EXECUTION'
    when s.verified_execution_rows<30
      then 'COLLECTING_VERIFIED_ENTRY_SLIPPAGE_SAMPLE'
    when s.verified_taker_rows<20
      then 'COLLECTING_TAKER_EXECUTION_SEGMENT'
    when s.verified_maker_rows<10
      then 'COLLECTING_MAKER_EXECUTION_SEGMENT'
    when s.verified_long_rows<5 or s.verified_short_rows<5
      then 'COLLECTING_DIRECTION_BALANCE'
    when s.arrival_slippage_measured_rows<>s.verified_execution_rows
      or s.realized_fee_measured_rows<>s.verified_execution_rows
      then 'ENTRY_SAMPLE_HAS_INCOMPLETE_COST_MEASUREMENTS'
    else 'ENTRY_SLIPPAGE_CALIBRATION_SAMPLE_READY_FULL_COST_PATH_INCOMPLETE'
  end as validation_status,

  case
    when s.verified_execution_rows=0
      then 'EXECUTE_A_FRESH_FROZEN_ALPHA_HUNTER_DECISION_AND_CONFIRM_EXACT_FILL'
    when not (
      s.verified_execution_rows>=30
      and s.verified_taker_rows>=20
      and s.verified_maker_rows>=10
      and s.verified_long_rows>=5
      and s.verified_short_rows>=5
      and s.arrival_slippage_measured_rows=s.verified_execution_rows
      and s.realized_fee_measured_rows=s.verified_execution_rows
    )
      then 'CONTINUE_EXPLICIT_VERIFIED_ENTRY_EXECUTION_SAMPLE'
    else 'CAPTURE_EXIT_SLIPPAGE_POST_FILL_MARKOUTS_FUNDING_AND_OOS_REPLICATION'
  end as next_gate,

  'ENTRY_CALIBRATION_30_TOTAL_20_TAKER_10_MAKER_5_EACH_DIRECTION'
    ::text as preregistered_sample_contract,
  true as evidence_collection_active,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  'verified-execution-slippage-status-v0.1'::text as model_version
from active a
cross join stats s;

revoke all on public.alpha_hunter_verified_execution_slippage_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_verified_execution_slippage_status_v01
  to service_role;


create or replace view public.alpha_hunter_execution_cost_validation_readiness_v04
with (security_invoker=true,security_barrier=true)
as
select
  r.eligible_market_fill_rows,
  r.benchmark_rows,
  r.benchmark_evaluated_rows,
  r.benchmark_data_insufficient_rows,
  r.benchmark_integrity_error_rows,
  r.benchmark_failure_rows,
  r.coarse_benchmark_coverage_pct,
  r.first_benchmark_fill_at_utc,
  r.latest_benchmark_fill_at_utc,
  r.realized_fee_rows,
  r.realized_fee_bps_rows,
  r.first_fee_fill_at_utc,
  r.latest_fee_fill_at_utc,
  r.observed_maker_fee_bps,
  r.observed_taker_fee_bps,
  r.observable_taker_round_trip_floor_p90_bps,

  s.spec_id as active_spec_id,
  s.started_at_utc as active_spec_started_at_utc,
  s.verified_execution_rows,
  s.verified_taker_rows,
  s.verified_maker_rows,
  s.verified_long_rows,
  s.verified_short_rows,
  s.execute_now_rows,
  s.place_limit_rows,
  s.arrival_slippage_measured_rows,
  s.realized_fee_measured_rows,
  s.first_verified_freeze_at_utc,
  s.latest_verified_freeze_at_utc,
  s.first_verified_fill_at_utc,
  s.latest_verified_fill_at_utc,
  s.mean_signed_arrival_to_fill_bps,
  s.median_signed_arrival_to_fill_bps,
  s.median_adverse_entry_slippage_bps,
  s.p90_adverse_entry_slippage_bps,
  s.p95_adverse_entry_slippage_bps,
  s.median_realized_fee_bps,
  s.p90_realized_fee_bps,
  s.median_freeze_to_order_seconds,
  s.p90_freeze_to_order_seconds,
  s.median_order_to_fill_seconds,
  s.p90_order_to_fill_seconds,
  s.minimum_verified_execution_rows,
  s.minimum_verified_taker_rows,
  s.minimum_verified_maker_rows,
  s.minimum_verified_long_rows,
  s.minimum_verified_short_rows,
  s.entry_slippage_calibration_sample_gate_met,
  s.verified_exit_slippage_rows,
  s.verified_post_fill_markout_rows,
  s.exit_slippage_sample_gate_met,
  s.adverse_selection_markout_gate_met,
  s.realized_funding_path_gate_met,
  s.missing_data_policy_frozen,
  s.out_of_sample_replication_gate_met,

  r.active_validated_model_rows,
  false as coarse_benchmark_is_slippage,
  false as alpha_hunter_execution_performance_claim_permitted,

  (
    r.active_validated_model_rows>0
    and s.entry_slippage_calibration_sample_gate_met
    and s.exit_slippage_sample_gate_met
    and s.adverse_selection_markout_gate_met
    and s.realized_funding_path_gate_met
    and s.missing_data_policy_frozen
    and s.out_of_sample_replication_gate_met
  ) as full_cost_validation_evidence_complete,

  false as cost_model_activation_permitted,
  false as realistic_net_r_model_activation_permitted,
  false as realistic_net_r_claim_permitted,

  case
    when r.active_validated_model_rows>0
      and s.entry_slippage_calibration_sample_gate_met
      and s.exit_slippage_sample_gate_met
      and s.adverse_selection_markout_gate_met
      and s.realized_funding_path_gate_met
      and s.missing_data_policy_frozen
      and s.out_of_sample_replication_gate_met
      then 'ACTIVE_MODEL_PRESENT_FULL_EVIDENCE_REVIEW_REQUIRED'
    else s.validation_status
  end as validation_status,

  case
    when r.active_validated_model_rows=0
      and s.entry_slippage_calibration_sample_gate_met
      then 'DO_NOT_ACTIVATE_YET_CAPTURE_FULL_COST_PATH_AND_OOS_REPLICATION'
    else s.next_gate
  end as next_gate,

  true as evidence_collection_active,
  true as shadow_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  'execution-cost-validation-readiness-v0.4'::text as model_version
from public.alpha_hunter_execution_cost_validation_readiness_v03 r
cross join public.alpha_hunter_verified_execution_slippage_status_v01 s;

revoke all on public.alpha_hunter_execution_cost_validation_readiness_v04
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_cost_validation_readiness_v04
  to service_role;

commit;
