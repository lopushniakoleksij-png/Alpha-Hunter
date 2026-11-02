-- SYNTHETIC TEST ONLY, 2026-10-12, read-only extracted public PostgreSQL metadata.
-- Production target table columns, NOT NULL/defaults, pkey/unique/check/FK and indexes
-- plus EXACT source private.alpha_hunter_capture_strategy_observations_v01() trigger.
-- Parent table stub exists ONLY to satisfy FK; never run this DDL in Supabase.
CREATE SCHEMA private;
CREATE TABLE public.alpha_hunter_snapshots(run_id text PRIMARY KEY);
CREATE TABLE public."alpha_hunter_symbol_snapshots"(
  "run_id" text NOT NULL,
  "symbol" text NOT NULL,
  "collected_at_utc" timestamptz NOT NULL,
  "state" text,
  "previous_state" text,
  "state_changed" bool NOT NULL DEFAULT false,
  "trade_permission" bool NOT NULL DEFAULT false,
  "direction" text,
  "reward_risk" float8,
  "last_price" float8,
  "open_interest" float8,
  "funding_rate" float8,
  "data_integrity_score" int4,
  "error" text,
  "payload" jsonb NOT NULL,
  "created_at" timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT "alpha_hunter_symbol_snapshots_run_id_fkey" FOREIGN KEY (run_id) REFERENCES alpha_hunter_snapshots(run_id) ON DELETE CASCADE,
  CONSTRAINT "alpha_hunter_symbol_snapshots_pkey" PRIMARY KEY (run_id, symbol)
);
CREATE TABLE public."alpha_hunter_strategy_observations_v01"(
  "observation_id" text NOT NULL,
  "run_id" text NOT NULL,
  "symbol" text NOT NULL,
  "observed_at_utc" timestamptz NOT NULL,
  "strategy_id" text NOT NULL,
  "strategy_name" text,
  "strategy_engine_version" text,
  "status" text NOT NULL,
  "action" text NOT NULL,
  "direction" text,
  "signal_score" float8,
  "score_is_calibrated" bool NOT NULL DEFAULT false,
  "reference_price" float8,
  "entry_price" float8,
  "stop_price" float8,
  "target_price" float8,
  "risk_amount" float8,
  "reward_amount" float8,
  "reward_risk" float8,
  "distance_to_entry_pct" float8,
  "geometry_valid" bool NOT NULL DEFAULT false,
  "persistence_state" text,
  "strategy_instance_id" text,
  "first_seen_at_utc" timestamptz,
  "consecutive_scans" int4 NOT NULL DEFAULT 0,
  "market_phase" text,
  "opportunity_timing" text,
  "evidence" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "checks" jsonb NOT NULL DEFAULT '{}'::jsonb,
  "reasons" jsonb NOT NULL DEFAULT '[]'::jsonb,
  "strategy_payload" jsonb NOT NULL,
  "shadow_only" bool NOT NULL DEFAULT true,
  "trade_permission" bool NOT NULL DEFAULT false,
  "production_permission" bool NOT NULL DEFAULT false,
  "production_promotion_permitted" bool NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT "alpha_hunter_strategy_observ_production_promotion_permitt_check" CHECK ((production_promotion_permitted = false)),
  CONSTRAINT "alpha_hunter_strategy_observations__production_permission_check" CHECK ((production_permission = false)),
  CONSTRAINT "alpha_hunter_strategy_observations_v01_direction_check" CHECK (((direction IS NULL) OR (direction = ANY (ARRAY['LONG'::text, 'SHORT'::text])))),
  CONSTRAINT "alpha_hunter_strategy_observations_v01_order_path_check" CHECK ((order_path = 'NONE'::text)),
  CONSTRAINT "alpha_hunter_strategy_observations_v01_shadow_only_check" CHECK ((shadow_only = true)),
  CONSTRAINT "alpha_hunter_strategy_observations_v01_trade_permission_check" CHECK ((trade_permission = false)),
  CONSTRAINT "alpha_hunter_strategy_observations_v01_pkey" PRIMARY KEY (observation_id),
  CONSTRAINT "alpha_hunter_strategy_observation_run_id_symbol_strategy_id_key" UNIQUE (run_id, symbol, strategy_id)
);
CREATE TABLE public."alpha_hunter_strategy_episodes_v01"(
  "episode_id" text NOT NULL,
  "symbol" text NOT NULL,
  "strategy_id" text NOT NULL,
  "strategy_name" text,
  "strategy_engine_version" text,
  "direction" text NOT NULL,
  "first_observed_at_utc" timestamptz NOT NULL,
  "first_observation_id" text NOT NULL,
  "first_status" text NOT NULL,
  "first_action" text NOT NULL,
  "first_signal_score" float8,
  "first_reference_price" float8,
  "earliest_identifiable_entry_price" float8,
  "first_stop_price" float8,
  "first_target_price" float8,
  "first_risk_amount" float8,
  "first_reward_amount" float8,
  "first_reward_risk" float8,
  "first_geometry_valid" bool NOT NULL DEFAULT false,
  "first_market_phase" text,
  "first_opportunity_timing" text,
  "first_strategy_payload" jsonb NOT NULL,
  "shadow_only" bool NOT NULL DEFAULT true,
  "trade_permission" bool NOT NULL DEFAULT false,
  "production_permission" bool NOT NULL DEFAULT false,
  "production_promotion_permitted" bool NOT NULL DEFAULT false,
  "order_path" text NOT NULL DEFAULT 'NONE'::text,
  "created_at" timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT "alpha_hunter_strategy_episod_production_promotion_permitt_check" CHECK ((production_promotion_permitted = false)),
  CONSTRAINT "alpha_hunter_strategy_episodes_v01_direction_check" CHECK ((direction = ANY (ARRAY['LONG'::text, 'SHORT'::text]))),
  CONSTRAINT "alpha_hunter_strategy_episodes_v01_order_path_check" CHECK ((order_path = 'NONE'::text)),
  CONSTRAINT "alpha_hunter_strategy_episodes_v01_production_permission_check" CHECK ((production_permission = false)),
  CONSTRAINT "alpha_hunter_strategy_episodes_v01_shadow_only_check" CHECK ((shadow_only = true)),
  CONSTRAINT "alpha_hunter_strategy_episodes_v01_trade_permission_check" CHECK ((trade_permission = false)),
  CONSTRAINT "alpha_hunter_strategy_episodes_v01_pkey" PRIMARY KEY (episode_id),
  CONSTRAINT "alpha_hunter_strategy_episodes_v01_first_observation_id_key" UNIQUE (first_observation_id)
);
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

-- BEGIN PRODUCTION TRIGGER FUNCTION EXTRACTED FROM pg_get_functiondef; DO NOT REWRITE.
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
CREATE TRIGGER trg_ah_capture_strategy_observations_v01 AFTER INSERT OR UPDATE OF payload ON public.alpha_hunter_symbol_snapshots FOR EACH ROW EXECUTE FUNCTION private.alpha_hunter_capture_strategy_observations_v01();
