-- Alpha Hunter sealed sample-integrity performance v0.3
--
-- Rewrites the integrity audit as per-spec lateral aggregates.
-- Scientific semantics and public column contract are preserved.
-- No strategy/economic threshold or trading-authority change.

create index if not exists idx_ah_strategy_candidate_time_run_v03
  on public.alpha_hunter_strategy_observations_v01(
    observed_at_utc,
    run_id,
    strategy_instance_id,
    first_seen_at_utc
  )
  where status='SHADOW_CANDIDATE';

create index if not exists idx_ah_strategy_outcome_24h_eval_episode_v03
  on public.alpha_hunter_strategy_forward_outcomes_v01(
    evaluated_at_utc,
    episode_id,
    first_observed_at_utc
  )
  where horizon_hours=24;

create or replace view public.alpha_hunter_profitability_sample_integrity_v01
with (security_invoker=true,security_barrier=true)
as
with specs as (
  select
    s.spec_id,
    s.preregistered_at_utc,
    s.required_run_source,
    a.started_at_utc,
    a.baseline_run_id
  from public.alpha_hunter_profitability_test_specs_v01 s
  left join public.alpha_hunter_profitability_test_activations_v01 a
    on a.spec_id=s.spec_id
)
select
  s.spec_id,
  s.preregistered_at_utc,
  s.started_at_utc,
  s.baseline_run_id,

  coalesce(ep.post_baseline_episode_count,0)::bigint
    as post_baseline_episode_count,

  coalesce(co.post_baseline_candidate_observation_count,0)::bigint
    as post_baseline_candidate_observation_count,
  coalesce(co.left_censored_candidate_observation_count,0)::bigint
    as left_censored_candidate_observation_count,
  coalesce(co.post_baseline_candidate_episode_count,0)::bigint
    as post_baseline_candidate_episode_count,

  coalesce(fc.post_baseline_24h_outcome_rows,0)::bigint
    as post_baseline_24h_outcome_rows,
  coalesce(fc.post_baseline_24h_triggered_rows,0)::bigint
    as post_baseline_24h_triggered_rows,
  coalesce(fc.post_baseline_24h_economic_eligible_rows,0)::bigint
    as post_baseline_24h_economic_eligible_rows,
  coalesce(fc.left_censored_24h_outcome_rows,0)::bigint
    as left_censored_24h_outcome_rows,

  coalesce(pc.completed_paper_economics_rows,0)::bigint
    as completed_paper_economics_rows,
  coalesce(pc.contaminated_pre_baseline_economics_rows,0)::bigint
    as contaminated_pre_baseline_economics_rows,
  coalesce(pc.duplicate_economics_episode_rows,0)::bigint
    as duplicate_economics_episode_rows,

  coalesce(du.duplicate_24h_outcome_rows,0)::bigint
    as duplicate_24h_outcome_rows,

  (
    coalesce(pc.contaminated_pre_baseline_economics_rows,0)=0
    and coalesce(pc.duplicate_economics_episode_rows,0)=0
    and coalesce(du.duplicate_24h_outcome_rows,0)=0
  ) as sealed_sample_integrity_ok,

  case
    when s.started_at_utc is null then 'WAITING_FOR_BASELINE'
    when coalesce(pc.contaminated_pre_baseline_economics_rows,0)>0
      then 'FAIL_PRE_BASELINE_CONTAMINATION'
    when coalesce(pc.duplicate_economics_episode_rows,0)>0
      or coalesce(du.duplicate_24h_outcome_rows,0)>0
      then 'FAIL_DUPLICATE_SAMPLE_ROWS'
    else 'PASS'
  end as sample_integrity_status,

  'POST_BASELINE_EPISODES_ONLY'::text as sample_boundary,
  'LEFT_CENSORED_CANDIDATES_ARE_DIAGNOSTIC_ONLY'::text
    as left_censor_policy,
  true as audit_only,
  true as paper_only,
  false as profitability_rule_change_permitted,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path

from specs s

