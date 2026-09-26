-- Alpha Hunter real-time profitability monitor v0.1
--
-- Purpose:
--   Make the sealed profitability test explicitly forward-only and timestamped
--   against the real production clock. This view does not evaluate historical
--   data as test evidence and cannot grant execution authority.

create index if not exists idx_ah_snapshots_collected_at_realtime_v01
  on public.alpha_hunter_snapshots(collected_at_utc);

create index if not exists idx_ah_strategy_obs_observed_at_realtime_v01
  on public.alpha_hunter_strategy_observations_v01(observed_at_utc);

create index if not exists idx_ah_strategy_forward_observed_horizon_realtime_v01
  on public.alpha_hunter_strategy_forward_outcomes_v01(
    first_observed_at_utc,horizon_hours
  );

create or replace view public.alpha_hunter_realtime_profitability_monitor_v01
with (security_invoker=true,security_barrier=true)
as
with spec as (
  select
    s.spec_id,
    s.preregistered_at_utc,
    s.frozen_git_commit,
    s.minimum_test_days,
    s.minimum_completed_paper_trades,
    a.baseline_run_id,
    a.started_at_utc
  from public.alpha_hunter_profitability_test_specs_v01 s
  left join public.alpha_hunter_profitability_test_activations_v01 a
    on a.spec_id=s.spec_id
  order by s.preregistered_at_utc desc
  limit 1
),
latest_scan as (
  select
    p.run_id,
    p.collected_at_utc,
    p.payload->'validation_identity'->>'git_commit' as git_commit,
    p.payload->'validation_identity'->>'config_sha256' as config_sha256,
    p.payload->'previous_snapshot_context'->>'source' as previous_snapshot_source,
    p.payload->'catalyst_summary'->>'version' as catalyst_version,
    coalesce(
      (p.payload->'multi_strategy_summary'->>'configured_strategy_count')::integer,
      0
    ) as configured_strategy_count,
    coalesce(
      (p.payload->'multi_strategy_summary'->>'shadow_candidate_count')::integer,
      0
    ) as shadow_candidate_count,
    coalesce(
      (p.payload->'multi_strategy_summary'->>'watch_count')::integer,
      0
    ) as watch_count
  from public.alpha_hunter_snapshots p
  order by p.collected_at_utc desc
  limit 1
),
scan_counts as (
  select
    s.spec_id,
    count(p.run_id) as real_scans_since_registration
  from spec s
  left join public.alpha_hunter_snapshots p
    on p.collected_at_utc>=s.preregistered_at_utc
  group by s.spec_id
),
observation_counts as (
  select
    s.spec_id,
    count(o.observation_id) as real_strategy_observations_since_registration,
    count(o.observation_id) filter(
      where o.status='SHADOW_CANDIDATE'
    ) as real_shadow_candidates_since_registration
  from spec s
  left join public.alpha_hunter_strategy_observations_v01 o
    on o.observed_at_utc>=s.preregistered_at_utc
  group by s.spec_id
),
outcome_counts as (
  select
    s.spec_id,
    count(f.episode_id) as real_24h_forward_outcomes_since_registration
  from spec s
  left join public.alpha_hunter_strategy_forward_outcomes_v01 f
    on f.first_observed_at_utc>=s.preregistered_at_utc
   and f.horizon_hours=24
  group by s.spec_id
),
post_registration as (
  select
    s.spec_id,
    coalesce(sc.real_scans_since_registration,0)
      as real_scans_since_registration,
    coalesce(oc.real_strategy_observations_since_registration,0)
      as real_strategy_observations_since_registration,
    coalesce(oc.real_shadow_candidates_since_registration,0)
      as real_shadow_candidates_since_registration,
    coalesce(fc.real_24h_forward_outcomes_since_registration,0)
      as real_24h_forward_outcomes_since_registration
  from spec s
  left join scan_counts sc on sc.spec_id=s.spec_id
  left join observation_counts oc on oc.spec_id=s.spec_id
  left join outcome_counts fc on fc.spec_id=s.spec_id
)
select
  clock_timestamp() as real_now_utc,
  s.spec_id,
  s.preregistered_at_utc as real_test_requested_at_utc,
  s.started_at_utc as real_counted_baseline_started_at_utc,
  s.frozen_git_commit,
  s.minimum_test_days,
  s.minimum_completed_paper_trades,

  l.run_id as latest_live_run_id,
  l.collected_at_utc as latest_live_scan_at_utc,
  extract(epoch from (clock_timestamp()-l.collected_at_utc))
    as latest_live_scan_age_seconds,
  l.git_commit as latest_live_git_commit,
  l.config_sha256 as latest_live_config_sha256,
  l.previous_snapshot_source,
  l.catalyst_version,
  l.configured_strategy_count,
  l.shadow_candidate_count as latest_scan_shadow_candidate_count,
  l.watch_count as latest_scan_watch_count,

  coalesce(p.real_scans_since_registration,0)
    as real_scans_since_registration,
  coalesce(p.real_strategy_observations_since_registration,0)
    as real_strategy_observations_since_registration,
  coalesce(p.real_shadow_candidates_since_registration,0)
    as real_shadow_candidates_since_registration,
  coalesce(p.real_24h_forward_outcomes_since_registration,0)
    as real_24h_forward_outcomes_since_registration,

  case
    when s.started_at_utc is not null then 'RUNNING_FORWARD_REAL_TIME'
    else 'PREREGISTERED_WAITING_FOR_CLEAN_LIVE_BASELINE'
  end as realtime_test_status,

  'REAL_PRODUCTION_TIMESTAMPS'::text as clock_source,
  'FORWARD_ONLY_FROM_REGISTRATION'::text as evidence_window,
  false as historical_replay_counted,
  false as backtest_counted,
  true as paper_only,
  false as live_money_claim_permitted,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from spec s
cross join latest_scan l
left join post_registration p on p.spec_id=s.spec_id;

revoke all on public.alpha_hunter_realtime_profitability_monitor_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_realtime_profitability_monitor_v01
  to service_role;
