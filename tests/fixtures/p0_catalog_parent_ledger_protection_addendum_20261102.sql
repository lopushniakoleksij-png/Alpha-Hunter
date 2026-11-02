-- P0 ISOLATED CATALOG ADDENDUM: never execute against production.
-- Derived from read-only catalog; synthetic empty tables; no production secrets.
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
CREATE TABLE private.alpha_hunter_snapshot_slim_v01 (
  "run_id" text NOT NULL,
  "collected_at_utc" timestamp with time zone NOT NULL,
  "payload" jsonb NOT NULL,
  "captured_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.alpha_hunter_account_state_snapshots (
  "account_snapshot_id" text NOT NULL,
  "captured_at_utc" timestamp with time zone NOT NULL,
  "equity_usdt" double precision,
  "available_usdt" double precision,
  "margin_used_usdt" double precision,
  "unrealized_pnl_usdt" double precision,
  "daily_realized_pnl_usdt" double precision,
  "source" text NOT NULL,
  "connection_status" text NOT NULL,
  "schema_validated" boolean NOT NULL DEFAULT false,
  "complete" boolean NOT NULL DEFAULT false,
  "evidence" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.alpha_hunter_open_position_snapshots (
  "position_snapshot_id" text NOT NULL,
  "account_snapshot_id" text NOT NULL,
  "captured_at_utc" timestamp with time zone NOT NULL,
  "symbol" text NOT NULL,
  "direction" text NOT NULL,
  "quantity" double precision,
  "average_entry" double precision,
  "mark_price" double precision,
  "liquidation_price" double precision,
  "notional_usdt" double precision,
  "unrealized_pnl_usdt" double precision,
  "source_position_id" text,
  "evidence" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "structural_stop_price" double precision,
  "planned_risk_usdt" double precision,
  "strategy_event_id" text,
  "source_order_intent_id" text
);
CREATE TABLE public.alpha_hunter_account_ledger_materialization_events (
  "event_id" text NOT NULL,
  "run_id" text NOT NULL,
  "captured_at_utc" timestamp with time zone NOT NULL,
  "status" text NOT NULL,
  "account_snapshot_id" text,
  "details" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "model_version" text NOT NULL DEFAULT 'canonical-account-ledger-materialization-v0.1'::text,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.alpha_hunter_profit_management_forward_config_v01 (
  "config_id" text NOT NULL,
  "activated_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "policy_count" integer NOT NULL DEFAULT 3,
  "model_version" text NOT NULL DEFAULT 'profit-management-forward-v0.1'::text,
  "forward_only" boolean NOT NULL DEFAULT true,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.alpha_hunter_profit_management_forward_v01 (
  "observation_id" text NOT NULL,
  "position_snapshot_id" text NOT NULL,
  "account_snapshot_id" text NOT NULL,
  "captured_at_utc" timestamp with time zone NOT NULL,
  "episode_id" text NOT NULL,
  "episode_started_at_utc" timestamp with time zone NOT NULL,
  "continuity_status" text NOT NULL,
  "previous_position_snapshot_id" text,
  "symbol" text NOT NULL,
  "direction" text NOT NULL,
  "quantity" double precision NOT NULL,
  "average_entry" double precision NOT NULL,
  "mark_price" double precision NOT NULL,
  "episode_entry_price" double precision NOT NULL,
  "episode_initial_quantity" double precision NOT NULL,
  "policy_id" text NOT NULL,
  "activation_favorable_pct" double precision NOT NULL,
  "lock_fraction" double precision NOT NULL,
  "threshold_basis" text NOT NULL,
  "running_favorable_mark" double precision NOT NULL,
  "running_favorable_pct" double precision NOT NULL,
  "policy_active" boolean NOT NULL,
  "policy_activated_at_utc" timestamp with time zone,
  "shadow_stop_price" double precision,
  "shadow_state" text NOT NULL,
  "trigger_observed_on_this_snapshot" boolean NOT NULL DEFAULT false,
  "shadow_trigger_at_utc" timestamp with time zone,
  "shadow_trigger_observed_mark" double precision,
  "shadow_stop_at_trigger" double precision,
  "entry_changed_from_previous" boolean NOT NULL DEFAULT false,
  "quantity_changed_from_previous" boolean NOT NULL DEFAULT false,
  "evidence" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "forward_only" boolean NOT NULL DEFAULT true,
  "sampled_mark_limitation" boolean NOT NULL DEFAULT true,
  "counterfactual_fee_claim_permitted" boolean NOT NULL DEFAULT false,
  "counterfactual_funding_claim_permitted" boolean NOT NULL DEFAULT false,
  "counterfactual_net_pnl_claim_permitted" boolean NOT NULL DEFAULT false,
  "management_change_permitted" boolean NOT NULL DEFAULT false,
  "stop_change_permitted" boolean NOT NULL DEFAULT false,
  "target_change_permitted" boolean NOT NULL DEFAULT false,
  "promotion_permitted" boolean NOT NULL DEFAULT false,
  "model_version" text NOT NULL DEFAULT 'profit-management-forward-v0.1'::text,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.alpha_hunter_protection_reconciliation_events_v01 (
  "event_id" text NOT NULL,
  "position_snapshot_id" text NOT NULL,
  "account_snapshot_id" text NOT NULL,
  "captured_at_utc" timestamp with time zone NOT NULL,
  "symbol" text NOT NULL,
  "direction" text NOT NULL,
  "observation_status" text NOT NULL,
  "protection_state" text NOT NULL,
  "stop_loss_observed" text,
  "take_profit_observed" text,
  "stop_loss_source" text,
  "take_profit_source" text,
  "stop_order_count" integer NOT NULL DEFAULT 0,
  "take_profit_order_count" integer NOT NULL DEFAULT 0,
  "position_field_gap_detected" boolean NOT NULL DEFAULT false,
  "details" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "model_version" text NOT NULL DEFAULT 'protection-reconciliation-audit-v0.1'::text,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE private.alpha_hunter_calibrated_paper_policy_v01 (
  "policy_id" text NOT NULL,
  "status" text NOT NULL,
  "outcome_definition" text NOT NULL,
  "calibrated_confidence_pct" double precision NOT NULL,
  "confidence_lower_95_pct" double precision NOT NULL,
  "confidence_upper_95_pct" double precision NOT NULL,
  "training_n" integer NOT NULL,
  "training_wins" integer NOT NULL,
  "holdout_n" integer NOT NULL,
  "holdout_wins" integer NOT NULL,
  "minimum_reward_risk" double precision NOT NULL,
  "max_active_paper_orders" integer NOT NULL DEFAULT 1,
  "cohort" jsonb NOT NULL,
  "evidence" jsonb NOT NULL,
  "paper_only" boolean NOT NULL DEFAULT true,
  "live_order_authority" boolean NOT NULL DEFAULT false,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "updated_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE private.alpha_hunter_calibrated_paper_orders_v01 (
  "paper_order_id" text NOT NULL,
  "policy_id" text NOT NULL,
  "execution_event_id" text NOT NULL,
  "decision_observation_id" text NOT NULL,
  "strategy_instance_id" text NOT NULL,
  "run_id" text NOT NULL,
  "symbol" text NOT NULL,
  "strategy_id" text NOT NULL,
  "direction" text NOT NULL,
  "action" text NOT NULL,
  "decision_observed_at_utc" timestamp with time zone NOT NULL,
  "frozen_at_utc" timestamp with time zone NOT NULL,
  "paper_order_created_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "planned_entry_price" double precision NOT NULL,
  "stop_price" double precision NOT NULL,
  "target_price" double precision NOT NULL,
  "reward_risk" double precision NOT NULL,
  "calibrated_confidence_pct" double precision NOT NULL,
  "confidence_lower_95_pct" double precision NOT NULL,
  "confidence_upper_95_pct" double precision NOT NULL,
  "calibration_cohort" jsonb NOT NULL,
  "state" text NOT NULL,
  "paper_only" boolean NOT NULL DEFAULT true,
  "live_exchange_order_sent" boolean NOT NULL DEFAULT false,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "paper_fill_status" text,
  "paper_fill_price" double precision,
  "paper_fill_at_utc" timestamp with time zone,
  "paper_fill_source" text,
  "paper_fill_horizon_hours" integer,
  "paper_entry_half_spread_bps" double precision,
  "paper_outcome_class" text,
  "paper_endpoint_price" double precision,
  "paper_gross_return_pct" double precision,
  "paper_gross_r" double precision,
  "paper_net_return_pct" double precision,
  "paper_net_r" double precision,
  "paper_cost_adjustment_status" text,
  "paper_outcome_evaluated_at_utc" timestamp with time zone,
  "last_reconciled_at_utc" timestamp with time zone,
  "paper_execution_evidence" jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE public.alpha_hunter_signal_features (
  "signal_id" text NOT NULL,
  "run_id" text NOT NULL,
  "symbol" text NOT NULL,
  "captured_at_utc" timestamp with time zone NOT NULL,
  "state" text,
  "direction" text,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "trend_15m" text,
  "trend_1h" text,
  "trend_4h" text,
  "btc_regime" text,
  "sector" text,
  "session" text,
  "weekday" smallint,
  "hour_utc" smallint,
  "huge_rr_score" double precision,
  "confidence_estimate_pct" double precision,
  "reward_risk" double precision,
  "volume_ratio" double precision,
  "volume_expansion" boolean,
  "volatility_pct" double precision,
  "compression_score" double precision,
  "funding_rate" double precision,
  "open_interest" double precision,
  "open_interest_change_pct" double precision,
  "relative_strength_btc" double precision,
  "rsi_15m" double precision,
  "rsi_1h" double precision,
  "rsi_4h" double precision,
  "distance_to_support_pct" double precision,
  "distance_to_resistance_pct" double precision,
  "ema_alignment_15m" text,
  "ema_alignment_1h" text,
  "ema_alignment_4h" text,
  "liquidity_state" text,
  "features" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "source_payload" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "created_at" timestamp with time zone NOT NULL DEFAULT now()
);
CREATE TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 (
  "spec_id" text NOT NULL,
  "registered_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "status" text NOT NULL DEFAULT 'COLLECTING'::text,
  "minimum_history_n" integer NOT NULL,
  "cost_fragile_threshold_r" double precision NOT NULL,
  "stop_reference" text NOT NULL,
  "target_reference" text NOT NULL,
  "minimum_forward_observations" integer NOT NULL,
  "minimum_forward_symbols" integer NOT NULL,
  "minimum_forward_days" integer NOT NULL,
  "evidence" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "threshold_change_permitted" boolean NOT NULL DEFAULT false,
  "production_promotion_permitted" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 (
  "geometry_health_id" text NOT NULL,
  "spec_id" text NOT NULL,
  "execution_event_id" text NOT NULL,
  "decision_observation_id" text NOT NULL,
  "strategy_instance_id" text NOT NULL,
  "run_id" text NOT NULL,
  "symbol" text NOT NULL,
  "strategy_id" text NOT NULL,
  "direction" text NOT NULL,
  "action" text NOT NULL,
  "decision_observed_at_utc" timestamp with time zone NOT NULL,
  "frozen_at_utc" timestamp with time zone NOT NULL,
  "planned_entry_price" double precision NOT NULL,
  "stop_price" double precision NOT NULL,
  "target_price" double precision NOT NULL,
  "reward_risk" double precision,
  "stop_distance_pct" double precision NOT NULL,
  "target_distance_pct" double precision NOT NULL,
  "descriptive_cost_floor_bps" double precision,
  "descriptive_cost_r" double precision,
  "history_n" integer NOT NULL,
  "historical_median_mae_pct" double precision,
  "historical_p75_mae_pct" double precision,
  "historical_median_mfe_pct" double precision,
  "historical_p90_mfe_pct" double precision,
  "stop_inside_median_mae" boolean,
  "target_beyond_p90_mfe" boolean,
  "cost_fragile" boolean,
  "geometry_health" text NOT NULL,
  "reasons" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "evidence" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "threshold_change_permitted" boolean NOT NULL DEFAULT false,
  "production_promotion_permitted" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.alpha_hunter_strategy_forward_outcomes_v01 (
  "episode_id" text NOT NULL,
  "horizon_hours" integer NOT NULL,
  "evaluated_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "horizon_end_utc" timestamp with time zone NOT NULL,
  "symbol" text NOT NULL,
  "strategy_id" text NOT NULL,
  "strategy_engine_version" text,
  "direction" text NOT NULL,
  "first_observed_at_utc" timestamp with time zone NOT NULL,
  "first_reference_price" double precision,
  "earliest_identifiable_entry_price" double precision,
  "first_reward_risk" double precision,
  "first_candidate_at_utc" timestamp with time zone,
  "first_candidate_action" text,
  "first_candidate_reference_price" double precision,
  "first_candidate_entry_price" double precision,
  "first_candidate_stop_price" double precision,
  "first_candidate_target_price" double precision,
  "remaining_r_at_candidate" double precision,
  "remaining_r_delta_from_first" double precision,
  "time_to_candidate_minutes" double precision,
  "confirmation_tax_reference_pct" double precision,
  "confirmation_tax_entry_pct" double precision,
  "confirmation_tax_r" double precision,
  "entry_trigger_status" text NOT NULL,
  "entry_trigger_candle_open_utc" timestamp with time zone,
  "entry_trigger_known_at_utc" timestamp with time zone,
  "fill_price" double precision,
  "time_to_entry_trigger_minutes" double precision,
  "measurement_start_candle_open_utc" timestamp with time zone,
  "expected_path_candle_count" integer NOT NULL DEFAULT 0,
  "observed_path_candle_count" integer NOT NULL DEFAULT 0,
  "path_coverage_pct" double precision,
  "path_measurement_quality" text NOT NULL,
  "trigger_candle_excluded" boolean NOT NULL DEFAULT true,
  "partial_signal_hour_excluded" boolean NOT NULL DEFAULT true,
  "max_favorable_excursion_pct" double precision,
  "max_adverse_excursion_pct" double precision,
  "endpoint_close_price" double precision,
  "direction_adjusted_endpoint_return_pct" double precision,
  "first_target_hit_candle_open_utc" timestamp with time zone,
  "first_stop_hit_candle_open_utc" timestamp with time zone,
  "path_outcome_class" text NOT NULL,
  "ordering_ambiguous" boolean NOT NULL DEFAULT false,
  "gross_only" boolean NOT NULL DEFAULT true,
  "net_of_cost_return_pct" double precision,
  "cost_adjustment_status" text NOT NULL DEFAULT 'NOT_BOUND_TO_COST_EVIDENCE'::text,
  "scientific_role" text NOT NULL DEFAULT 'PROSPECTIVE_STRATEGY_FORWARD_OUTCOME'::text,
  "model_version" text NOT NULL DEFAULT 'strategy-forward-outcome-v0.1'::text,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "threshold_change_permitted" boolean NOT NULL DEFAULT false,
  "production_promotion_permitted" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_or_live_exchange_order_sent_check" CHECK ((live_exchange_order_sent = false));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders__planned_entry_price_check" CHECK ((planned_entry_price > (0)::double precision));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_action_check" CHECK ((action = ANY (ARRAY['EXECUTE_NOW'::text, 'PLACE_LIMIT'::text])));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_direction_check" CHECK ((direction = ANY (ARRAY['LONG'::text, 'SHORT'::text])));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_paper_only_check" CHECK ((paper_only = true));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_reward_risk_check" CHECK ((reward_risk > (0)::double precision));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_state_check" CHECK ((state = ANY (ARRAY['PENDING_LIMIT_PAPER'::text, 'OPEN_PAPER'::text, 'OUTCOME_AVAILABLE'::text])));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_stop_price_check" CHECK ((stop_price > (0)::double precision));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_target_price_check" CHECK ((target_price > (0)::double precision));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_pkey" PRIMARY KEY (paper_order_id);
ALTER TABLE private.alpha_hunter_calibrated_paper_orders_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_orders_v01_execution_event_id_key" UNIQUE (execution_event_id);
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_p_calibrated_confidence_pct_check" CHECK (((calibrated_confidence_pct >= (0)::double precision) AND (calibrated_confidence_pct <= (100)::double precision)));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_pol_max_active_paper_orders_check" CHECK ((max_active_paper_orders >= 1));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy__minimum_reward_risk_check" CHECK ((minimum_reward_risk > (0)::double precision));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_live_order_authority_check" CHECK ((live_order_authority = false));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_v01_check" CHECK (((confidence_lower_95_pct >= (0)::double precision) AND (confidence_lower_95_pct <= calibrated_confidence_pct)));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_v01_check1" CHECK (((confidence_upper_95_pct >= calibrated_confidence_pct) AND (confidence_upper_95_pct <= (100)::double precision)));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_v01_check2" CHECK (((training_n > 0) AND (holdout_n > 0)));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_v01_check3" CHECK (((training_wins >= 0) AND (training_wins <= training_n)));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_v01_check4" CHECK (((holdout_wins >= 0) AND (holdout_wins <= holdout_n)));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_v01_paper_only_check" CHECK ((paper_only = true));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_v01_status_check" CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'PAUSED'::text, 'RETIRED'::text])));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_v01_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE private.alpha_hunter_calibrated_paper_policy_v01 ADD CONSTRAINT "alpha_hunter_calibrated_paper_policy_v01_pkey" PRIMARY KEY (policy_id);
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry__threshold_change_permitted_check1" CHECK ((threshold_change_permitted = false));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_o_planned_entry_price_check" CHECK ((planned_entry_price > (0)::double precision));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_o_target_distance_pct_check" CHECK ((target_distance_pct > (0)::double precision));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_obs_stop_distance_pct_check" CHECK ((stop_distance_pct > (0)::double precision));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_obse_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_observat_target_price_check" CHECK ((target_price > (0)::double precision));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_observati_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_observatio_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_observatio_stop_price_check" CHECK ((stop_price > (0)::double precision));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_observation_direction_check" CHECK ((direction = ANY (ARRAY['LONG'::text, 'SHORT'::text])));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_observation_history_n_check" CHECK ((history_n >= 0));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_production_promotion_permit_check1" CHECK ((production_promotion_permitted = false));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_observations_v01_pkey" PRIMARY KEY (geometry_health_id);
ALTER TABLE private.alpha_hunter_payoff_geometry_health_observations_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_obse_execution_event_id_key" UNIQUE (execution_event_id);
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_h_threshold_change_permitted_check" CHECK ((threshold_change_permitted = false));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_hea_cost_fragile_threshold_r_check" CHECK ((cost_fragile_threshold_r > (0)::double precision));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_heal_minimum_forward_symbols_check" CHECK ((minimum_forward_symbols >= 1));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health__minimum_forward_days_check" CHECK ((minimum_forward_days >= 1));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_spe_minimum_history_n_check" CHECK ((minimum_history_n >= 1));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_spec_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_specs_v01_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_specs_v01_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_specs_v01_status_check" CHECK ((status = ANY (ARRAY['COLLECTING'::text, 'PAUSED'::text, 'RETIRED'::text])));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_minimum_forward_observations_check" CHECK ((minimum_forward_observations >= 1));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_production_promotion_permitt_check" CHECK ((production_promotion_permitted = false));
ALTER TABLE private.alpha_hunter_payoff_geometry_health_specs_v01 ADD CONSTRAINT "alpha_hunter_payoff_geometry_health_specs_v01_pkey" PRIMARY KEY (spec_id);
ALTER TABLE private.alpha_hunter_snapshot_slim_v01 ADD CONSTRAINT "alpha_hunter_snapshot_slim_v01_pkey" PRIMARY KEY (run_id);
ALTER TABLE public.alpha_hunter_account_ledger_materialization_events ADD CONSTRAINT "alpha_hunter_account_ledger_materializat_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_account_ledger_materialization_events ADD CONSTRAINT "alpha_hunter_account_ledger_materialization_e_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_account_ledger_materialization_events ADD CONSTRAINT "alpha_hunter_account_ledger_materialization_event_details_check" CHECK ((jsonb_typeof(details) = 'object'::text));
ALTER TABLE public.alpha_hunter_account_ledger_materialization_events ADD CONSTRAINT "alpha_hunter_account_ledger_materialization_events_status_check" CHECK ((status = ANY (ARRAY['MATERIALIZED_CONNECTED'::text, 'MATERIALIZED_DISCONNECTED'::text, 'MATERIALIZED_INSUFFICIENT'::text, 'FAILED'::text])));
ALTER TABLE public.alpha_hunter_account_ledger_materialization_events ADD CONSTRAINT "alpha_hunter_account_ledger_materialization_events_pkey" PRIMARY KEY (event_id);
ALTER TABLE public.alpha_hunter_account_state_snapshots ADD CONSTRAINT "alpha_hunter_account_state_snapshots_connection_status_check" CHECK ((connection_status = ANY (ARRAY['CONNECTED_READ_ONLY'::text, 'DISCONNECTED'::text, 'DATA_INSUFFICIENT'::text])));
ALTER TABLE public.alpha_hunter_account_state_snapshots ADD CONSTRAINT "alpha_hunter_account_state_snapshots_evidence_check" CHECK ((jsonb_typeof(evidence) = 'object'::text));
ALTER TABLE public.alpha_hunter_account_state_snapshots ADD CONSTRAINT "alpha_hunter_account_state_snapshots_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_account_state_snapshots ADD CONSTRAINT "alpha_hunter_account_state_snapshots_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_account_state_snapshots ADD CONSTRAINT "alpha_hunter_account_state_snapshots_pkey" PRIMARY KEY (account_snapshot_id);
ALTER TABLE public.alpha_hunter_open_position_snapshots ADD CONSTRAINT "alpha_hunter_open_position_snapshots_direction_check" CHECK ((direction = ANY (ARRAY['LONG'::text, 'SHORT'::text])));
ALTER TABLE public.alpha_hunter_open_position_snapshots ADD CONSTRAINT "alpha_hunter_open_position_snapshots_evidence_check" CHECK ((jsonb_typeof(evidence) = 'object'::text));
ALTER TABLE public.alpha_hunter_open_position_snapshots ADD CONSTRAINT "alpha_hunter_open_position_snapshots_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_open_position_snapshots ADD CONSTRAINT "alpha_hunter_open_position_snapshots_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_open_position_snapshots ADD CONSTRAINT "alpha_hunter_open_position_snapshots_pkey" PRIMARY KEY (position_snapshot_id);
ALTER TABLE public.alpha_hunter_profit_management_forward_config_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_c_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_profit_management_forward_config_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_conf_model_version_check" CHECK ((model_version = 'profit-management-forward-v0.1'::text));
ALTER TABLE public.alpha_hunter_profit_management_forward_config_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_confi_forward_only_check" CHECK ((forward_only = true));
ALTER TABLE public.alpha_hunter_profit_management_forward_config_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_confi_policy_count_check" CHECK ((policy_count = 3));
ALTER TABLE public.alpha_hunter_profit_management_forward_config_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_config__order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE public.alpha_hunter_profit_management_forward_config_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_config_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_profit_management_forward_config_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_config_v_config_id_check" CHECK ((config_id = 'profit-management-forward-v0.1'::text));
ALTER TABLE public.alpha_hunter_profit_management_forward_config_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_config_v01_pkey" PRIMARY KEY (config_id);
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_manageme_counterfactual_fee_claim_per_check" CHECK ((counterfactual_fee_claim_permitted = false));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_manageme_counterfactual_funding_claim_check" CHECK ((counterfactual_funding_claim_permitted = false));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_manageme_counterfactual_net_pnl_claim_check" CHECK ((counterfactual_net_pnl_claim_permitted = false));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_managemen_management_change_permitted_check" CHECK ((management_change_permitted = false));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_fo_sampled_mark_limitation_check" CHECK ((sampled_mark_limitation = true));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_fo_target_change_permitted_check" CHECK ((target_change_permitted = false));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forw_stop_change_permitted_check" CHECK ((stop_change_permitted = false));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forwar_promotion_permitted_check" CHECK ((promotion_permitted = false));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward__continuity_status_check" CHECK ((continuity_status = ANY (ARRAY['NEW_FORWARD_EPISODE'::text, 'CONTINUED_FROM_PREVIOUS_ACCOUNT_SNAPSHOT'::text, 'ENTRY_CHANGED_RESTART'::text, 'FORWARD_ANCHOR_MISSING_RESTART'::text])));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v01_direction_check" CHECK ((direction = ANY (ARRAY['LONG'::text, 'SHORT'::text])));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v01_evidence_check" CHECK ((jsonb_typeof(evidence) = 'object'::text));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v01_forward_only_check" CHECK ((forward_only = true));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v01_model_version_check" CHECK ((model_version = 'profit-management-forward-v0.1'::text));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v01_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v01_policy_id_check" CHECK ((policy_id = ANY (ARRAY['BE_AFTER_3PCT'::text, 'LOCK_25_AFTER_5PCT'::text, 'LOCK_50_AFTER_5PCT'::text])));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v01_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v01_shadow_state_check" CHECK ((shadow_state = ANY (ARRAY['INACTIVE'::text, 'ACTIVE'::text, 'TRIGGERED'::text])));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_management_forward_v01_pkey" PRIMARY KEY (observation_id);
ALTER TABLE public.alpha_hunter_profit_management_forward_v01 ADD CONSTRAINT "alpha_hunter_profit_managemen_position_snapshot_id_policy_i_key" UNIQUE (position_snapshot_id, policy_id);
ALTER TABLE public.alpha_hunter_protection_reconciliation_events_v01 ADD CONSTRAINT "alpha_hunter_protection_reconcili_take_profit_order_count_check" CHECK ((take_profit_order_count >= 0));
ALTER TABLE public.alpha_hunter_protection_reconciliation_events_v01 ADD CONSTRAINT "alpha_hunter_protection_reconciliation_e_protection_state_check" CHECK ((protection_state = ANY (ARRAY['OBSERVED_BOTH'::text, 'OBSERVED_STOP_ONLY'::text, 'OBSERVED_TP_ONLY'::text, 'NONE_OBSERVED'::text, 'UNKNOWN'::text])));
ALTER TABLE public.alpha_hunter_protection_reconciliation_events_v01 ADD CONSTRAINT "alpha_hunter_protection_reconciliation_e_stop_order_count_check" CHECK ((stop_order_count >= 0));
ALTER TABLE public.alpha_hunter_protection_reconciliation_events_v01 ADD CONSTRAINT "alpha_hunter_protection_reconciliation_e_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_protection_reconciliation_events_v01 ADD CONSTRAINT "alpha_hunter_protection_reconciliation_events_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_protection_reconciliation_events_v01 ADD CONSTRAINT "alpha_hunter_protection_reconciliation_events_v01_details_check" CHECK ((jsonb_typeof(details) = 'object'::text));
ALTER TABLE public.alpha_hunter_protection_reconciliation_events_v01 ADD CONSTRAINT "alpha_hunter_protection_reconciliation_events_v01_pkey" PRIMARY KEY (event_id);
ALTER TABLE public.alpha_hunter_signal_features ADD CONSTRAINT "alpha_hunter_signal_features_pkey" PRIMARY KEY (signal_id);
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forwar_partial_signal_hour_excluded_check" CHECK ((partial_signal_hour_excluded = true));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forwar_production_promotion_permitt_check" CHECK ((production_promotion_permitted = false));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forward__threshold_change_permitted_check" CHECK ((threshold_change_permitted = false));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forward_out_trigger_candle_excluded_check" CHECK ((trigger_candle_excluded = true));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forward_outcomes_v01_direction_check" CHECK ((direction = ANY (ARRAY['LONG'::text, 'SHORT'::text])));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forward_outcomes_v01_gross_only_check" CHECK ((gross_only = true));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forward_outcomes_v01_horizon_hours_check" CHECK ((horizon_hours = ANY (ARRAY[1, 4, 12, 24])));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forward_outcomes_v01_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forward_outcomes_v01_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forward_outcomes_v_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_strategy_forward_outcomes_v01 ADD CONSTRAINT "alpha_hunter_strategy_forward_outcomes_v01_pkey" PRIMARY KEY (episode_id, horizon_hours);
CREATE INDEX idx_ah_cal_paper_orders_state_time ON private.alpha_hunter_calibrated_paper_orders_v01 USING btree (state, paper_order_created_at_utc DESC);
CREATE INDEX idx_ah_payoff_geometry_health_class_v01 ON private.alpha_hunter_payoff_geometry_health_observations_v01 USING btree (geometry_health, frozen_at_utc DESC);
CREATE INDEX idx_ah_payoff_geometry_health_strategy_v01 ON private.alpha_hunter_payoff_geometry_health_observations_v01 USING btree (strategy_id, direction, frozen_at_utc DESC);
CREATE INDEX idx_ah_snapshot_slim_source_time_v01 ON private.alpha_hunter_snapshot_slim_v01 USING btree ((((payload -> 'validation_identity'::text) ->> 'run_source'::text)), collected_at_utc DESC);
CREATE INDEX idx_ah_account_materialization_events_time ON public.alpha_hunter_account_ledger_materialization_events USING btree (captured_at_utc DESC);
CREATE INDEX idx_ah_account_state_time ON public.alpha_hunter_account_state_snapshots USING btree (captured_at_utc DESC);
CREATE INDEX idx_ah_open_positions_account ON public.alpha_hunter_open_position_snapshots USING btree (account_snapshot_id, symbol);
CREATE INDEX idx_ah_profit_management_forward_episode_v01 ON public.alpha_hunter_profit_management_forward_v01 USING btree (episode_id, policy_id, captured_at_utc);
CREATE INDEX idx_ah_profit_management_forward_symbol_v01 ON public.alpha_hunter_profit_management_forward_v01 USING btree (symbol, direction, captured_at_utc DESC);
CREATE INDEX idx_ah_protection_recon_symbol_time ON public.alpha_hunter_protection_reconciliation_events_v01 USING btree (symbol, captured_at_utc DESC);
CREATE INDEX idx_ah_features_btc_regime ON public.alpha_hunter_signal_features USING btree (btc_regime, captured_at_utc DESC);
CREATE INDEX idx_ah_features_captured_training_v01 ON public.alpha_hunter_signal_features USING btree (captured_at_utc DESC);
CREATE INDEX idx_ah_features_run_captured_training_v01 ON public.alpha_hunter_signal_features USING btree (run_id, captured_at_utc DESC);
CREATE INDEX idx_ah_features_sector ON public.alpha_hunter_signal_features USING btree (sector, captured_at_utc DESC);
CREATE INDEX idx_ah_features_session ON public.alpha_hunter_signal_features USING btree (session, captured_at_utc DESC);
CREATE INDEX idx_ah_features_state_time ON public.alpha_hunter_signal_features USING btree (state, captured_at_utc DESC);
CREATE INDEX idx_ah_features_symbol_time ON public.alpha_hunter_signal_features USING btree (symbol, captured_at_utc DESC);
CREATE INDEX idx_ah_strategy_forward_observed_horizon_realtime_v01 ON public.alpha_hunter_strategy_forward_outcomes_v01 USING btree (first_observed_at_utc, horizon_hours);
CREATE INDEX idx_ah_strategy_forward_outcome_strategy_v01 ON public.alpha_hunter_strategy_forward_outcomes_v01 USING btree (strategy_id, horizon_hours, evaluated_at_utc);
CREATE INDEX idx_ah_strategy_outcome_24h_eval_episode_v03 ON public.alpha_hunter_strategy_forward_outcomes_v01 USING btree (evaluated_at_utc, episode_id, first_observed_at_utc) WHERE (horizon_hours = 24);
CREATE INDEX idx_ah_strategy_outcome_24h_time_episode_v02 ON public.alpha_hunter_strategy_forward_outcomes_v01 USING btree (first_observed_at_utc, episode_id) WHERE (horizon_hours = 24);
-- Source catalog function sha md5 cea4e21b84587377fd665e21d2763d6c
CREATE OR REPLACE FUNCTION private.alpha_hunter_capture_payoff_geometry_health_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_spec private.alpha_hunter_payoff_geometry_health_specs_v01%rowtype;
  v_cost_floor_bps double precision;
  v_stop_pct double precision;
  v_target_pct double precision;
  v_cost_r double precision;
  v_history_n integer:=0;
  v_median_mae double precision;
  v_p75_mae double precision;
  v_median_mfe double precision;
  v_p90_mfe double precision;
  v_stop_inside boolean;
  v_target_beyond boolean;
  v_cost_fragile boolean;
  v_health text;
begin
  select * into v_spec
  from private.alpha_hunter_payoff_geometry_health_specs_v01
  where spec_id='PAYOFF-GEOMETRY-HEALTH-V01'
    and status='COLLECTING';

  if not found then
    return new;
  end if;

  if new.frozen_at_utc<v_spec.registered_at_utc then
    return new;
  end if;

  if new.planned_entry_price is null
     or new.planned_entry_price<=0
     or new.stop_price is null
     or new.stop_price<=0
     or new.target_price is null
     or new.target_price<=0
     or new.strategy_instance_id is null
     or new.decision_observation_id is null
  then
    return new;
  end if;

  v_stop_pct :=
    100.0*abs(new.planned_entry_price-new.stop_price)/new.planned_entry_price;
  v_target_pct :=
    100.0*abs(new.target_price-new.planned_entry_price)/new.planned_entry_price;

  if v_stop_pct<=0 or v_target_pct<=0 then
    return new;
  end if;

  select observable_taker_round_trip_floor_median_bps
    into v_cost_floor_bps
  from public.alpha_hunter_execution_cost_floor_status_v01
  where cost_scope='ALL'
  limit 1;

  if v_cost_floor_bps is not null then
    v_cost_r := (v_cost_floor_bps/100.0)/v_stop_pct;
  end if;

  select
    count(*)::integer,
    percentile_cont(0.5) within group(order by o.max_adverse_excursion_pct),
    percentile_cont(0.75) within group(order by o.max_adverse_excursion_pct),
    percentile_cont(0.5) within group(order by o.max_favorable_excursion_pct),
    percentile_cont(0.90) within group(order by o.max_favorable_excursion_pct)
  into
    v_history_n,
    v_median_mae,
    v_p75_mae,
    v_median_mfe,
    v_p90_mfe
  from public.alpha_hunter_strategy_forward_outcomes_v01 o
  where o.horizon_hours=24
    and o.strategy_id=new.strategy_id
    and o.direction=new.direction
    and o.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
    and o.path_measurement_quality='COMPLETE_ENOUGH'
    and o.ordering_ambiguous=false
    and o.evaluated_at_utc<=new.frozen_at_utc
    and o.max_adverse_excursion_pct is not null
    and o.max_favorable_excursion_pct is not null;

  v_stop_inside :=
    case
      when v_history_n>=v_spec.minimum_history_n and v_median_mae is not null
        then v_stop_pct<v_median_mae
      else null
    end;

  v_target_beyond :=
    case
      when v_history_n>=v_spec.minimum_history_n and v_p90_mfe is not null
        then v_target_pct>v_p90_mfe
      else null
    end;

  v_cost_fragile :=
    case
      when v_cost_r is not null
        then v_cost_r>v_spec.cost_fragile_threshold_r
      else null
    end;

  v_health :=
    case
      when v_history_n<v_spec.minimum_history_n
        then 'INSUFFICIENT_HISTORY'
      when v_stop_inside is true and v_target_beyond is true and v_cost_fragile is true
        then 'STOP_TARGET_AND_COST_FRAGILE'
      when v_stop_inside is true and v_target_beyond is true
        then 'STOP_TIGHT_TARGET_BEYOND_P90'
      when v_stop_inside is true and v_cost_fragile is true
        then 'STOP_AND_COST_FRAGILE'
      when v_target_beyond is true and v_cost_fragile is true
        then 'TARGET_AND_COST_FRAGILE'
      when v_stop_inside is true
        then 'STOP_INSIDE_MEDIAN_MAE'
      when v_target_beyond is true
        then 'TARGET_BEYOND_P90_MFE'
      when v_cost_fragile is true
        then 'COST_FRAGILE'
      else 'GEOMETRY_PLAUSIBLE_SHADOW'
    end;

  insert into private.alpha_hunter_payoff_geometry_health_observations_v01(
    geometry_health_id,spec_id,execution_event_id,decision_observation_id,
    strategy_instance_id,run_id,symbol,strategy_id,direction,action,
    decision_observed_at_utc,frozen_at_utc,
    planned_entry_price,stop_price,target_price,reward_risk,
    stop_distance_pct,target_distance_pct,
    descriptive_cost_floor_bps,descriptive_cost_r,
    history_n,historical_median_mae_pct,historical_p75_mae_pct,
    historical_median_mfe_pct,historical_p90_mfe_pct,
    stop_inside_median_mae,target_beyond_p90_mfe,cost_fragile,
    geometry_health,reasons,evidence,
    shadow_only,trade_permission,threshold_change_permitted,
    production_promotion_permitted,order_path
  ) values (
    'payoff-geometry-'||md5(v_spec.spec_id||'|'||new.execution_event_id),
    v_spec.spec_id,new.execution_event_id,new.decision_observation_id,
    new.strategy_instance_id,new.decision_run_id,new.symbol,new.strategy_id,
    new.direction,new.action,new.decision_observed_at_utc,new.frozen_at_utc,
    new.planned_entry_price,new.stop_price,new.target_price,new.reward_risk,
    v_stop_pct,v_target_pct,v_cost_floor_bps,v_cost_r,
    v_history_n,v_median_mae,v_p75_mae,v_median_mfe,v_p90_mfe,
    v_stop_inside,v_target_beyond,v_cost_fragile,v_health,
    jsonb_build_object(
      'stop_inside_median_mae',v_stop_inside,
      'target_beyond_p90_mfe',v_target_beyond,
      'cost_fragile',v_cost_fragile
    ),
    jsonb_build_object(
      'model_version','payoff-geometry-health-v0.1',
      'history_cutoff_at_decision_utc',new.frozen_at_utc,
      'cost_floor_is_validated_model',false,
      'cost_floor_assumption','DESCRIPTIVE_MEDIAN_TAKER_ROUND_TRIP_FLOOR',
      'trade_gate_applied',false,
      'production_selector_changed',false
    ),
    true,false,false,false,'NONE'
  )
  on conflict(execution_event_id) do nothing;

  return new;
end;
$function$
;
-- Source catalog function sha md5 b2e7875f08bd146358181dd606181e93
CREATE OR REPLACE FUNCTION private.alpha_hunter_capture_snapshot_slim_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  insert into private.alpha_hunter_snapshot_slim_v01(
    run_id,collected_at_utc,payload,captured_at_utc
  ) values (
    new.run_id,
    new.collected_at_utc,
    jsonb_build_object(
      'validation_identity',coalesce(new.payload->'validation_identity','{}'::jsonb),
      'previous_snapshot_context',coalesce(new.payload->'previous_snapshot_context','{}'::jsonb),
      'catalyst_summary',coalesce(new.payload->'catalyst_summary','{}'::jsonb),
      'multi_strategy_summary',coalesce(new.payload->'multi_strategy_summary','{}'::jsonb)
    ),
    clock_timestamp()
  )
  on conflict(run_id) do update
  set
    collected_at_utc=excluded.collected_at_utc,
    payload=excluded.payload,
    captured_at_utc=excluded.captured_at_utc;
  return new;
end;
$function$
;
-- Source catalog function sha md5 c05fc276562bba077d3ca48a88b3a3a1
CREATE OR REPLACE FUNCTION private.alpha_hunter_create_calibrated_paper_order_v02()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  p private.alpha_hunter_calibrated_paper_policy_v01%rowtype;
  sf public.alpha_hunter_signal_features%rowtype;
  so public.alpha_hunter_strategy_observations_v01%rowtype;
  v_active integer;
  v_state text;
  v_fill_status text;
  v_fill_price double precision;
  v_fill_at timestamptz;
  v_fill_source text;
begin
  select * into p
  from private.alpha_hunter_calibrated_paper_policy_v01
  where status='ACTIVE'
  order by updated_at desc
  limit 1;

  if p.policy_id is null then
    return new;
  end if;

  if new.spec_id<>'SEALED-ARCH-V14R3-FP-20M-20260929'
     or new.direction<>'SHORT'
     or new.action not in ('EXECUTE_NOW','PLACE_LIMIT')
     or new.reward_risk is null
     or new.reward_risk<p.minimum_reward_risk
     or new.planned_entry_price is null
     or new.stop_price is null
     or new.target_price is null
     or not (
       new.target_price<new.planned_entry_price
       and new.planned_entry_price<new.stop_price
     )
  then
    return new;
  end if;

  select * into sf
  from public.alpha_hunter_signal_features x
  where x.run_id=new.decision_run_id
    and upper(x.symbol)=upper(new.symbol)
  order by abs(
    extract(epoch from(x.captured_at_utc-new.decision_observed_at_utc))
  ) asc
  limit 1;

  if sf.signal_id is null
     or sf.state<>'WATCH_SHORT'
     or sf.trend_1h<>'BEARISH'
     or sf.trend_4h<>'NEUTRAL'
     or sf.btc_regime<>'BTC_NEUTRAL'
     or sf.liquidity_state<>'GOOD'
     or sf.volume_expansion is distinct from false
  then
    return new;
  end if;

  select * into so
  from public.alpha_hunter_strategy_observations_v01 s
  where s.observation_id=new.decision_observation_id
  limit 1;

  if so.observation_id is null or so.strategy_instance_id is null then
    return new;
  end if;

  select count(*) into v_active
  from private.alpha_hunter_calibrated_paper_orders_v01
  where state in ('PENDING_LIMIT_PAPER','OPEN_PAPER');

  if v_active>=p.max_active_paper_orders then
    return new;
  end if;

  if new.action='EXECUTE_NOW' then
    if new.quote_complete is not true
       or new.entry_cross_price is null
       or new.entry_cross_price<=0
    then
      return new;
    end if;

    v_state:='OPEN_PAPER';
    v_fill_status:='FILLED_EXECUTE_NOW_AT_CROSS';
    v_fill_price:=new.entry_cross_price::double precision;
    v_fill_at:=coalesce(new.decision_captured_at_utc,new.frozen_at_utc);
    v_fill_source:='IMMUTABLE_DECISION_QUOTE_ENTRY_CROSS';
  else
    v_state:='PENDING_LIMIT_PAPER';
    v_fill_status:='PENDING_LIMIT';
    v_fill_price:=null;
    v_fill_at:=null;
    v_fill_source:='AWAIT_FORWARD_LIMIT_TRIGGER';
  end if;

  insert into private.alpha_hunter_calibrated_paper_orders_v01(
    paper_order_id,policy_id,execution_event_id,decision_observation_id,
    strategy_instance_id,run_id,symbol,strategy_id,direction,action,
    decision_observed_at_utc,frozen_at_utc,planned_entry_price,stop_price,target_price,
    reward_risk,calibrated_confidence_pct,confidence_lower_95_pct,
    confidence_upper_95_pct,calibration_cohort,state,
    paper_fill_status,paper_fill_price,paper_fill_at_utc,paper_fill_source,
    paper_entry_half_spread_bps,paper_execution_evidence,
    paper_only,live_exchange_order_sent,trade_permission
  ) values (
    'cal-paper-'||md5(p.policy_id||'|'||new.execution_event_id),
    p.policy_id,new.execution_event_id,new.decision_observation_id,
    so.strategy_instance_id,new.decision_run_id,new.symbol,so.strategy_id,
    new.direction,new.action,new.decision_observed_at_utc,new.frozen_at_utc,
    new.planned_entry_price,new.stop_price,new.target_price,new.reward_risk,
    p.calibrated_confidence_pct,p.confidence_lower_95_pct,p.confidence_upper_95_pct,
    p.cohort,v_state,
    v_fill_status,v_fill_price,v_fill_at,v_fill_source,
    new.entry_cross_half_spread_bps::double precision,
    jsonb_build_object(
      'execution_model_version','realistic-paper-execution-v0.1',
      'decision_quote_complete',new.quote_complete,
      'decision_entry_cross_price',new.entry_cross_price,
      'decision_midpoint',new.midpoint,
      'decision_best_bid',new.best_bid,
      'decision_best_ask',new.best_ask,
      'paper_fill_hindsight_permitted',false,
      'live_exchange_order_sent',false,
      'validated_net_cost_model_available',false
    ),
    true,false,false
  )
  on conflict(execution_event_id) do nothing;

  return new;
end;
$function$
;
-- Source catalog function sha md5 0c182ed495711252abb96d40f3515a9e
CREATE OR REPLACE FUNCTION private.alpha_hunter_guard_r10_profitability_activation_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare
  role_name text;
  exec_row public.alpha_hunter_paper_execution_activation_v10%rowtype;
begin
  select s.scientific_role into role_name
  from public.alpha_hunter_profitability_test_specs_v01 s
  where s.spec_id=new.spec_id;

  if role_name is distinct from 'SUCCESSOR_EXECUTED_PAPER_24H_R10' then
    return new;
  end if;

  select e.* into exec_row
  from public.alpha_hunter_paper_execution_activation_v10 e
  where e.spec_id=new.spec_id
  limit 1;

  if exec_row.activation_id is null then
    return null;
  end if;

  if new.started_at_utc is distinct from exec_row.activated_at_utc then
    raise exception 'R10 profitability activation timestamp must match paper execution activation';
  end if;

  if coalesce(new.baseline_scientific_fingerprint_sha256,'')
     <>exec_row.scientific_fingerprint_sha256 then
    raise exception 'R10 profitability activation fingerprint must match paper execution activation';
  end if;

  return new;
end;
$function$
;
-- Source catalog function sha md5 ad067d0d796d2a42e981531b1714e782
CREATE OR REPLACE FUNCTION private.alpha_hunter_guard_r8_profitability_activation_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_exec public.alpha_hunter_paper_execution_integrity_activation_v08%rowtype;
begin
  if new.spec_id<>'SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003' then
    return new;
  end if;

  select e.* into v_exec
  from public.alpha_hunter_paper_execution_integrity_activation_v08 e
  where e.activation_id='PAPER_EXECUTION_R8'
  order by e.activated_at_utc desc
  limit 1;

  -- Generic activation remains fail-closed and quiet until the dedicated
  -- atomic R8 activation has created the matching execution row.
  if v_exec.activation_id is null then
    return null;
  end if;

  if v_exec.activated_at_utc<>new.started_at_utc then
    raise exception
      'R8 profitability activation timestamp must match paper execution activation';
  end if;

  if coalesce(v_exec.scientific_fingerprint_sha256,'')
     <>coalesce(new.baseline_scientific_fingerprint_sha256,'')
  then
    raise exception
      'R8 profitability activation fingerprint must match paper execution activation';
  end if;

  return new;
end;
$function$
;
-- Source catalog function sha md5 09d8c61feb762c1e35f7c6b9deeb23dd
CREATE OR REPLACE FUNCTION private.alpha_hunter_guard_r9_activation_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare e public.alpha_hunter_paper_execution_activation_v09%rowtype;
begin
 if new.spec_id<>'SEALED-ARCH-V14R9-EXEC-PAPER-24H-20261004' then return new; end if;
 select * into e from public.alpha_hunter_paper_execution_activation_v09
 where activation_id='PAPER_EXECUTION_R9';
 if e.activation_id is null then return null; end if;
 if new.started_at_utc<>e.activated_at_utc
   or new.baseline_scientific_fingerprint_sha256<>e.scientific_fingerprint_sha256 then
   raise exception 'R9 activation identity must align atomically'; end if;
 return new;
end; $function$
;
-- Source catalog function sha md5 5dde00a0e79d2343e91dd1bbf3ac5365
CREATE OR REPLACE FUNCTION private.alpha_hunter_materialize_account_ledger_from_snapshot()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_private jsonb := coalesce(new.payload->'private_account','{}'::jsonb);
  v_scanner_status text;
  v_account_snapshot_id text;
  v_usdt_account jsonb;
  v_positions jsonb := '[]'::jsonb;
  v_position_count integer := 0;
  v_claimed_position_count integer;
  v_invalid_positions integer := 0;
  v_distinct_positions integer := 0;
  v_schema_errors jsonb := '[]'::jsonb;
  v_schema_validated boolean := false;
  v_complete boolean := false;
  v_connection_status text := 'DATA_INSUFFICIENT';
  v_event_status text := 'MATERIALIZED_INSUFFICIENT';
  v_equity double precision;
  v_available double precision;
  v_unrealized double precision;
  v_locked text;
begin
  v_account_snapshot_id := substr(
    encode(
      extensions.digest(
        'canonical-account-ledger-v0.1|' || new.run_id,
        'sha256'
      ),
      'hex'
    ),
    1,
    32
  );

  if jsonb_typeof(v_private) <> 'object' then
    v_private := '{}'::jsonb;
    v_schema_errors := v_schema_errors || jsonb_build_array('PRIVATE_ACCOUNT_NOT_OBJECT');
  end if;

  v_scanner_status := upper(coalesce(nullif(v_private->>'status',''),'MISSING'));

  if v_scanner_status = 'CONNECTED' then
    if jsonb_typeof(v_private->'accounts') <> 'array' then
      v_schema_errors := v_schema_errors || jsonb_build_array('ACCOUNTS_NOT_LIST');
    else
      select a.value into v_usdt_account
      from jsonb_array_elements(v_private->'accounts') a(value)
      where jsonb_typeof(a.value)='object'
        and upper(coalesce(a.value->>'margin_coin',''))='USDT'
      limit 1;

      if v_usdt_account is null then
        v_schema_errors := v_schema_errors || jsonb_build_array('USDT_ACCOUNT_MISSING');
      else
        v_equity := private.alpha_hunter_text_float(v_usdt_account->>'account_equity');
        v_available := private.alpha_hunter_text_float(v_usdt_account->>'available');
        v_unrealized := private.alpha_hunter_text_float(v_usdt_account->>'unrealized_pl');
        v_locked := v_usdt_account->>'locked';

        if v_equity is null then
          v_schema_errors := v_schema_errors || jsonb_build_array('ACCOUNT_ACCOUNT_EQUITY_INVALID');
        end if;
        if v_available is null then
          v_schema_errors := v_schema_errors || jsonb_build_array('ACCOUNT_AVAILABLE_INVALID');
        end if;
        if v_unrealized is null then
          v_schema_errors := v_schema_errors || jsonb_build_array('ACCOUNT_UNREALIZED_PL_INVALID');
        end if;
      end if;
    end if;

    if jsonb_typeof(v_private->'open_positions') <> 'array' then
      v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITIONS_NOT_LIST');
    else
      v_positions := v_private->'open_positions';
      v_position_count := jsonb_array_length(v_positions);

      if coalesce(v_private->>'open_position_count','') ~ '^[0-9]+$' then
        v_claimed_position_count := (v_private->>'open_position_count')::integer;
        if v_claimed_position_count <> v_position_count then
          v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITION_COUNT_CLAIM_MISMATCH');
        end if;
      else
        v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITION_COUNT_CLAIM_INVALID');
      end if;

      select count(*)::integer into v_invalid_positions
      from jsonb_array_elements(v_positions) p(value)
      where jsonb_typeof(p.value)<>'object'
         or nullif(upper(coalesce(p.value->>'symbol','')),'') is null
         or lower(coalesce(p.value->>'hold_side','')) not in ('long','short')
         or private.alpha_hunter_text_float(p.value->>'total') is null
         or private.alpha_hunter_text_float(p.value->>'total')=0;

      if v_invalid_positions > 0 then
        v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITION_SCHEMA_INVALID');
      end if;

      select count(distinct (
        upper(coalesce(p.value->>'symbol','')) || '|' || lower(coalesce(p.value->>'hold_side',''))
      ))::integer into v_distinct_positions
      from jsonb_array_elements(v_positions) p(value)
      where jsonb_typeof(p.value)='object';

      if v_distinct_positions <> v_position_count then
        v_schema_errors := v_schema_errors || jsonb_build_array('OPEN_POSITION_DUPLICATE_SYMBOL_DIRECTION');
      end if;
    end if;

    v_schema_validated := jsonb_array_length(v_schema_errors)=0;
    v_complete := v_schema_validated;
    if v_complete then
      v_connection_status := 'CONNECTED_READ_ONLY';
      v_event_status := 'MATERIALIZED_CONNECTED';
    else
      v_connection_status := 'DATA_INSUFFICIENT';
      v_event_status := 'MATERIALIZED_INSUFFICIENT';
    end if;

  elsif v_scanner_status = 'NOT_CONFIGURED' then
    v_connection_status := 'DISCONNECTED';
    v_schema_errors := v_schema_errors || jsonb_build_array('PRIVATE_API_NOT_CONFIGURED');
    v_event_status := 'MATERIALIZED_DISCONNECTED';
  else
    v_connection_status := 'DATA_INSUFFICIENT';
    v_schema_errors := v_schema_errors || jsonb_build_array(
      'SCANNER_PRIVATE_ACCOUNT_STATUS_' || v_scanner_status
    );
    v_event_status := 'MATERIALIZED_INSUFFICIENT';
  end if;

  insert into public.alpha_hunter_account_state_snapshots(
    account_snapshot_id,captured_at_utc,equity_usdt,available_usdt,margin_used_usdt,
    unrealized_pnl_usdt,daily_realized_pnl_usdt,source,connection_status,
    schema_validated,complete,evidence,shadow_only,trade_permission
  ) values (
    v_account_snapshot_id,
    new.collected_at_utc,
    case when v_complete then v_equity end,
    case when v_complete then v_available end,
    null,
    case when v_complete then v_unrealized end,
    null,
    'CANONICAL_SCANNER_PRIVATE_ACCOUNT_CACHE',
    v_connection_status,
    v_schema_validated,
    v_complete,
    jsonb_build_object(
      'model_version','canonical-account-ledger-v0.1',
      'materialization_model_version','canonical-account-ledger-materialization-v0.1',
      'canonical_run_id',new.run_id,
      'scanner_private_account_status',v_scanner_status,
      'account_count',case when jsonb_typeof(v_private->'accounts')='array' then jsonb_array_length(v_private->'accounts') else null end,
      'scanner_open_position_count',v_private->'open_position_count',
      'persisted_open_position_count',case when v_complete then v_position_count else 0 end,
      'api_permission_probe_status',v_private->>'api_permission_probe_status',
      'api_permission_probe_error',v_private->>'api_permission_probe_error',
      'api_permission_type',v_private->>'api_permission_type',
      'api_permissions',case when jsonb_typeof(v_private->'api_permissions')='array' then v_private->'api_permissions' else '[]'::jsonb end,
      'permission_metadata_is_trade_authority',false,
      'locked_observed',case when v_usdt_account is null then null else v_locked end,
      'margin_used_inferred_from_locked',false,
      'daily_realized_pnl_invented',false,
      'protection_observation_status',v_private->>'protection_observation_status',
      'protection_observation_error',v_private->>'protection_observation_error',
      'protection_observation_source',v_private->>'protection_observation_source',
      'pending_tpsl_order_count',v_private->'pending_tpsl_order_count',
      'schema_errors',v_schema_errors,
      'no_extra_bitget_request',true,
      'cached_payload_only',true,
      'materialized_at_snapshot_insert',true
    ),
    true,
    false
  ) on conflict(account_snapshot_id) do nothing;

  if v_complete and v_position_count>0 then
    insert into public.alpha_hunter_open_position_snapshots(
      position_snapshot_id,account_snapshot_id,captured_at_utc,symbol,direction,quantity,
      average_entry,mark_price,liquidation_price,notional_usdt,unrealized_pnl_usdt,
      source_position_id,structural_stop_price,planned_risk_usdt,strategy_event_id,
      source_order_intent_id,evidence,shadow_only,trade_permission
    )
    select
      substr(
        encode(
          extensions.digest(
            'canonical-account-ledger-v0.1|' || v_account_snapshot_id || '|' ||
            upper(p.value->>'symbol') || '|' ||
            case lower(p.value->>'hold_side') when 'long' then 'LONG' else 'SHORT' end,
            'sha256'
          ),
          'hex'
        ),
        1,
        32
      ),
      v_account_snapshot_id,
      new.collected_at_utc,
      upper(p.value->>'symbol'),
      case lower(p.value->>'hold_side') when 'long' then 'LONG' else 'SHORT' end,
      abs(private.alpha_hunter_text_float(p.value->>'total')),
      private.alpha_hunter_text_float(p.value->>'open_price_avg'),
      private.alpha_hunter_text_float(p.value->>'mark_price'),
      private.alpha_hunter_text_float(p.value->>'liquidation_price'),
      null,
      private.alpha_hunter_text_float(p.value->>'unrealized_pl'),
      null,
      null,
      null,
      null,
      null,
      jsonb_build_object(
        'source','CANONICAL_SCANNER_PRIVATE_ACCOUNT_CACHE',
        'margin_mode',p.value->>'margin_mode',
        'leverage',p.value->>'leverage',
        'available_quantity',p.value->>'available',
        'break_even_price',p.value->>'break_even_price',
        'exchange_take_profit_observed',p.value->>'take_profit',
        'exchange_stop_loss_observed',p.value->>'stop_loss',
        'exchange_take_profit_source',p.value->>'take_profit_source',
        'exchange_stop_loss_source',p.value->>'stop_loss_source',
        'exchange_protection_observation_status',p.value->>'protection_observation_status',
        'exchange_protection_observation_error',p.value->>'protection_observation_error',
        'exchange_protection_orders_observed',
          case
            when jsonb_typeof(p.value->'protection_orders')='array'
              then p.value->'protection_orders'
            else '[]'::jsonb
          end,
        'exchange_protection_absence_confirmed',
          (
            p.value->>'protection_observation_status'='CONNECTED'
            and nullif(btrim(coalesce(p.value->>'take_profit','')),'') is null
            and nullif(btrim(coalesce(p.value->>'stop_loss','')),'') is null
            and case
                  when jsonb_typeof(p.value->'protection_orders')='array'
                    then jsonb_array_length(p.value->'protection_orders')=0
                  else true
                end
          ),
        'structural_stop_inferred_from_exchange_stop',false,
        'planned_risk_invented',false,
        'notional_invented',false,
        'no_extra_bitget_request',true,
        'materialized_at_snapshot_insert',true
      ),
      true,
      false
    from jsonb_array_elements(v_positions) p(value)
    on conflict(position_snapshot_id) do nothing;
  end if;

  insert into public.alpha_hunter_account_ledger_materialization_events(
    event_id,run_id,captured_at_utc,status,account_snapshot_id,details,
    model_version,shadow_only,trade_permission
  ) values (
    substr(
      encode(
        extensions.digest(
          'canonical-account-ledger-materialization-v0.1|' || new.run_id,
          'sha256'
        ),
        'hex'
      ),
      1,
      32
    ),
    new.run_id,
    new.collected_at_utc,
    v_event_status,
    v_account_snapshot_id,
    jsonb_build_object(
      'scanner_private_account_status',v_scanner_status,
      'connection_status',v_connection_status,
      'schema_validated',v_schema_validated,
      'complete',v_complete,
      'schema_errors',v_schema_errors,
      'position_count',case when v_complete then v_position_count else 0 end,
      'api_permission_probe_status',v_private->>'api_permission_probe_status',
      'api_permission_type',v_private->>'api_permission_type',
      'protection_observation_status',v_private->>'protection_observation_status',
      'pending_tpsl_order_count',v_private->'pending_tpsl_order_count',
      'permission_metadata_is_trade_authority',false,
      'snapshot_persistence_preserved',true,
      'no_exchange_call',true
    ),
    'canonical-account-ledger-materialization-v0.1',
    true,
    false
  ) on conflict(event_id) do nothing;

  return new;
exception when others then
  -- Account-ledger failure must never destroy the canonical market snapshot.
  begin
    insert into public.alpha_hunter_account_ledger_materialization_events(
      event_id,run_id,captured_at_utc,status,account_snapshot_id,details,
      model_version,shadow_only,trade_permission
    ) values (
      substr(
        encode(
          extensions.digest(
            'canonical-account-ledger-materialization-v0.1|' || new.run_id,
            'sha256'
          ),
          'hex'
        ),
        1,
        32
      ),
      new.run_id,
      new.collected_at_utc,
      'FAILED',
      v_account_snapshot_id,
      jsonb_build_object(
        'sqlstate',sqlstate,
        'error',left(sqlerrm,1000),
        'snapshot_persistence_preserved',true,
        'readiness_fail_closed',true,
        'no_exchange_call',true
      ),
      'canonical-account-ledger-materialization-v0.1',
      true,
      false
    ) on conflict(event_id) do nothing;
  exception when others then
    null;
  end;
  return new;
end;
$function$
;
-- Source catalog function sha md5 c27ec2afb598d3e7950374527ab5941f
CREATE OR REPLACE FUNCTION private.alpha_hunter_materialize_profit_management_forward_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_activated_at timestamptz;
  v_current_source text;
  v_prev_account_id text;
  v_prev_position_id text;
  v_prev_average_entry double precision;
  v_prev_quantity double precision;
  v_anchor_episode_id text;
  v_anchor_episode_started_at timestamptz;
  v_anchor_entry_price double precision;
  v_anchor_initial_quantity double precision;
  v_continuity_status text;
  v_entry_changed boolean := false;
  v_quantity_changed boolean := false;
  v_entry_tolerance double precision;

  v_policy record;
  v_prev_policy public.alpha_hunter_profit_management_forward_v01%rowtype;

  v_running_favorable_mark double precision;
  v_running_favorable_pct double precision;
  v_policy_active boolean;
  v_policy_activated_at timestamptz;
  v_shadow_stop double precision;
  v_shadow_state text;
  v_trigger_now boolean;
  v_trigger_at timestamptz;
  v_trigger_mark double precision;
  v_trigger_stop double precision;
  v_observation_id text;
begin
  select c.activated_at_utc
    into v_activated_at
  from public.alpha_hunter_profit_management_forward_config_v01 c
  where c.config_id='profit-management-forward-v0.1';

  if v_activated_at is null or new.captured_at_utc < v_activated_at then
    return new;
  end if;

  if new.direction not in ('LONG','SHORT')
     or new.average_entry is null
     or new.average_entry <= 0
     or new.mark_price is null
     or new.mark_price <= 0
     or new.quantity is null
     or new.quantity <= 0 then
    return new;
  end if;

  select a.source
    into v_current_source
  from public.alpha_hunter_account_state_snapshots a
  where a.account_snapshot_id=new.account_snapshot_id;

  select a.account_snapshot_id
    into v_prev_account_id
  from public.alpha_hunter_account_state_snapshots a
  where a.captured_at_utc < new.captured_at_utc
    and (
      v_current_source is null
      or a.source is not distinct from v_current_source
    )
  order by a.captured_at_utc desc,a.account_snapshot_id desc
  limit 1;

  if v_prev_account_id is not null then
    select
      p.position_snapshot_id,
      p.average_entry,
      p.quantity
    into
      v_prev_position_id,
      v_prev_average_entry,
      v_prev_quantity
    from public.alpha_hunter_open_position_snapshots p
    where p.account_snapshot_id=v_prev_account_id
      and p.symbol=new.symbol
      and p.direction=new.direction
    order by p.position_snapshot_id
    limit 1;
  end if;

  if v_prev_position_id is null then
    v_continuity_status := 'NEW_FORWARD_EPISODE';

  else
    v_entry_tolerance := greatest(
      1e-9,
      abs(new.average_entry)*1e-8,
      abs(coalesce(v_prev_average_entry,new.average_entry))*1e-8
    );

    v_entry_changed := (
      v_prev_average_entry is null
      or abs(new.average_entry-v_prev_average_entry) > v_entry_tolerance
    );

    v_quantity_changed := (
      v_prev_quantity is null
      or abs(new.quantity-v_prev_quantity)
        > greatest(
            1e-9,
            abs(new.quantity)*1e-8,
            abs(coalesce(v_prev_quantity,new.quantity))*1e-8
          )
    );

    if v_entry_changed then
      v_continuity_status := 'ENTRY_CHANGED_RESTART';
    else
      select
        f.episode_id,
        f.episode_started_at_utc,
        f.episode_entry_price,
        f.episode_initial_quantity
      into
        v_anchor_episode_id,
        v_anchor_episode_started_at,
        v_anchor_entry_price,
        v_anchor_initial_quantity
      from public.alpha_hunter_profit_management_forward_v01 f
      where f.position_snapshot_id=v_prev_position_id
      order by f.policy_id
      limit 1;

      if v_anchor_episode_id is null then
        v_continuity_status := 'FORWARD_ANCHOR_MISSING_RESTART';
      else
        v_continuity_status := 'CONTINUED_FROM_PREVIOUS_ACCOUNT_SNAPSHOT';
      end if;
    end if;
  end if;

  if v_continuity_status <> 'CONTINUED_FROM_PREVIOUS_ACCOUNT_SNAPSHOT' then
    v_anchor_episode_id := substr(
      encode(
        extensions.digest(
          'profit-management-forward-v0.1|episode|' || new.position_snapshot_id,
          'sha256'
        ),
        'hex'
      ),
      1,
      32
    );
    v_anchor_episode_started_at := new.captured_at_utc;
    v_anchor_entry_price := new.average_entry;
    v_anchor_initial_quantity := new.quantity;
  end if;

  for v_policy in
    select *
    from (
      values
        (
          'BE_AFTER_3PCT'::text,
          3.0::double precision,
          0.0::double precision,
          'EXISTING_LIFECYCLE_3PCT_MILESTONE'::text
        ),
        (
          'LOCK_25_AFTER_5PCT'::text,
          5.0::double precision,
          0.25::double precision,
          'EXISTING_LIFECYCLE_5PCT_MILESTONE'::text
        ),
        (
          'LOCK_50_AFTER_5PCT'::text,
          5.0::double precision,
          0.50::double precision,
          'EXISTING_LIFECYCLE_5PCT_MILESTONE'::text
        )
    ) as p(policy_id,activation_favorable_pct,lock_fraction,threshold_basis)
  loop
    v_prev_policy := null;

    if v_continuity_status='CONTINUED_FROM_PREVIOUS_ACCOUNT_SNAPSHOT' then
      select f.*
        into v_prev_policy
      from public.alpha_hunter_profit_management_forward_v01 f
      where f.position_snapshot_id=v_prev_position_id
        and f.policy_id=v_policy.policy_id
      limit 1;
    end if;

    if v_prev_policy.observation_id is not null
       and v_prev_policy.shadow_state='TRIGGERED' then
      -- Once the shadow policy has exited, freeze its terminal evidence while
      -- the real position may continue to exist.
      v_running_favorable_mark := v_prev_policy.running_favorable_mark;
      v_running_favorable_pct := v_prev_policy.running_favorable_pct;
      v_policy_active := true;
      v_policy_activated_at := v_prev_policy.policy_activated_at_utc;
      v_shadow_stop := v_prev_policy.shadow_stop_price;
      v_shadow_state := 'TRIGGERED';
      v_trigger_now := false;
      v_trigger_at := v_prev_policy.shadow_trigger_at_utc;
      v_trigger_mark := v_prev_policy.shadow_trigger_observed_mark;
      v_trigger_stop := v_prev_policy.shadow_stop_at_trigger;

    else
      if v_prev_policy.observation_id is not null then
        if new.direction='LONG' then
          v_running_favorable_mark := greatest(
            v_prev_policy.running_favorable_mark,
            new.mark_price
          );
        else
          v_running_favorable_mark := least(
            v_prev_policy.running_favorable_mark,
            new.mark_price
          );
        end if;
      else
        v_running_favorable_mark := new.mark_price;
      end if;

      if new.direction='LONG' then
        v_running_favorable_pct :=
          100.0*(v_running_favorable_mark-v_anchor_entry_price)
          /v_anchor_entry_price;
      else
        v_running_favorable_pct :=
          100.0*(v_anchor_entry_price-v_running_favorable_mark)
          /v_anchor_entry_price;
      end if;

      v_policy_active := coalesce(v_prev_policy.policy_active,false)
        or v_running_favorable_pct >= v_policy.activation_favorable_pct;

      v_policy_activated_at := case
        when v_prev_policy.policy_activated_at_utc is not null
          then v_prev_policy.policy_activated_at_utc
        when v_policy_active
          then new.captured_at_utc
        else null
      end;

      if v_policy_active then
        if new.direction='LONG' then
          v_shadow_stop :=
            v_anchor_entry_price
            + v_policy.lock_fraction
              *(v_running_favorable_mark-v_anchor_entry_price);
        else
          v_shadow_stop :=
            v_anchor_entry_price
            - v_policy.lock_fraction
              *(v_anchor_entry_price-v_running_favorable_mark);
        end if;
      else
        v_shadow_stop := null;
      end if;

      v_trigger_now := (
        v_policy_active
        and v_shadow_stop is not null
        and (
          (new.direction='LONG' and new.mark_price <= v_shadow_stop)
          or
          (new.direction='SHORT' and new.mark_price >= v_shadow_stop)
        )
      );

      if v_trigger_now then
        v_shadow_state := 'TRIGGERED';
        v_trigger_at := new.captured_at_utc;
        v_trigger_mark := new.mark_price;
        v_trigger_stop := v_shadow_stop;
      elsif v_policy_active then
        v_shadow_state := 'ACTIVE';
        v_trigger_at := null;
        v_trigger_mark := null;
        v_trigger_stop := null;
      else
        v_shadow_state := 'INACTIVE';
        v_trigger_at := null;
        v_trigger_mark := null;
        v_trigger_stop := null;
      end if;
    end if;

    v_observation_id := substr(
      encode(
        extensions.digest(
          'profit-management-forward-v0.1|observation|'
          || new.position_snapshot_id || '|' || v_policy.policy_id,
          'sha256'
        ),
        'hex'
      ),
      1,
      32
    );

    insert into public.alpha_hunter_profit_management_forward_v01(
      observation_id,
      position_snapshot_id,
      account_snapshot_id,
      captured_at_utc,
      episode_id,
      episode_started_at_utc,
      continuity_status,
      previous_position_snapshot_id,
      symbol,
      direction,
      quantity,
      average_entry,
      mark_price,
      episode_entry_price,
      episode_initial_quantity,
      policy_id,
      activation_favorable_pct,
      lock_fraction,
      threshold_basis,
      running_favorable_mark,
      running_favorable_pct,
      policy_active,
      policy_activated_at_utc,
      shadow_stop_price,
      shadow_state,
      trigger_observed_on_this_snapshot,
      shadow_trigger_at_utc,
      shadow_trigger_observed_mark,
      shadow_stop_at_trigger,
      entry_changed_from_previous,
      quantity_changed_from_previous,
      evidence,
      forward_only,
      sampled_mark_limitation,
      counterfactual_fee_claim_permitted,
      counterfactual_funding_claim_permitted,
      counterfactual_net_pnl_claim_permitted,
      management_change_permitted,
      stop_change_permitted,
      target_change_permitted,
      promotion_permitted,
      model_version,
      shadow_only,
      trade_permission,
      order_path
    ) values (
      v_observation_id,
      new.position_snapshot_id,
      new.account_snapshot_id,
      new.captured_at_utc,
      v_anchor_episode_id,
      v_anchor_episode_started_at,
      v_continuity_status,
      v_prev_position_id,
      new.symbol,
      new.direction,
      new.quantity,
      new.average_entry,
      new.mark_price,
      v_anchor_entry_price,
      v_anchor_initial_quantity,
      v_policy.policy_id,
      v_policy.activation_favorable_pct,
      v_policy.lock_fraction,
      v_policy.threshold_basis,
      v_running_favorable_mark,
      v_running_favorable_pct,
      v_policy_active,
      v_policy_activated_at,
      v_shadow_stop,
      v_shadow_state,
      v_trigger_now,
      v_trigger_at,
      v_trigger_mark,
      v_trigger_stop,
      v_entry_changed,
      v_quantity_changed,
      jsonb_build_object(
        'source','CANONICAL_OPEN_POSITION_SNAPSHOT_TRIGGER',
        'account_source',v_current_source,
        'previous_account_snapshot_id',v_prev_account_id,
        'previous_position_snapshot_id',v_prev_position_id,
        'episode_identity_rule',
          'PREVIOUS_ACCOUNT_SNAPSHOT_SAME_SYMBOL_DIRECTION_AND_STABLE_ENTRY',
        'sampled_mark_is_not_tick_path',true,
        'no_historical_backfill',true,
        'no_exchange_call',true
      ),
      true,
      true,
      false,
      false,
      false,
      false,
      false,
      false,
      false,
      'profit-management-forward-v0.1',
      true,
      false,
      'NONE'
    )
    on conflict(position_snapshot_id,policy_id) do nothing;
  end loop;

  return new;

exception when others then
  -- Shadow-monitor failure must never block canonical account evidence.
  return new;
end;
$function$
;
-- Source catalog function sha md5 1eada4dc507cabcc374fd3870c541db6
CREATE OR REPLACE FUNCTION private.alpha_hunter_materialize_protection_reconciliation_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_orders jsonb := case
    when jsonb_typeof(new.evidence->'exchange_protection_orders_observed')='array'
      then new.evidence->'exchange_protection_orders_observed'
    else '[]'::jsonb
  end;
  v_observation_status text := upper(coalesce(
    nullif(new.evidence->>'exchange_protection_observation_status',''),
    'UNKNOWN'
  ));
  v_stop text := nullif(btrim(coalesce(
    new.evidence->>'exchange_stop_loss_observed',''
  )),'');
  v_take text := nullif(btrim(coalesce(
    new.evidence->>'exchange_take_profit_observed',''
  )),'');
  v_stop_source text := nullif(btrim(coalesce(
    new.evidence->>'exchange_stop_loss_source',''
  )),'');
  v_take_source text := nullif(btrim(coalesce(
    new.evidence->>'exchange_take_profit_source',''
  )),'');
  v_stop_order_count integer := 0;
  v_take_order_count integer := 0;
  v_stop_present boolean := false;
  v_take_present boolean := false;
  v_state text := 'UNKNOWN';
  v_gap boolean := false;
begin
  select count(*)::integer into v_stop_order_count
  from jsonb_array_elements(v_orders) o(value)
  where lower(coalesce(o.value->>'plan_type','')) in ('loss_plan','pos_loss');

  select count(*)::integer into v_take_order_count
  from jsonb_array_elements(v_orders) o(value)
  where lower(coalesce(o.value->>'plan_type','')) in ('profit_plan','pos_profit');

  v_stop_present := v_stop is not null or v_stop_order_count > 0;
  v_take_present := v_take is not null or v_take_order_count > 0;
  v_gap := coalesce(v_stop_source,'')='PENDING_TPSL'
        or coalesce(v_take_source,'')='PENDING_TPSL';

  if v_observation_status <> 'CONNECTED' then
    v_state := 'UNKNOWN';
  elsif v_stop_present and v_take_present then
    v_state := 'OBSERVED_BOTH';
  elsif v_stop_present then
    v_state := 'OBSERVED_STOP_ONLY';
  elsif v_take_present then
    v_state := 'OBSERVED_TP_ONLY';
  else
    v_state := 'NONE_OBSERVED';
  end if;

  insert into public.alpha_hunter_protection_reconciliation_events_v01(
    event_id,
    position_snapshot_id,
    account_snapshot_id,
    captured_at_utc,
    symbol,
    direction,
    observation_status,
    protection_state,
    stop_loss_observed,
    take_profit_observed,
    stop_loss_source,
    take_profit_source,
    stop_order_count,
    take_profit_order_count,
    position_field_gap_detected,
    details,
    model_version,
    shadow_only,
    trade_permission
  ) values (
    substr(
      encode(
        extensions.digest(
          'protection-reconciliation-audit-v0.1|' || new.position_snapshot_id,
          'sha256'
        ),
        'hex'
      ),
      1,
      32
    ),
    new.position_snapshot_id,
    new.account_snapshot_id,
    new.captured_at_utc,
    new.symbol,
    new.direction,
    v_observation_status,
    v_state,
    v_stop,
    v_take,
    v_stop_source,
    v_take_source,
    v_stop_order_count,
    v_take_order_count,
    v_gap,
    jsonb_build_object(
      'exchange_protection_absence_confirmed',
        coalesce(
          (new.evidence->>'exchange_protection_absence_confirmed')::boolean,
          false
        ),
      'protection_order_count',jsonb_array_length(v_orders),
      'structural_stop_inferred_from_exchange_stop',
        coalesce(
          (new.evidence->>'structural_stop_inferred_from_exchange_stop')::boolean,
          false
        ),
      'source',new.evidence->>'source',
      'forward_only',true,
      'no_exchange_call',true
    ),
    'protection-reconciliation-audit-v0.1',
    true,
    false
  )
  on conflict(event_id) do nothing;

  return new;
exception when others then
  -- Audit failure must not block canonical position persistence.
  return new;
end;
$function$
;
-- Source catalog function sha md5 bf8640ff428408d181b4efb2a220aa31
CREATE OR REPLACE FUNCTION private.alpha_hunter_text_float(p_value text)
 RETURNS double precision
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
  select case
    when p_value ~ '^-?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' then p_value::double precision
    else null
  end;
$function$
;
CREATE TRIGGER trg_ah_account_materialization_events_append_only BEFORE DELETE OR UPDATE ON public.alpha_hunter_account_ledger_materialization_events FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_account_state_append_only BEFORE DELETE OR UPDATE ON public.alpha_hunter_account_state_snapshots FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_materialize_profit_management_forward_v01 AFTER INSERT ON public.alpha_hunter_open_position_snapshots FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_materialize_profit_management_forward_v01();
CREATE TRIGGER trg_ah_materialize_protection_reconciliation_v01 AFTER INSERT ON public.alpha_hunter_open_position_snapshots FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_materialize_protection_reconciliation_v01();
CREATE TRIGGER trg_ah_open_positions_append_only BEFORE DELETE OR UPDATE ON public.alpha_hunter_open_position_snapshots FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_profit_management_forward_config_append_only_v01 BEFORE DELETE OR UPDATE ON public.alpha_hunter_profit_management_forward_config_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_profit_management_forward_append_only_v01 BEFORE DELETE OR UPDATE ON public.alpha_hunter_profit_management_forward_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_protection_reconciliation_events_append_only BEFORE DELETE OR UPDATE ON public.alpha_hunter_protection_reconciliation_events_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
-- UNRESOLVED ADDENDUM TRIGGER trg_ah_enrich_signal_feature_geometry_context_v01 -> private.alpha_hunter_enrich_signal_feature_geometry_context_v01
CREATE TRIGGER trg_ah_strategy_forward_outcome_append_only_v01 BEFORE DELETE OR UPDATE ON public.alpha_hunter_strategy_forward_outcomes_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();

-- Attach two previously uninstalled parent triggers to new supporting tables.
CREATE TRIGGER trg_ah_capture_snapshot_slim_v01 AFTER INSERT OR UPDATE OF payload ON public.alpha_hunter_snapshots FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_capture_snapshot_slim_v01();
CREATE TRIGGER trg_ah_materialize_account_ledger_from_snapshot AFTER INSERT ON public.alpha_hunter_snapshots FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_materialize_account_ledger_from_snapshot();
