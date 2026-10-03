-- Alpha Hunter threshold + risk governance drafts v0.1
--
-- Purpose:
--   Register explicit DRAFT governance records so the production system has
--   durable validation targets instead of empty version tables.
--
-- Safety:
--   * status remains DRAFT
--   * all numeric thresholds/risk limits remain NULL
--   * validated_at_utc / activated_at_utc remain NULL
--   * shadow_only=true
--   * trade_permission=false
--   * live writers select ACTIVE+validated+activated rows only
--   * no execution or order authority is introduced

insert into public.alpha_hunter_money_entry_threshold_sets(
  threshold_set_id,
  status,
  max_t0_stop_distance_pct,
  min_t0_remaining_r,
  min_t1_remaining_r,
  min_t2_remaining_r,
  evidence_reference,
  validated_at_utc,
  activated_at_utc,
  model_version,
  shadow_only,
  trade_permission
) values (
  'ME-THRESH-DRAFT-R3-20260929',
  'DRAFT',
  null,
  null,
  null,
  null,
  jsonb_build_object(
    'scientific_role','PREREGISTERED_DRAFT_ONLY',
    'cohort','R3_PARALLEL_CALIBRATION_PILOT',
    'calibration_source','private.alpha_hunter_money_entry_calibration_cohort_v01',
    'pilot_snapshot_at_utc','2026-09-29T15:59:34.163232+00:00',
    'pilot_24h_evaluated_candidates',1009,
    'pilot_distinct_symbols',185,
    'pilot_avg_path_r_pre_cost',0.0361729163480245,
    'pilot_median_path_r_pre_cost',0.0735024849594561,
    'pilot_stop_survived_rows',881,
    'pilot_target_hit_rows',788,
    'pilot_only_not_confirmatory',true,
    'numeric_thresholds_frozen',false,
    'numeric_threshold_promotion_permitted',false,
    'required_before_validation',jsonb_build_array(
      'FREEZE_EXACT_INCLUSION_EXCLUSION_RULES',
      'FREEZE_TEST_AND_MATCHED_CONTROL_CONSTRUCTION',
      'FREEZE_PRIMARY_AND_SECONDARY_HORIZONS',
      'FREEZE_DUPLICATE_AND_DEPENDENCE_HANDLING',
      'DERIVE_SAMPLE_FLOOR_FROM_PILOT_VARIANCE_THEN_FREEZE_BEFORE_HOLDOUT',
      'FREEZE_MINIMUM_ECONOMIC_EFFECT_BEFORE_HOLDOUT',
      'FREEZE_ALPHA_AND_MULTIPLE_TESTING_FAMILY',
      'FREEZE_MISSING_DATA_POLICY',
      'FREEZE_FALSIFICATION_CONDITION',
      'REQUIRE_INDEPENDENT_REPLICATION',
      'REQUIRE_VALIDATED_EXECUTION_COST_MODEL_FOR_REALISTIC_NET_R',
      'NO_THRESHOLD_INFERENCE_FROM_PILOT_MEANS_ALONE'
    ),
    'governance_issue',29
  ),
  null,
  null,
  'money-entry-threshold-draft-r3-v0.1',
  true,
  false
)
on conflict(threshold_set_id) do nothing;

insert into public.alpha_hunter_risk_policy_versions(
  risk_policy_id,
  status,
  risk_per_trade_usdt,
  max_total_open_risk_usdt,
  max_concurrent_positions,
  max_correlated_positions,
  max_daily_loss_usdt,
  min_liquidation_buffer_pct,
  evidence_reference,
  validated_at_utc,
  activated_at_utc,
  model_version,
  shadow_only,
  trade_permission
) values (
  'RISK-POLICY-DRAFT-R3-20260929',
  'DRAFT',
  null,
  null,
  null,
  null,
  null,
  null,
  jsonb_build_object(
    'scientific_role','PREREGISTERED_DRAFT_ONLY',
    'policy_role','VETO_ONLY_POSITION_AND_PORTFOLIO_RISK',
    'account_source','alpha_hunter_account_state_snapshots',
    'position_source','alpha_hunter_open_position_snapshots',
    'current_account_gate','CONNECTED_READ_ONLY_COMPLETE',
    'current_position_gate','VERIFIED_SNAPSHOT',
    'numeric_risk_limits_frozen',false,
    'risk_policy_activation_permitted',false,
    'required_before_validation',jsonb_build_array(
      'EXPLICIT_NUMERIC_RISK_BUDGET_PREREGISTRATION',
      'VALIDATED_MONEY_ENTRY_THRESHOLD_SET',
      'ACTIVE_VALIDATED_EXECUTION_COST_MODEL',
      'VERIFIED_REALISTIC_NET_R_PATH',
      'CONNECTED_READ_ONLY_COMPLETE_ACCOUNT_STATE',
      'VERIFIED_POSITION_LEDGER',
      'CORRELATION_MODEL_OR_FAIL_CLOSED_CORRELATION_LIMIT',
      'DAILY_LOSS_CIRCUIT_BREAKER_TESTS',
      'LIQUIDATION_BUFFER_TESTS',
      'FORWARD_SHADOW_REPLICATION',
      'NO_LEVERAGE_SELECTION_BEFORE_STRUCTURAL_STOP_AND_POSITION_SIZE'
    )
  ),
  null,
  null,
  'portfolio-risk-policy-draft-r3-v0.1',
  true,
  false
)
on conflict(risk_policy_id) do nothing;
