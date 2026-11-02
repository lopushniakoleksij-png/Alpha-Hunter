-- STRICTLY ISOLATED PG16/17 synthetic schema from read-only production catalogs. NO PRODUCTION DATABASE DATA.
CREATE SCHEMA IF NOT EXISTS private;
CREATE TABLE public.alpha_hunter_snapshots (
  "run_id" text NOT NULL,
  "collected_at_utc" timestamp with time zone NOT NULL,
  "version" text NOT NULL,
  "product_type" text NOT NULL,
  "symbol_count" integer NOT NULL,
  "error_count" integer NOT NULL DEFAULT 0,
  "payload" jsonb NOT NULL,
  "created_at" timestamp with time zone NOT NULL DEFAULT now()
);
CREATE TABLE public.alpha_hunter_symbol_snapshots (
  "run_id" text NOT NULL,
  "symbol" text NOT NULL,
  "collected_at_utc" timestamp with time zone NOT NULL,
  "state" text,
  "previous_state" text,
  "state_changed" boolean NOT NULL DEFAULT false,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "direction" text,
  "reward_risk" double precision,
  "last_price" double precision,
  "open_interest" double precision,
  "funding_rate" double precision,
  "data_integrity_score" integer,
  "error" text,
  "payload" jsonb NOT NULL,
  "created_at" timestamp with time zone NOT NULL DEFAULT now()
);
CREATE TABLE public.alpha_hunter_strategy_observations_v01 (
  "observation_id" text NOT NULL,
  "run_id" text NOT NULL,
  "symbol" text NOT NULL,
  "observed_at_utc" timestamp with time zone NOT NULL,
  "strategy_id" text NOT NULL,
  "strategy_name" text,
  "strategy_engine_version" text,
  "status" text NOT NULL,
  "action" text NOT NULL,
  "direction" text,
  "signal_score" double precision,
  "score_is_calibrated" boolean NOT NULL DEFAULT false,
  "reference_price" double precision,
  "entry_price" double precision,
  "stop_price" double precision,
  "target_price" double precision,
  "risk_amount" double precision,
  "reward_amount" double precision,
  "reward_risk" double precision,
  "distance_to_entry_pct" double precision,
  "geometry_valid" boolean NOT NULL DEFAULT false,
  "persistence_state" text,
  "strategy_instance_id" text,
  "first_seen_at_utc" timestamp with time zone,
  "consecutive_scans" integer NOT NULL DEFAULT 0,
  "market_phase" text,
  "opportunity_timing" text,
  "evidence" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "checks" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "reasons" jsonb NOT NULL DEFAULT '[]'::jsonb,
  "strategy_payload" jsonb NOT NULL,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "production_permission" boolean NOT NULL DEFAULT false,
  "production_promotion_permitted" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.alpha_hunter_strategy_episodes_v01 (
  "episode_id" text NOT NULL,
  "symbol" text NOT NULL,
  "strategy_id" text NOT NULL,
  "strategy_name" text,
  "strategy_engine_version" text,
  "direction" text NOT NULL,
  "first_observed_at_utc" timestamp with time zone NOT NULL,
  "first_observation_id" text NOT NULL,
  "first_status" text NOT NULL,
  "first_action" text NOT NULL,
  "first_signal_score" double precision,
  "first_reference_price" double precision,
  "earliest_identifiable_entry_price" double precision,
  "first_stop_price" double precision,
  "first_target_price" double precision,
  "first_risk_amount" double precision,
  "first_reward_amount" double precision,
  "first_reward_risk" double precision,
  "first_geometry_valid" boolean NOT NULL DEFAULT false,
  "first_market_phase" text,
  "first_opportunity_timing" text,
  "first_strategy_payload" jsonb NOT NULL,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "production_permission" boolean NOT NULL DEFAULT false,
  "production_promotion_permitted" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE public.alpha_hunter_shadow_decision_quotes_v01 (
  "observation_id" text NOT NULL,
  "strategy_instance_id" text,
  "run_id" text NOT NULL,
  "symbol" text NOT NULL,
  "strategy_id" text NOT NULL,
  "direction" text NOT NULL,
  "action" text NOT NULL,
  "observed_at_utc" timestamp with time zone NOT NULL,
  "captured_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "run_source" text,
  "git_commit" text,
  "config_sha256" text,
  "reference_price" double precision,
  "planned_entry_price" double precision,
  "best_bid" double precision,
  "best_ask" double precision,
  "midpoint" double precision,
  "spread_pct" double precision,
  "entry_cross_price" double precision,
  "entry_cross_half_spread_bps" double precision,
  "planned_entry_directional_distance_bps" double precision,
  "depth_imbalance" double precision,
  "trade_imbalance" double precision,
  "source_skew_ms" bigint,
  "order_book_exchange_timestamp_ms" bigint,
  "newest_trade_timestamp_ms" bigint,
  "microstructure_status" text,
  "quote_status" text NOT NULL,
  "quote_complete" boolean NOT NULL DEFAULT false,
  "evidence_source" text NOT NULL DEFAULT 'CANONICAL_SYMBOL_SNAPSHOT_MICROSTRUCTURE'::text,
  "prospective_capture" boolean NOT NULL DEFAULT true,
  "slippage_measured" boolean NOT NULL DEFAULT false,
  "fill_claim_permitted" boolean NOT NULL DEFAULT false,
  "cost_model_activation_permitted" boolean NOT NULL DEFAULT false,
  "realistic_net_r_claim_permitted" boolean NOT NULL DEFAULT false,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "production_promotion_permitted" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text
);
CREATE TABLE public.alpha_hunter_profitability_test_specs_v01 (
  "spec_id" text NOT NULL,
  "protocol_version" text NOT NULL DEFAULT 'sealed-profitability-v0.1'::text,
  "frozen_git_commit" text NOT NULL,
  "required_strategy_count" integer NOT NULL DEFAULT 10,
  "required_minimum_rr" double precision NOT NULL DEFAULT 5.0,
  "evaluation_horizon_hours" integer NOT NULL DEFAULT 24,
  "minimum_test_days" integer NOT NULL DEFAULT 30,
  "minimum_completed_paper_trades" integer NOT NULL DEFAULT 100,
  "confidence_z" double precision NOT NULL DEFAULT 1.96,
  "require_validated_cost_model" boolean NOT NULL DEFAULT true,
  "preregistered_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "scientific_role" text NOT NULL DEFAULT 'SEALED_PROFITABILITY_PREREGISTRATION'::text,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "production_promotion_permitted" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "required_run_source" text NOT NULL DEFAULT 'GITHUB_REALTIME_HOURLY'::text,
  "frozen_scientific_fingerprint_sha256" text
);
CREATE TABLE public.alpha_hunter_profitability_test_activations_v01 (
  "spec_id" text NOT NULL,
  "baseline_run_id" text NOT NULL,
  "started_at_utc" timestamp with time zone NOT NULL,
  "baseline_config_sha256" text NOT NULL,
  "baseline_git_commit" text NOT NULL,
  "baseline_previous_snapshot_source" text NOT NULL,
  "baseline_catalyst_version" text NOT NULL,
  "baseline_symbol_rows" integer NOT NULL,
  "baseline_strategy_rows" integer NOT NULL,
  "baseline_microstructure_rows" integer NOT NULL,
  "baseline_closed_candle_rows" integer NOT NULL,
  "activation_checks" jsonb NOT NULL,
  "activated_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "scientific_role" text NOT NULL DEFAULT 'SEALED_PROFITABILITY_ACTIVATION'::text,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "production_promotion_permitted" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "baseline_scientific_fingerprint_sha256" text
);
CREATE TABLE public.alpha_hunter_execution_decision_freezes_v01 (
  "execution_event_id" text NOT NULL,
  "spec_id" text NOT NULL,
  "decision_observation_id" text NOT NULL,
  "strategy_instance_id" text NOT NULL,
  "decision_run_id" text NOT NULL,
  "symbol" text NOT NULL,
  "strategy_id" text NOT NULL,
  "direction" text NOT NULL,
  "action" text NOT NULL,
  "decision_observed_at_utc" timestamp with time zone NOT NULL,
  "decision_captured_at_utc" timestamp with time zone NOT NULL,
  "frozen_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "reference_price" numeric,
  "planned_entry_price" numeric,
  "stop_price" numeric,
  "target_price" numeric,
  "reward_risk" numeric,
  "best_bid" numeric NOT NULL,
  "best_ask" numeric NOT NULL,
  "midpoint" numeric NOT NULL,
  "entry_cross_price" numeric NOT NULL,
  "entry_cross_half_spread_bps" numeric,
  "quote_complete" boolean NOT NULL,
  "prospective_capture" boolean NOT NULL,
  "evidence" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "scientific_role" text NOT NULL DEFAULT 'PROSPECTIVE_EXECUTION_ATTRIBUTION'::text,
  "shadow_only" boolean NOT NULL DEFAULT true,
  "trade_permission" boolean NOT NULL DEFAULT false,
  "production_promotion_permitted" boolean NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamp with time zone NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE private.alpha_hunter_strategy_24h_outcome_queue_v01 (
  "episode_id" text NOT NULL,
  "due_at_utc" timestamp with time zone NOT NULL,
  "status" text NOT NULL DEFAULT 'PENDING'::text,
  "enqueued_at_utc" timestamp with time zone NOT NULL DEFAULT clock_timestamp(),
  "processed_at_utc" timestamp with time zone,
  "attempts" integer NOT NULL DEFAULT 0
);
ALTER TABLE private.alpha_hunter_strategy_24h_outcome_queue_v01 ADD CONSTRAINT "alpha_hunter_strategy_24h_outcome_queue_v01_attempts_check" CHECK ((attempts >= 0));
ALTER TABLE private.alpha_hunter_strategy_24h_outcome_queue_v01 ADD CONSTRAINT "alpha_hunter_strategy_24h_outcome_queue_v01_status_check" CHECK ((status = ANY (ARRAY['PENDING'::text, 'DONE'::text])));
ALTER TABLE private.alpha_hunter_strategy_24h_outcome_queue_v01 ADD CONSTRAINT "alpha_hunter_strategy_24h_outcome_queue_v01_pkey" PRIMARY KEY (episode_id);
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decis_production_promotion_permitt_check" CHECK ((production_promotion_permitted = false));
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_freez_prospective_capture_check" CHECK ((prospective_capture = true));
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_freezes__trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_freezes_v01_action_check" CHECK ((action = ANY (ARRAY['EXECUTE_NOW'::text, 'PLACE_LIMIT'::text])));
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_freezes_v01_check" CHECK ((frozen_at_utc >= decision_captured_at_utc));
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_freezes_v01_direction_check" CHECK ((direction = ANY (ARRAY['LONG'::text, 'SHORT'::text])));
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_freezes_v01_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_freezes_v01_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_freezes_v0_quote_complete_check" CHECK ((quote_complete = true));
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_freezes_v01_pkey" PRIMARY KEY (execution_event_id);
ALTER TABLE public.alpha_hunter_execution_decision_freezes_v01 ADD CONSTRAINT "alpha_hunter_execution_decision_fre_decision_observation_id_key" UNIQUE (decision_observation_id);
ALTER TABLE public.alpha_hunter_profitability_test_activations_v01 ADD CONSTRAINT "alpha_hunter_profitability_t_production_promotion_permit_check1" CHECK ((production_promotion_permitted = false));
ALTER TABLE public.alpha_hunter_profitability_test_activations_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_activati_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_profitability_test_activations_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_activations_v0_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE public.alpha_hunter_profitability_test_activations_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_activations_v_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_profitability_test_activations_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_activations_v01_pkey" PRIMARY KEY (spec_id);
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_t_minimum_completed_paper_trad_check" CHECK ((minimum_completed_paper_trades >= 100));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_t_production_promotion_permitt_check" CHECK ((production_promotion_permitted = false));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_test__evaluation_horizon_hours_check" CHECK ((evaluation_horizon_hours = 24));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_s_required_strategy_count_check" CHECK ((required_strategy_count = 10));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_specs_required_minimum_rr_check" CHECK ((required_minimum_rr >= (5.0)::double precision));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_specs_v01_confidence_z_check" CHECK ((confidence_z >= (1.64)::double precision));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_specs_v01_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_specs_v01_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_specs_v0_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_specs_v_minimum_test_days_check" CHECK ((minimum_test_days >= 30));
ALTER TABLE public.alpha_hunter_profitability_test_specs_v01 ADD CONSTRAINT "alpha_hunter_profitability_test_specs_v01_pkey" PRIMARY KEY (spec_id);
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_cost_model_activation_permit_check" CHECK ((cost_model_activation_permitted = false));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_production_promotion_permitt_check" CHECK ((production_promotion_permitted = false));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_quotes__fill_claim_permitted_check" CHECK ((fill_claim_permitted = false));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_quotes_v01_direction_check" CHECK ((direction = ANY (ARRAY['LONG'::text, 'SHORT'::text])));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_quotes_v01_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_quotes_v01_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_quotes_v01_slippage_measured_check" CHECK ((slippage_measured = false));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_quotes_v01_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_quotes_v_prospective_capture_check" CHECK ((prospective_capture = true));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_realistic_net_r_claim_permit_check" CHECK ((realistic_net_r_claim_permitted = false));
ALTER TABLE public.alpha_hunter_shadow_decision_quotes_v01 ADD CONSTRAINT "alpha_hunter_shadow_decision_quotes_v01_pkey" PRIMARY KEY (observation_id);
ALTER TABLE public.alpha_hunter_snapshots ADD CONSTRAINT "alpha_hunter_snapshots_pkey" PRIMARY KEY (run_id);
ALTER TABLE public.alpha_hunter_strategy_episodes_v01 ADD CONSTRAINT "alpha_hunter_strategy_episod_production_promotion_permitt_check" CHECK ((production_promotion_permitted = false));
ALTER TABLE public.alpha_hunter_strategy_episodes_v01 ADD CONSTRAINT "alpha_hunter_strategy_episodes_v01_direction_check" CHECK ((direction = ANY (ARRAY['LONG'::text, 'SHORT'::text])));
ALTER TABLE public.alpha_hunter_strategy_episodes_v01 ADD CONSTRAINT "alpha_hunter_strategy_episodes_v01_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE public.alpha_hunter_strategy_episodes_v01 ADD CONSTRAINT "alpha_hunter_strategy_episodes_v01_production_permission_check" CHECK ((production_permission = false));
ALTER TABLE public.alpha_hunter_strategy_episodes_v01 ADD CONSTRAINT "alpha_hunter_strategy_episodes_v01_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_strategy_episodes_v01 ADD CONSTRAINT "alpha_hunter_strategy_episodes_v01_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_strategy_episodes_v01 ADD CONSTRAINT "alpha_hunter_strategy_episodes_v01_pkey" PRIMARY KEY (episode_id);
ALTER TABLE public.alpha_hunter_strategy_episodes_v01 ADD CONSTRAINT "alpha_hunter_strategy_episodes_v01_first_observation_id_key" UNIQUE (first_observation_id);
ALTER TABLE public.alpha_hunter_strategy_observations_v01 ADD CONSTRAINT "alpha_hunter_strategy_observ_production_promotion_permitt_check" CHECK ((production_promotion_permitted = false));
ALTER TABLE public.alpha_hunter_strategy_observations_v01 ADD CONSTRAINT "alpha_hunter_strategy_observations__production_permission_check" CHECK ((production_permission = false));
ALTER TABLE public.alpha_hunter_strategy_observations_v01 ADD CONSTRAINT "alpha_hunter_strategy_observations_v01_direction_check" CHECK (((direction IS NULL) OR (direction = ANY (ARRAY['LONG'::text, 'SHORT'::text]))));
ALTER TABLE public.alpha_hunter_strategy_observations_v01 ADD CONSTRAINT "alpha_hunter_strategy_observations_v01_order_path_check" CHECK ((order_path = 'NONE'::text));
ALTER TABLE public.alpha_hunter_strategy_observations_v01 ADD CONSTRAINT "alpha_hunter_strategy_observations_v01_shadow_only_check" CHECK ((shadow_only = true));
ALTER TABLE public.alpha_hunter_strategy_observations_v01 ADD CONSTRAINT "alpha_hunter_strategy_observations_v01_trade_permission_check" CHECK ((trade_permission = false));
ALTER TABLE public.alpha_hunter_strategy_observations_v01 ADD CONSTRAINT "alpha_hunter_strategy_observations_v01_pkey" PRIMARY KEY (observation_id);
ALTER TABLE public.alpha_hunter_strategy_observations_v01 ADD CONSTRAINT "alpha_hunter_strategy_observation_run_id_symbol_strategy_id_key" UNIQUE (run_id, symbol, strategy_id);
ALTER TABLE public.alpha_hunter_symbol_snapshots ADD CONSTRAINT "alpha_hunter_symbol_snapshots_pkey" PRIMARY KEY (run_id, symbol);
CREATE INDEX idx_ah_strategy_24h_queue_pending_due_v01 ON private.alpha_hunter_strategy_24h_outcome_queue_v01 USING btree (status, due_at_utc, episode_id);
CREATE INDEX idx_ah_profitability_specs_run_source_v02 ON public.alpha_hunter_profitability_test_specs_v01 USING btree (required_run_source);
CREATE INDEX idx_ah_profitability_specs_science_fp_v01 ON public.alpha_hunter_profitability_test_specs_v01 USING btree (frozen_scientific_fingerprint_sha256);
CREATE INDEX idx_ah_shadow_quote_instance_v01 ON public.alpha_hunter_shadow_decision_quotes_v01 USING btree (strategy_instance_id);
CREATE INDEX idx_ah_shadow_quote_source_time_v01 ON public.alpha_hunter_shadow_decision_quotes_v01 USING btree (run_source, observed_at_utc DESC);
CREATE INDEX idx_ah_shadow_quote_time_v01 ON public.alpha_hunter_shadow_decision_quotes_v01 USING btree (observed_at_utc DESC);
CREATE INDEX idx_ah_snapshots_collected_at_realtime_v01 ON public.alpha_hunter_snapshots USING btree (collected_at_utc);
CREATE INDEX idx_ah_snapshots_run_source_time_v02 ON public.alpha_hunter_snapshots USING btree ((((payload -> 'validation_identity'::text) ->> 'run_source'::text)), collected_at_utc DESC);
CREATE INDEX idx_ah_strategy_episode_strategy_time_v01 ON public.alpha_hunter_strategy_episodes_v01 USING btree (strategy_id, first_observed_at_utc);
CREATE INDEX idx_ah_strategy_episode_time_v01 ON public.alpha_hunter_strategy_episodes_v01 USING btree (first_observed_at_utc);
CREATE INDEX idx_ah_strategy_candidate_time_run_v03 ON public.alpha_hunter_strategy_observations_v01 USING btree (observed_at_utc, run_id, strategy_instance_id, first_seen_at_utc) WHERE (status = 'SHADOW_CANDIDATE'::text);
CREATE INDEX idx_ah_strategy_obs_instance_time_v01 ON public.alpha_hunter_strategy_observations_v01 USING btree (strategy_instance_id, observed_at_utc) WHERE (strategy_instance_id IS NOT NULL);
CREATE INDEX idx_ah_strategy_obs_observed_at_realtime_v01 ON public.alpha_hunter_strategy_observations_v01 USING btree (observed_at_utc);
CREATE INDEX idx_ah_strategy_obs_strategy_time_v01 ON public.alpha_hunter_strategy_observations_v01 USING btree (strategy_id, observed_at_utc);
CREATE INDEX idx_ah_strategy_obs_time_run_status_v02 ON public.alpha_hunter_strategy_observations_v01 USING btree (observed_at_utc, run_id, status);
CREATE INDEX idx_ah_permission_time ON public.alpha_hunter_symbol_snapshots USING btree (trade_permission, collected_at_utc DESC);
CREATE INDEX idx_ah_state_time ON public.alpha_hunter_symbol_snapshots USING btree (state, collected_at_utc DESC);
CREATE INDEX idx_ah_symbol_time ON public.alpha_hunter_symbol_snapshots USING btree (symbol, collected_at_utc DESC);
-- Live catalog function md5 2caefa517ee67735917497ccdba350fe
CREATE OR REPLACE FUNCTION private.alpha_hunter_auto_freeze_execution_decision_v02()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  s public.alpha_hunter_strategy_observations_v01%rowtype;
  sp public.alpha_hunter_profitability_test_specs_v01%rowtype;
  p public.alpha_hunter_snapshots%rowtype;
  v_execution_event_id text;
begin
  if new.quote_complete is not true
     or new.prospective_capture is not true
     or new.action not in ('EXECUTE_NOW','PLACE_LIMIT')
     or coalesce(new.run_source,'')<>'RENDER_CRON'
  then
    return new;
  end if;

  select x.* into s
  from public.alpha_hunter_strategy_observations_v01 x
  where x.observation_id=new.observation_id
  limit 1;

  if s.observation_id is null
     or s.geometry_valid is not true
     or s.direction<>new.direction
     or s.action<>new.action
  then
    return new;
  end if;

  select x.* into p
  from public.alpha_hunter_snapshots x
  where x.run_id=new.run_id
  limit 1;

  if p.run_id is null then
    return new;
  end if;

  select spec.* into sp
  from public.alpha_hunter_profitability_test_specs_v01 spec
  join public.alpha_hunter_profitability_test_activations_v01 act
    on act.spec_id=spec.spec_id
  where spec.required_run_source=new.run_source
    and act.started_at_utc<=new.observed_at_utc
    and (
      (
        spec.frozen_scientific_fingerprint_sha256 is not null
        and coalesce(
          p.payload->'validation_identity'->>'scientific_fingerprint_sha256',
          ''
        )=spec.frozen_scientific_fingerprint_sha256
      )
      or
      (
        spec.frozen_scientific_fingerprint_sha256 is null
        and coalesce(p.payload->'validation_identity'->>'git_commit','')
            =act.baseline_git_commit
        and coalesce(p.payload->'validation_identity'->>'config_sha256','')
            =act.baseline_config_sha256
      )
    )
  order by act.activated_at_utc desc
  limit 1;

  if sp.spec_id is null then
    return new;
  end if;

  v_execution_event_id:='exec-auto-'||md5(new.observation_id);

  insert into public.alpha_hunter_execution_decision_freezes_v01(
    execution_event_id,
    spec_id,
    decision_observation_id,
    strategy_instance_id,
    decision_run_id,
    symbol,
    strategy_id,
    direction,
    action,
    decision_observed_at_utc,
    decision_captured_at_utc,
    frozen_at_utc,
    reference_price,
    planned_entry_price,
    stop_price,
    target_price,
    reward_risk,
    best_bid,
    best_ask,
    midpoint,
    entry_cross_price,
    entry_cross_half_spread_bps,
    quote_complete,
    prospective_capture,
    evidence,
    scientific_role,
    shadow_only,
    trade_permission,
    production_promotion_permitted,
    order_path
  ) values (
    v_execution_event_id,
    sp.spec_id,
    new.observation_id,
    new.strategy_instance_id,
    new.run_id,
    new.symbol,
    new.strategy_id,
    new.direction,
    new.action,
    new.observed_at_utc,
    new.captured_at_utc,
    greatest(clock_timestamp(),new.captured_at_utc),
    new.reference_price,
    new.planned_entry_price,
    s.stop_price,
    s.target_price,
    s.reward_risk,
    new.best_bid,
    new.best_ask,
    new.midpoint,
    new.entry_cross_price,
    new.entry_cross_half_spread_bps,
    true,
    true,
    jsonb_build_object(
      'source','SEALED_PROSPECTIVE_DECISION_QUOTE',
      'capture_mode','AUTO_FREEZE_AT_DECISION_QUOTE_INSERT',
      'run_source',new.run_source,
      'git_commit',new.git_commit,
      'config_sha256',new.config_sha256,
      'scientific_fingerprint_sha256',
        p.payload->'validation_identity'->>'scientific_fingerprint_sha256',
      'automatic_decision_freeze',true,
      'automatic_fill_binding_permitted',false,
      'symbol_time_proximity_attribution_permitted',false,
      'explicit_exact_fill_binding_required',true
    ),
    'PROSPECTIVE_EXECUTION_ATTRIBUTION_AUTO_FREEZE',
    true,
    false,
    false,
    'NONE'
  )
  on conflict(decision_observation_id) do nothing;

  return new;
end;
$function$
;
-- Live catalog function md5 4db6a60b328f843970f8b165142f6fe2
CREATE OR REPLACE FUNCTION private.alpha_hunter_block_append_only_mutation()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  raise exception 'append-only Alpha Hunter evidence cannot be updated or deleted';
end;
$function$
;
-- Live catalog function md5 88af26209fa503cbdf4ad9cf29eb09b5
CREATE OR REPLACE FUNCTION private.alpha_hunter_capture_shadow_decision_quote_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_parent public.alpha_hunter_snapshots%rowtype;
  v_symbol public.alpha_hunter_symbol_snapshots%rowtype;
  v_book jsonb;
  v_recent jsonb;
  v_bid double precision;
  v_ask double precision;
  v_mid double precision;
  v_entry_cross double precision;
  v_half_spread_bps double precision;
  v_entry_distance_bps double precision;
  v_complete boolean;
  v_status text;
begin
  if new.status<>'SHADOW_CANDIDATE'
     or new.direction not in ('LONG','SHORT')
  then
    return new;
  end if;

  select p.* into v_parent
  from public.alpha_hunter_snapshots p
  where p.run_id=new.run_id
  limit 1;

  select s.* into v_symbol
  from public.alpha_hunter_symbol_snapshots s
  where s.run_id=new.run_id
    and s.symbol=new.symbol
  limit 1;

  v_book := v_symbol.payload->'microstructure'->'order_book';
  v_recent := v_symbol.payload->'microstructure'->'recent_trades';

  v_bid := nullif(v_book->>'best_bid','')::double precision;
  v_ask := nullif(v_book->>'best_ask','')::double precision;
  v_mid := nullif(v_book->>'midpoint','')::double precision;

  v_complete := (
    v_parent.run_id is not null
    and v_symbol.run_id is not null
    and coalesce(v_symbol.payload->'microstructure'->>'status','')='COMPLETE'
    and v_bid is not null
    and v_ask is not null
    and v_mid is not null
    and v_mid>0
    and v_ask>=v_bid
  );

  if v_complete then
    v_entry_cross := case
      when new.direction='LONG' then v_ask
      else v_bid
    end;

    v_half_spread_bps := case
      when new.direction='LONG'
        then (v_ask-v_mid)/v_mid*10000.0
      else (v_mid-v_bid)/v_mid*10000.0
    end;

    v_entry_distance_bps := case
      when new.entry_price is null then null
      when new.direction='LONG'
        then (new.entry_price-v_mid)/v_mid*10000.0
      else (v_mid-new.entry_price)/v_mid*10000.0
    end;

    v_status := 'COMPLETE_DECISION_TIME_QUOTE';
  else
    v_status := 'INCOMPLETE_DECISION_TIME_QUOTE';
  end if;

  insert into public.alpha_hunter_shadow_decision_quotes_v01(
    observation_id,
    strategy_instance_id,
    run_id,
    symbol,
    strategy_id,
    direction,
    action,
    observed_at_utc,
    run_source,
    git_commit,
    config_sha256,
    reference_price,
    planned_entry_price,
    best_bid,
    best_ask,
    midpoint,
    spread_pct,
    entry_cross_price,
    entry_cross_half_spread_bps,
    planned_entry_directional_distance_bps,
    depth_imbalance,
    trade_imbalance,
    source_skew_ms,
    order_book_exchange_timestamp_ms,
    newest_trade_timestamp_ms,
    microstructure_status,
    quote_status,
    quote_complete
  ) values (
    new.observation_id,
    new.strategy_instance_id,
    new.run_id,
    new.symbol,
    new.strategy_id,
    new.direction,
    new.action,
    new.observed_at_utc,
    v_parent.payload->'validation_identity'->>'run_source',
    v_parent.payload->'validation_identity'->>'git_commit',
    v_parent.payload->'validation_identity'->>'config_sha256',
    new.reference_price,
    new.entry_price,
    v_bid,
    v_ask,
    v_mid,
    nullif(v_book->>'spread_pct','')::double precision,
    v_entry_cross,
    v_half_spread_bps,
    v_entry_distance_bps,
    nullif(v_book->>'depth_imbalance','')::double precision,
    nullif(v_recent->>'trade_imbalance','')::double precision,
    nullif(v_symbol.payload->'microstructure'->>'source_skew_ms','')::bigint,
    nullif(v_book->>'exchange_timestamp_ms','')::bigint,
    nullif(v_recent->>'newest_trade_timestamp_ms','')::bigint,
    v_symbol.payload->'microstructure'->>'status',
    v_status,
    v_complete
  )
  on conflict(observation_id) do nothing;

  return new;
end;
$function$
;
-- Live catalog function md5 52b3b76ecb79ed9694c5a3063a8c81ab
CREATE OR REPLACE FUNCTION private.alpha_hunter_capture_strategy_observations_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_strategy jsonb;
  v_persistence jsonb;
  v_observation_id text;
  v_instance_id text;
  v_direction text;
  v_first_seen timestamptz;
begin
  if new.payload is null
     or jsonb_typeof(new.payload->'multi_strategy_engine'->'strategies') <> 'array'
  then
    return new;
  end if;

  for v_strategy in
    select value
    from jsonb_array_elements(
      new.payload->'multi_strategy_engine'->'strategies'
    )
  loop
    v_persistence := coalesce(v_strategy->'persistence','{}'::jsonb);
    v_instance_id := nullif(v_persistence->>'strategy_instance_id','');
    v_direction := nullif(upper(v_strategy->>'direction'),'');
    v_first_seen := coalesce(
      nullif(v_persistence->>'first_seen_at_utc','')::timestamptz,
      new.collected_at_utc
    );

    v_observation_id := pg_catalog.md5(
      'strategy-observation-v0.1|'
      ||coalesce(new.run_id,'')||'|'
      ||coalesce(new.symbol,'')||'|'
      ||coalesce(v_strategy->>'strategy_id','')||'|'
      ||new.collected_at_utc::text
    );

    insert into public.alpha_hunter_strategy_observations_v01(
      observation_id,run_id,symbol,observed_at_utc,
      strategy_id,strategy_name,strategy_engine_version,status,action,direction,
      signal_score,score_is_calibrated,reference_price,
      entry_price,stop_price,target_price,risk_amount,reward_amount,reward_risk,
      distance_to_entry_pct,geometry_valid,
      persistence_state,strategy_instance_id,first_seen_at_utc,consecutive_scans,
      market_phase,opportunity_timing,evidence,checks,reasons,strategy_payload,
      shadow_only,trade_permission,production_permission,
      production_promotion_permitted,order_path
    ) values (
      v_observation_id,new.run_id,new.symbol,new.collected_at_utc,
      v_strategy->>'strategy_id',v_strategy->>'strategy_name',
      v_strategy->>'engine_version',coalesce(v_strategy->>'status','UNKNOWN'),
      coalesce(v_strategy->>'action','NO_SAFE_TRADE'),v_direction,
      nullif(v_strategy->>'signal_score','')::double precision,
      coalesce((v_strategy->>'score_is_calibrated')::boolean,false),
      nullif(new.payload->>'last_price','')::double precision,
      nullif(v_strategy->>'entry','')::double precision,
      nullif(v_strategy->>'stop','')::double precision,
      nullif(v_strategy->>'target','')::double precision,
      nullif(v_strategy->>'risk','')::double precision,
      nullif(v_strategy->>'reward','')::double precision,
      nullif(v_strategy->>'rr','')::double precision,
      nullif(v_strategy->>'distance_to_entry_pct','')::double precision,
      coalesce((v_strategy->>'geometry_valid')::boolean,false),
      v_persistence->>'state',v_instance_id,v_first_seen,
      coalesce(nullif(v_persistence->>'consecutive_scans','')::integer,0),
      new.payload->>'market_phase',new.payload->>'opportunity_timing',
      coalesce(v_strategy->'evidence','{}'::jsonb),
      coalesce(v_strategy->'checks','{}'::jsonb),
      coalesce(v_strategy->'reasons','[]'::jsonb),
      v_strategy,
      true,false,false,false,'NONE'
    )
    on conflict(observation_id) do nothing;

    if v_instance_id is not null
       and v_direction in ('LONG','SHORT')
       and coalesce(v_strategy->>'status','') in ('WATCH','SHADOW_CANDIDATE')
    then
      insert into public.alpha_hunter_strategy_episodes_v01(
        episode_id,symbol,strategy_id,strategy_name,strategy_engine_version,direction,
        first_observed_at_utc,first_observation_id,first_status,first_action,
        first_signal_score,first_reference_price,earliest_identifiable_entry_price,
        first_stop_price,first_target_price,first_risk_amount,first_reward_amount,
        first_reward_risk,first_geometry_valid,first_market_phase,
        first_opportunity_timing,first_strategy_payload,
        shadow_only,trade_permission,production_permission,
        production_promotion_permitted,order_path
      ) values (
        v_instance_id,new.symbol,v_strategy->>'strategy_id',
        v_strategy->>'strategy_name',v_strategy->>'engine_version',v_direction,
        v_first_seen,v_observation_id,coalesce(v_strategy->>'status','UNKNOWN'),
        coalesce(v_strategy->>'action','NO_SAFE_TRADE'),
        nullif(v_strategy->>'signal_score','')::double precision,
        nullif(new.payload->>'last_price','')::double precision,
        nullif(v_strategy->>'entry','')::double precision,
        nullif(v_strategy->>'stop','')::double precision,
        nullif(v_strategy->>'target','')::double precision,
        nullif(v_strategy->>'risk','')::double precision,
        nullif(v_strategy->>'reward','')::double precision,
        nullif(v_strategy->>'rr','')::double precision,
        coalesce((v_strategy->>'geometry_valid')::boolean,false),
        new.payload->>'market_phase',new.payload->>'opportunity_timing',
        v_strategy,true,false,false,false,'NONE'
      )
      on conflict(episode_id) do nothing;
    end if;
  end loop;

  return new;
end;
$function$
;
-- Live catalog function md5 18ed88128252c57891fa66a680cb1028
CREATE OR REPLACE FUNCTION private.alpha_hunter_enqueue_strategy_24h_outcome_v01()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  insert into private.alpha_hunter_strategy_24h_outcome_queue_v01(
    episode_id,due_at_utc,status
  ) values (
    new.episode_id,
    new.first_observed_at_utc+interval '24 hours',
    'PENDING'
  )
  on conflict(episode_id) do nothing;
  return new;
end;
$function$
;
CREATE TRIGGER trg_ah_execution_decision_freezes_append_only BEFORE DELETE OR UPDATE ON public.alpha_hunter_execution_decision_freezes_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_profitability_activation_append_only_v01 BEFORE DELETE OR UPDATE ON public.alpha_hunter_profitability_test_activations_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_profitability_specs_append_only_v01 BEFORE DELETE OR UPDATE ON public.alpha_hunter_profitability_test_specs_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_auto_freeze_execution_decision_v02 AFTER INSERT ON public.alpha_hunter_shadow_decision_quotes_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_auto_freeze_execution_decision_v02();
CREATE TRIGGER trg_ah_shadow_decision_quotes_append_only_v01 BEFORE DELETE OR UPDATE ON public.alpha_hunter_shadow_decision_quotes_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_enqueue_strategy_24h_outcome_v01 AFTER INSERT ON public.alpha_hunter_strategy_episodes_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_enqueue_strategy_24h_outcome_v01();
CREATE TRIGGER trg_ah_strategy_episode_append_only_v01 BEFORE DELETE OR UPDATE ON public.alpha_hunter_strategy_episodes_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_capture_shadow_decision_quote_v01 AFTER INSERT ON public.alpha_hunter_strategy_observations_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_capture_shadow_decision_quote_v01();
CREATE TRIGGER trg_ah_strategy_obs_append_only_v01 BEFORE DELETE OR UPDATE ON public.alpha_hunter_strategy_observations_v01 FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_block_append_only_mutation();
CREATE TRIGGER trg_ah_capture_strategy_observations_v01 AFTER INSERT OR UPDATE OF payload ON public.alpha_hunter_symbol_snapshots FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_capture_strategy_observations_v01();
-- No historic records or live credentials included.
