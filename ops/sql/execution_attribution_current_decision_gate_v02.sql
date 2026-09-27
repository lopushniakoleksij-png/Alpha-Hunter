-- Alpha Hunter current decision freeze gate v0.2
--
-- Operations-only attribution integrity. Lives under ops/sql and remains
-- outside the sealed V14 scientific fingerprint.
--
-- A decision is freezeable only when:
-- - it belongs to the latest canonical run for the active sealed source;
-- - it is no older than the active cadence maximum interval (35m fallback);
-- - the quote is complete/prospective and geometry-valid;
-- - it has not already been frozen.
--
-- Historical quotes remain preserved for audit but are not freezeable.

create or replace view public.alpha_hunter_execution_attribution_candidates_v01
with (security_invoker=true,security_barrier=true) as
with active as (
  select e.spec_id,v.started_at_utc,s.required_run_source
  from public.alpha_hunter_test_engine_latest_v01 e
  join public.alpha_hunter_profitability_validation_status_v01 v
    on v.spec_id=e.spec_id
  join public.alpha_hunter_profitability_test_specs_v01 s
    on s.spec_id=e.spec_id
  where v.test_activated=true
  limit 1
),
cadence as (
  select c.maximum_interval_minutes
  from public.alpha_hunter_profitability_cadence_integrity_v01 c
  join active a on a.spec_id=c.spec_id
  limit 1
),
latest_canonical as (
  select
    s.run_id,
    s.collected_at_utc
  from public.alpha_hunter_snapshots s
  join active a
    on s.payload->'validation_identity'->>'run_source'=a.required_run_source
  order by s.collected_at_utc desc
  limit 1
)
select
  a.spec_id,
  q.observation_id as decision_observation_id,
  q.strategy_instance_id,
  q.run_id as decision_run_id,
  q.symbol,
  q.strategy_id,
  q.direction,
  q.action,
  q.observed_at_utc as decision_observed_at_utc,
  q.captured_at_utc as decision_captured_at_utc,
  q.reference_price,
  q.planned_entry_price,
  s.stop_price,
  s.target_price,
  s.reward_risk,
  s.geometry_valid,
  q.best_bid,
  q.best_ask,
  q.midpoint,
  q.entry_cross_price,
  q.entry_cross_half_spread_bps,
  q.quote_complete,
  q.prospective_capture,
  q.run_source,
  q.git_commit,
  q.config_sha256,
  not exists (
    select 1
    from public.alpha_hunter_execution_decision_freezes_v01 f
    where f.decision_observation_id=q.observation_id
  ) as freeze_available,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from active a
join latest_canonical lc on true
left join cadence c on true
join public.alpha_hunter_shadow_decision_quotes_v01 q
  on q.run_source=a.required_run_source
 and q.run_id=lc.run_id
 and q.observed_at_utc>=a.started_at_utc
 and q.observed_at_utc<=clock_timestamp()
 and q.observed_at_utc>=clock_timestamp()
   - coalesce(c.maximum_interval_minutes,35)::double precision
     * interval '1 minute'
join public.alpha_hunter_strategy_observations_v01 s
  on s.observation_id=q.observation_id
where q.quote_complete=true
  and q.prospective_capture=true
  and q.action in ('EXECUTE_NOW','PLACE_LIMIT')
  and s.geometry_valid=true
  and s.direction=q.direction
  and s.action=q.action;

revoke all on public.alpha_hunter_execution_attribution_candidates_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_execution_attribution_candidates_v01
  to service_role;