left join lateral (
  select count(*)::bigint as post_baseline_episode_count
  from public.alpha_hunter_strategy_episodes_v01 e
  join public.alpha_hunter_strategy_observations_v01 fo
    on fo.observation_id=e.first_observation_id
  join public.alpha_hunter_snapshots p
    on p.run_id=fo.run_id
  where s.started_at_utc is not null
    and e.first_observed_at_utc>=s.started_at_utc
    and p.payload->'validation_identity'->>'run_source'
      =s.required_run_source
) ep on true

left join lateral (
  select
    count(*)::bigint as post_baseline_candidate_observation_count,
    count(*) filter(
      where coalesce(o.first_seen_at_utc,o.observed_at_utc)
        <s.started_at_utc
    )::bigint as left_censored_candidate_observation_count,
    count(distinct o.strategy_instance_id) filter(
      where o.strategy_instance_id is not null
        and coalesce(o.first_seen_at_utc,o.observed_at_utc)
          >=s.started_at_utc
    )::bigint as post_baseline_candidate_episode_count
  from public.alpha_hunter_strategy_observations_v01 o
  join public.alpha_hunter_snapshots p
    on p.run_id=o.run_id
  where s.started_at_utc is not null
    and o.observed_at_utc>=s.started_at_utc
    and o.status='SHADOW_CANDIDATE'
    and p.payload->'validation_identity'->>'run_source'
      =s.required_run_source
) co on true

left join lateral (
  select
    count(*) filter(
      where f.first_observed_at_utc>=s.started_at_utc
    )::bigint as post_baseline_24h_outcome_rows,
    count(*) filter(
      where f.first_observed_at_utc>=s.started_at_utc
        and f.entry_trigger_status in (
          'TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT'
        )
    )::bigint as post_baseline_24h_triggered_rows,
    count(*) filter(
      where f.first_observed_at_utc>=s.started_at_utc
        and f.entry_trigger_status in (
          'TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT'
        )
        and f.path_measurement_quality='COMPLETE_ENOUGH'
        and f.ordering_ambiguous=false
    )::bigint as post_baseline_24h_economic_eligible_rows,
    count(*) filter(
      where f.first_observed_at_utc<s.started_at_utc
    )::bigint as left_censored_24h_outcome_rows
  from public.alpha_hunter_strategy_forward_outcomes_v01 f
  join public.alpha_hunter_strategy_episodes_v01 e
    on e.episode_id=f.episode_id
  join public.alpha_hunter_strategy_observations_v01 fo
    on fo.observation_id=e.first_observation_id
  join public.alpha_hunter_snapshots p
    on p.run_id=fo.run_id
  where s.started_at_utc is not null
    and f.horizon_hours=24
    and f.evaluated_at_utc>=s.started_at_utc
    and p.payload->'validation_identity'->>'run_source'
      =s.required_run_source
) fc on true

left join lateral (
  select
    count(*)::bigint as completed_paper_economics_rows,
    count(*) filter(
      where e.first_observed_at_utc<s.started_at_utc
    )::bigint as contaminated_pre_baseline_economics_rows,
    (
      count(*)-count(distinct e.episode_id)
    )::bigint as duplicate_economics_episode_rows
  from public.alpha_hunter_strategy_paper_economics_v01 e
  where e.spec_id=s.spec_id
) pc on true

left join lateral (
  select coalesce(sum(x.duplicate_rows),0)::bigint
    as duplicate_24h_outcome_rows
  from (
    select greatest(count(*)-1,0)::bigint as duplicate_rows
    from public.alpha_hunter_strategy_forward_outcomes_v01 f
    join public.alpha_hunter_strategy_episodes_v01 e
      on e.episode_id=f.episode_id
    join public.alpha_hunter_strategy_observations_v01 fo
      on fo.observation_id=e.first_observation_id
    join public.alpha_hunter_snapshots p
      on p.run_id=fo.run_id
    where s.started_at_utc is not null
      and f.horizon_hours=24
      and f.first_observed_at_utc>=s.started_at_utc
      and p.payload->'validation_identity'->>'run_source'
        =s.required_run_source
    group by f.episode_id,f.horizon_hours
    having count(*)>1
  ) x
) du on true;

revoke all on public.alpha_hunter_profitability_sample_integrity_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profitability_sample_integrity_v01
  to service_role;
