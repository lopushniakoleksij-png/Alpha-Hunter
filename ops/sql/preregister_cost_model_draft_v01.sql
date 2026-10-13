-- Alpha Hunter execution-cost model governance draft v0.1
--
-- Descriptive evidence is persisted, but no model parameter is promoted.
-- All fee/slippage model columns stay NULL until prospective Alpha Hunter
-- executions are explicitly bound and independently validated.

insert into public.alpha_hunter_execution_cost_model_versions(
  cost_model_id,
  status,
  maker_fee_bps,
  taker_fee_bps,
  entry_slippage_bps,
  exit_slippage_bps,
  evidence_reference,
  validated_at_utc,
  activated_at_utc,
  model_version,
  shadow_only,
  trade_permission
) values (
  'COST-MODEL-DRAFT-R3-20260929',
  'DRAFT',
  null,
  null,
  null,
  null,
  jsonb_build_object(
    'scientific_role','PREREGISTERED_DRAFT_ONLY',
    'observed_at_utc','2026-09-29T16:17:00+00:00',
    'descriptive_fee_evidence',jsonb_build_object(
      'maker_fee_bps',2.0,
      'maker_fill_count',9,
      'taker_fee_bps',6.0,
      'taker_fill_count',200,
      'fee_values_promoted_to_model',false
    ),
    'descriptive_spread_evidence',jsonb_build_object(
      'snapshot_rows',11603,
      'valid_quote_pct',100.0,
      'median_spread_bps',4.60405156537703,
      'p90_spread_bps',16.4473684210529,
      'p95_spread_bps',20.3778925803801,
      'observable_taker_round_trip_floor_median_bps',16.604051565377,
      'observable_taker_round_trip_floor_p90_bps',28.4473684210529,
      'observable_taker_round_trip_floor_p95_bps',32.3778925803801,
      'floor_is_validated_cost_model',false
    ),
    'prospective_attribution_state',jsonb_build_object(
      'frozen_decisions',12,
      'explicit_fill_bindings',0,
      'verified_alpha_hunter_executions',0,
      'slippage_model_validated',false,
      'realistic_net_r_claim_permitted',false
    ),
    'model_parameters_frozen',false,
    'cost_model_activation_permitted',false,
    'required_before_validation',jsonb_build_array(
      'EXPLICIT_PROSPECTIVE_DECISION_TO_EXACT_FILL_BINDINGS',
      'VERIFIED_ALPHA_HUNTER_EXECUTION_ATTRIBUTION',
      'ARRIVAL_TO_FILL_SLIPPAGE_SAMPLE',
      'FREEZE_MINIMUM_SLIPPAGE_SAMPLE_FLOOR_BEFORE_CONFIRMATORY_USE',
      'SEGMENT_MAKER_AND_TAKER_EXECUTIONS',
      'MEASURE_FREEZE_TO_ORDER_AND_ORDER_TO_FILL_LATENCY',
      'MEASURE_ADVERSE_SELECTION_AND_POST_FILL_MARKOUTS',
      'MEASURE_EXIT_SLIPPAGE_OR_DEFINE_CONSERVATIVE_EXIT_MODEL',
      'INCLUDE_REALIZED_FEES',
      'BIND_FUNDING_WHERE_APPLICABLE',
      'FREEZE_MISSING_DATA_POLICY',
      'REQUIRE_OUT_OF_SAMPLE_REPLICATION',
      'NO_REALISTIC_NET_R_CLAIM_BEFORE_VALIDATION'
    ),
    'next_gate','FIRST_EXPLICIT_PROSPECTIVE_ALPHA_HUNTER_FILL_BINDING'
  ),
  null,
  null,
  'execution-cost-model-draft-r3-v0.1',
  true,
  false
)
on conflict(cost_model_id) do nothing;
