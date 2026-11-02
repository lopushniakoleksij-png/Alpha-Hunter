-- PROTOTYPE ONLY. NEVER RUN ON PRODUCTION. Internal isolated tests use an
-- explicitly trusted synthetic run identifier ($1). The source table's actual
-- per-row strategy trigger is disabled ONLY in the isolated candidate fixture.
-- This is not a migration, not an exposed RPC and NOT a drop-in R10 replacement.
-- Semantics copied field-for-field from production
-- private.alpha_hunter_capture_strategy_observations_v01(), 2026-10-12.
INSERT INTO public.alpha_hunter_strategy_observations_v01(
 observation_id,run_id,symbol,observed_at_utc,
 strategy_id,strategy_name,strategy_engine_version,status,action,direction,
 signal_score,score_is_calibrated,reference_price,
 entry_price,stop_price,target_price,risk_amount,reward_amount,reward_risk,
 distance_to_entry_pct,geometry_valid,
 persistence_state,strategy_instance_id,first_seen_at_utc,consecutive_scans,
 market_phase,opportunity_timing,evidence,checks,reasons,strategy_payload,
 shadow_only,trade_permission,production_permission,
 production_promotion_permitted,order_path
)
SELECT
 pg_catalog.md5('strategy-observation-v0.1|'||coalesce(c.run_id,'')||'|'||
                coalesce(c.symbol,'')||'|'||coalesce(s.value->>'strategy_id','')||
                '|'||c.collected_at_utc::text),
 c.run_id,c.symbol,c.collected_at_utc,
 s.value->>'strategy_id',s.value->>'strategy_name',s.value->>'engine_version',
 coalesce(s.value->>'status','UNKNOWN'),coalesce(s.value->>'action','NO_SAFE_TRADE'),
 nullif(upper(s.value->>'direction'),''),
 nullif(s.value->>'signal_score','')::double precision,
 coalesce((s.value->>'score_is_calibrated')::boolean,false),
 nullif(c.payload->>'last_price','')::double precision,
 nullif(s.value->>'entry','')::double precision,
 nullif(s.value->>'stop','')::double precision,
 nullif(s.value->>'target','')::double precision,
 nullif(s.value->>'risk','')::double precision,
 nullif(s.value->>'reward','')::double precision,
 nullif(s.value->>'rr','')::double precision,
 nullif(s.value->>'distance_to_entry_pct','')::double precision,
 coalesce((s.value->>'geometry_valid')::boolean,false),
 coalesce(s.value->'persistence','{}'::jsonb)->>'state',
 nullif((coalesce(s.value->'persistence','{}'::jsonb)->>'strategy_instance_id'),''),
 coalesce(nullif((coalesce(s.value->'persistence','{}'::jsonb)->>'first_seen_at_utc'),'')::timestamptz,
          c.collected_at_utc),
 coalesce(nullif((coalesce(s.value->'persistence','{}'::jsonb)->>'consecutive_scans'),'')::integer,0),
 c.payload->>'market_phase',c.payload->>'opportunity_timing',
 coalesce(s.value->'evidence','{}'::jsonb),coalesce(s.value->'checks','{}'::jsonb),
 coalesce(s.value->'reasons','[]'::jsonb),s.value,
 true,false,false,false,'NONE'
FROM public.alpha_hunter_symbol_snapshots c
CROSS JOIN LATERAL jsonb_array_elements(
  CASE WHEN jsonb_typeof(c.payload->'multi_strategy_engine'->'strategies')='array'
       THEN c.payload->'multi_strategy_engine'->'strategies'
       ELSE '[]'::jsonb END
) AS s(value)
WHERE c.run_id=$1
ON CONFLICT(observation_id) DO NOTHING;

-- NEXT STATEMENT
INSERT INTO public.alpha_hunter_strategy_episodes_v01(
 episode_id,symbol,strategy_id,strategy_name,strategy_engine_version,direction,
 first_observed_at_utc,first_observation_id,first_status,first_action,
 first_signal_score,first_reference_price,earliest_identifiable_entry_price,
 first_stop_price,first_target_price,first_risk_amount,first_reward_amount,
 first_reward_risk,first_geometry_valid,first_market_phase,
 first_opportunity_timing,first_strategy_payload,
 shadow_only,trade_permission,production_permission,
 production_promotion_permitted,order_path
)
SELECT
 nullif(coalesce(s.value->'persistence','{}'::jsonb)->>'strategy_instance_id',''),
 c.symbol,s.value->>'strategy_id',s.value->>'strategy_name',s.value->>'engine_version',
 nullif(upper(s.value->>'direction'),''),
 coalesce(nullif(coalesce(s.value->'persistence','{}'::jsonb)->>'first_seen_at_utc','')::timestamptz,
          c.collected_at_utc),
 pg_catalog.md5('strategy-observation-v0.1|'||coalesce(c.run_id,'')||'|'||
                coalesce(c.symbol,'')||'|'||coalesce(s.value->>'strategy_id','')||
                '|'||c.collected_at_utc::text),
 coalesce(s.value->>'status','UNKNOWN'),coalesce(s.value->>'action','NO_SAFE_TRADE'),
 nullif(s.value->>'signal_score','')::double precision,
 nullif(c.payload->>'last_price','')::double precision,
 nullif(s.value->>'entry','')::double precision,
 nullif(s.value->>'stop','')::double precision,
 nullif(s.value->>'target','')::double precision,
 nullif(s.value->>'risk','')::double precision,
 nullif(s.value->>'reward','')::double precision,
 nullif(s.value->>'rr','')::double precision,
 coalesce((s.value->>'geometry_valid')::boolean,false),
 c.payload->>'market_phase',c.payload->>'opportunity_timing',s.value,
 true,false,false,false,'NONE'
FROM public.alpha_hunter_symbol_snapshots c
CROSS JOIN LATERAL jsonb_array_elements(
  CASE WHEN jsonb_typeof(c.payload->'multi_strategy_engine'->'strategies')='array'
       THEN c.payload->'multi_strategy_engine'->'strategies'
       ELSE '[]'::jsonb END
) AS s(value)
WHERE c.run_id=$1
  AND nullif(coalesce(s.value->'persistence','{}'::jsonb)->>'strategy_instance_id','') IS NOT NULL
  AND nullif(upper(s.value->>'direction'),'') IN ('LONG','SHORT')
  AND coalesce(s.value->>'status','') IN ('WATCH','SHADOW_CANDIDATE')
ON CONFLICT(episode_id) DO NOTHING;
