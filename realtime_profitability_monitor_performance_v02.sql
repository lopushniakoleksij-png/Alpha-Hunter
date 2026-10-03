-- Alpha Hunter realtime profitability monitor performance v0.2
--
-- DB-only scientific infrastructure optimization.
-- Exact sealed-test semantics are preserved; no strategy, threshold,
-- execution permission, sample requirement or profitability rule changes.

create index if not exists idx_ah_snapshots_run_source_time_v02
  on public.alpha_hunter_snapshots(
    ((payload->'validation_identity'->>'run_source')),
    collected_at_utc desc
  );

create index if not exists idx_ah_strategy_obs_time_run_status_v02
  on public.alpha_hunter_strategy_observations_v01(
    observed_at_utc,
    run_id,
    status
  );

create index if not exists idx_ah_strategy_outcome_24h_time_episode_v02
  on public.alpha_hunter_strategy_forward_outcomes_v01(
    first_observed_at_utc,
    episode_id
  )
  where horizon_hours=24;

-- Preserve the existing view contract and source-isolated semantics.
-- Use per-spec lateral aggregates so PostgREST filtering/limit does not force
-- large cross-spec joins through all evidence tables.
create or replace view public.alpha_hunter_realtime_profitability_monitor_v01
with (security_invoker=true,security_barrier=true)
as
select
  clock_timestamp() as real_now_utc,
  s.spec_id,
  s.preregistered_at_utc as real_test_requested_at_utc,
  a.started_at_utc as real_counted_baseline_started_at_utc,
  s.frozen_git_commit,
  s.minimum_test_days,
  s.minimum_completed_paper_trades,

  latest.run_id as latest_live_run_id,
  latest.collected_at_utc as latest_live_scan_at_utc,
  extract(epoch from (clock_timestamp()-latest.collected_at_utc))
    as latest_live_scan_age_seconds,
  latest.git_commit as latest_live_git_commit,
  latest.config_sha256 as latest_live_config_sha256,
  latest.previous_snapshot_source,
  latest.catalyst_version,
  latest.configured_strategy_count,
  latest.shadow_candidate_count as latest_scan_shadow_candidate_count,
  latest.watch_count as latest_scan_watch_count,

  coalesce(scan_count.n,0) as real_scans_since_registration,
  coalesce(obs_count.n,0) as real_strategy_observations_since_registration,
  coalesce(obs_count.candidates,0) as real_shadow_candidates_since_registration,
  coalesce(outcome_count.n,0) as real_24h_forward_outcomes_since_registration,

  case
    when a.started_at_utc is not null then 'RUNNING_FORWARD_REAL_TIME'
    else 'PREREGISTERED_WAITING_FOR_CLEAN_LIVE_BASELINE'
  end as realtime_test_status,

  'REAL_PRODUCTION_TIMESTAMPS'::text as clock_source,
  'FORWARD_ONLY_SOURCE_ISOLATED'::text as evidence_window,
  false as historical_replay_counted,
  false as backtest_counted,
  true as paper_only,
  false as live_money_claim_permitted,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  true as run_source_isolated
from public.alpha_hunter_profitability_test_specs_v01 s
left join public.alpha_hunter_profitability_test_activations_v01 a
  on a.spec_id=s.spec_id
left join lateral (
  select
    p.run_id,
    p.collected_at_utc,
    p.payload->'validation_identity'->>'git_commit' as git_commit,
    p.payload->'validation_identity'->>'config_sha256' as config_sha256,
    p.payload->'previous_snapshot_context'->>'source'
      as previous_snapshot_source,
    p.payload->'catalyst_summary'->>'version' as catalyst_version,
    coalesce(
      (p.payload->'multi_strategy_summary'
        ->>'configured_strategy_count')::integer,
      0
    ) as configured_strategy_count,
    coalesce(
      (p.payload->'multi_strategy_summary'
        ->>'shadow_candidate_count')::integer,
      0
    ) as shadow_candidate_count,
    coalesce(
      (p.payload->'multi_strategy_summary'
        ->>'watch_count')::integer,
      0
    ) as watch_count
  from public.alpha_hunter_snapshots p
  where p.payload->'validation_identity'->>'run_source'
    =s.required_run_source
  order by p.collected_at_utc desc
  limit 1
) latest on true
left join lateral (
  select count(*)::bigint as n
  from public.alpha_hunter_snapshots p
  where p.collected_at_utc>=s.preregistered_at_utc
    and p.payload->'validation_identity'->>'run_source'
      =s.required_run_source
) scan_count on true
left join lateral (
  select
    count(*)::bigint as n,
    count(*) filter(where o.status='SHADOW_CANDIDATE')::bigint
      as candidates
  from public.alpha_hunter_strategy_observations_v01 o
  join public.alpha_hunter_snapshots p
    on p.run_id=o.run_id
  where o.observed_at_utc>=s.preregistered_at_utc
    and p.payload->'validation_identity'->>'run_source'
      =s.required_run_source
) obs_count on true
left join lateral (
  select count(*)::bigint as n
  from public.alpha_hunter_strategy_forward_outcomes_v01 f
  join public.alpha_hunter_strategy_episodes_v01 ep
    on ep.episode_id=f.episode_id
  join public.alpha_hunter_strategy_observations_v01 fo
    on fo.observation_id=ep.first_observation_id
  join public.alpha_hunter_snapshots p
    on p.run_id=fo.run_id
  where f.first_observed_at_utc>=s.preregistered_at_utc
    and f.horizon_hours=24
    and p.payload->'validation_identity'->>'run_source'
      =s.required_run_source
) outcome_count on true;

revoke all on public.alpha_hunter_realtime_profitability_monitor_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_realtime_profitability_monitor_v01
  to service_role;
