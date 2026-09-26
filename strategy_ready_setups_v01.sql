-- Alpha Hunter canonical S1-S10 ready-setup view v0.1
--
-- Purpose:
-- Expose strategy candidates that have already passed the S1-S10 candidate
-- contract as a canonical decision-support queue. This closes the gap between
-- strategy discovery and the operator-facing Money Action layer.
--
-- IMPORTANT:
-- READY_SETUP means "all strategy/safety/geometry/5R gates passed for paper
-- decision support". It does NOT grant exchange/order authority.
--
-- Sources:
-- - RENDER_CRON: canonical Render production scanner
-- - RENDER: legacy canonical Render scanner during migration
-- - GITHUB_FAST_DISCOVERY: isolated 20-minute early-discovery scanner
-- - RENDER_WEB is intentionally excluded from the canonical ready queue
--
-- Staleness:
-- - only the latest run from each source
-- - source run must be <= 90 minutes old

create or replace view public.alpha_hunter_strategy_ready_setups_v01
with (security_invoker=true,security_barrier=true)
as
with source_latest as (
  select distinct on (
    p.payload->'validation_identity'->>'run_source'
  )
    p.run_id,
    p.collected_at_utc,
    p.payload->'validation_identity'->>'run_source' as run_source,
    p.payload->'validation_identity'->>'git_commit' as git_commit,
    p.payload->'validation_identity'->>'config_sha256' as config_sha256
  from public.alpha_hunter_snapshots p
  where p.payload->'validation_identity'->>'run_source'
      in ('RENDER_CRON','RENDER','GITHUB_FAST_DISCOVERY')
    and p.collected_at_utc >= clock_timestamp()-interval '90 minutes'
  order by
    p.payload->'validation_identity'->>'run_source',
    p.collected_at_utc desc
),
eligible as (
  select
    l.run_source,
    l.run_id,
    l.collected_at_utc as scan_at_utc,
    l.git_commit,
    l.config_sha256,
    extract(
      epoch from (clock_timestamp()-l.collected_at_utc)
    ) as scan_age_seconds,

    o.observation_id,
    o.strategy_instance_id,
    o.symbol,
    o.strategy_id,
    o.strategy_name,
    o.direction,
    o.status as strategy_status,
    o.action as strategy_action,
    coalesce(
      o.strategy_payload->>'proposed_action',
      o.action
    ) as proposed_action,
    o.signal_score,
    o.score_is_calibrated,
    o.reference_price,
    o.entry_price,
    o.stop_price,
    o.target_price,
    o.reward_risk,
    o.distance_to_entry_pct,
    o.geometry_valid,
    o.persistence_state,
    o.consecutive_scans,
    o.first_seen_at_utc,
    o.observed_at_utc,
    o.checks,
    o.reasons,
    o.evidence,

    case
      when o.action='EXECUTE_NOW'
        then 'READY_SETUP_NOW'
      when o.action='PLACE_LIMIT'
        then 'READY_LIMIT_SETUP'
      else 'NOT_READY'
    end as ready_status,

    case
      when o.action='EXECUTE_NOW' then 2
      when o.action='PLACE_LIMIT' then 1
      else 0
    end as action_priority

  from source_latest l
  join public.alpha_hunter_strategy_observations_v01 o
    on o.run_id=l.run_id

  where o.status='SHADOW_CANDIDATE'
    and o.action in ('EXECUTE_NOW','PLACE_LIMIT')
    and o.direction in ('LONG','SHORT')
    and coalesce(o.geometry_valid,false)
    and o.reward_risk>=5.0
    and o.entry_price is not null
    and o.stop_price is not null
    and o.target_price is not null
    and coalesce(o.shadow_only,false)
    and coalesce(o.trade_permission,false)=false
    and coalesce(o.production_permission,false)=false

    and (
      (
        o.direction='LONG'
        and o.stop_price<o.entry_price
        and o.entry_price<o.target_price
      )
      or
      (
        o.direction='SHORT'
        and o.target_price<o.entry_price
        and o.entry_price<o.stop_price
      )
    )
),
ranked as (
  select
    e.*,
    row_number() over (
      partition by e.run_source
      order by
        e.action_priority desc,
        e.signal_score desc,
        e.reward_risk desc,
        coalesce(e.distance_to_entry_pct,0) asc,
        e.symbol,
        e.strategy_id
    ) as source_rank,
    row_number() over (
      partition by e.run_source,e.symbol
      order by
        e.action_priority desc,
        e.signal_score desc,
        e.reward_risk desc,
        coalesce(e.distance_to_entry_pct,0) asc,
        e.strategy_id
    ) as symbol_rank
  from eligible e
)
select
  r.run_source,
  r.run_id,
  r.scan_at_utc,
  r.scan_age_seconds,
  r.git_commit,
  r.config_sha256,
  r.source_rank,
  r.symbol_rank,

  r.symbol,
  r.strategy_id,
  r.strategy_name,
  r.direction,
  r.ready_status,
  r.strategy_action,
  r.signal_score,
  r.score_is_calibrated,

  r.reference_price,
  r.entry_price,
  r.stop_price,
  r.target_price,
  r.reward_risk,
  r.distance_to_entry_pct,

  r.persistence_state,
  r.consecutive_scans,
  r.first_seen_at_utc,
  r.observed_at_utc,

  r.checks,
  r.reasons,
  r.evidence,

  'S1_S10_SHADOW_CANDIDATE_5R'::text as readiness_contract,
  true as decision_support_only,
  true as shadow_only,
  false as live_money_claim_permitted,
  false as execution_authority,
  false as trade_permission,
  false as production_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from ranked r;

revoke all on public.alpha_hunter_strategy_ready_setups_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_strategy_ready_setups_v01
  to service_role;
