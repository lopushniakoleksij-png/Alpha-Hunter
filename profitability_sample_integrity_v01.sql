-- Alpha Hunter sealed profitability sample-integrity monitor v0.1
--
-- Additive scientific/audit infrastructure only.
-- This view does NOT change strategy logic, scanner configuration,
-- profitability pass/fail rules, execution costs, or trade permission.
--
-- Purpose:
--   Prove that the sealed prospective profitability sample is not contaminated
--   by episodes that began before the frozen baseline (left-censoring), and
--   reconcile candidate observations -> candidate episodes -> 24H outcomes ->
--   completed paper-economics rows.

create or replace view public.alpha_hunter_profitability_sample_integrity_v01
with (security_invoker=true,security_barrier=true)
as
with specs as (
  select
    s.spec_id,
    s.preregistered_at_utc,
    s.minimum_test_days,
    s.minimum_completed_paper_trades,
    a.started_at_utc,
    a.baseline_run_id
  from public.alpha_hunter_profitability_test_specs_v01 s
  left join public.alpha_hunter_profitability_test_activations_v01 a
    on a.spec_id=s.spec_id
),
episode_counts as (
  select
    s.spec_id,
    count(e.episode_id) filter(
      where s.started_at_utc is not null
        and e.first_observed_at_utc>=s.started_at_utc
    ) as post_baseline_episode_count
  from specs s
  left join public.alpha_hunter_strategy_episodes_v01 e
    on s.started_at_utc is not null
   and e.first_observed_at_utc>=s.started_at_utc
  group by s.spec_id
),
candidate_observations as (
  select
    s.spec_id,
    count(o.observation_id) filter(
      where s.started_at_utc is not null
        and o.observed_at_utc>=s.started_at_utc
        and o.status='SHADOW_CANDIDATE'
    ) as post_baseline_candidate_observation_count,
    count(o.observation_id) filter(
      where s.started_at_utc is not null
        and o.observed_at_utc>=s.started_at_utc
        and o.status='SHADOW_CANDIDATE'
        and coalesce(o.first_seen_at_utc,o.observed_at_utc)<s.started_at_utc
    ) as left_censored_candidate_observation_count,
    count(distinct o.strategy_instance_id) filter(
      where s.started_at_utc is not null
        and o.observed_at_utc>=s.started_at_utc
        and o.status='SHADOW_CANDIDATE'
        and o.strategy_instance_id is not null
        and coalesce(o.first_seen_at_utc,o.observed_at_utc)>=s.started_at_utc
    ) as post_baseline_candidate_episode_count
  from specs s
  left join public.alpha_hunter_strategy_observations_v01 o
    on s.started_at_utc is not null
   and o.observed_at_utc>=s.started_at_utc
  group by s.spec_id
),
forward_counts as (
  select
    s.spec_id,
    count(f.episode_id) filter(
      where s.started_at_utc is not null
        and f.first_observed_at_utc>=s.started_at_utc
        and f.horizon_hours=24
    ) as post_baseline_24h_outcome_rows,
    count(f.episode_id) filter(
      where s.started_at_utc is not null
        and f.first_observed_at_utc>=s.started_at_utc
        and f.horizon_hours=24
        and f.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
    ) as post_baseline_24h_triggered_rows,
    count(f.episode_id) filter(
      where s.started_at_utc is not null
        and f.first_observed_at_utc>=s.started_at_utc
        and f.horizon_hours=24
        and f.entry_trigger_status in ('TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT')
        and f.path_measurement_quality='COMPLETE_ENOUGH'
        and f.ordering_ambiguous=false
    ) as post_baseline_24h_economic_eligible_rows,
    count(f.episode_id) filter(
      where s.started_at_utc is not null
        and f.first_observed_at_utc<s.started_at_utc
        and f.evaluated_at_utc>=s.started_at_utc
        and f.horizon_hours=24
    ) as left_censored_24h_outcome_rows
  from specs s
  left join public.alpha_hunter_strategy_forward_outcomes_v01 f
    on s.started_at_utc is not null
   and f.evaluated_at_utc>=s.started_at_utc
  group by s.spec_id
),
economics_counts as (
  select
    s.spec_id,
    count(e.episode_id) as completed_paper_economics_rows,
    count(e.episode_id) filter(
      where e.first_observed_at_utc<s.started_at_utc
    ) as contaminated_pre_baseline_economics_rows,
    count(e.episode_id)-count(distinct e.episode_id)
      as duplicate_economics_episode_rows
  from specs s
  left join public.alpha_hunter_strategy_paper_economics_v01 e
    on e.spec_id=s.spec_id
  group by s.spec_id
),
duplicate_outcomes as (
  select
    s.spec_id,
    coalesce(sum(x.duplicate_rows),0)::bigint as duplicate_24h_outcome_rows
  from specs s
  left join lateral (
    select greatest(count(*)-1,0)::bigint as duplicate_rows
    from public.alpha_hunter_strategy_forward_outcomes_v01 f
    where s.started_at_utc is not null
      and f.first_observed_at_utc>=s.started_at_utc
      and f.horizon_hours=24
    group by f.episode_id,f.horizon_hours
    having count(*)>1
  ) x on true
  group by s.spec_id
)
select
  s.spec_id,
  s.preregistered_at_utc,
  s.started_at_utc,
  s.baseline_run_id,
  coalesce(ec.post_baseline_episode_count,0) as post_baseline_episode_count,
  coalesce(co.post_baseline_candidate_observation_count,0)
    as post_baseline_candidate_observation_count,
  coalesce(co.left_censored_candidate_observation_count,0)
    as left_censored_candidate_observation_count,
  coalesce(co.post_baseline_candidate_episode_count,0)
    as post_baseline_candidate_episode_count,
  coalesce(fc.post_baseline_24h_outcome_rows,0)
    as post_baseline_24h_outcome_rows,
  coalesce(fc.post_baseline_24h_triggered_rows,0)
    as post_baseline_24h_triggered_rows,
  coalesce(fc.post_baseline_24h_economic_eligible_rows,0)
    as post_baseline_24h_economic_eligible_rows,
  coalesce(fc.left_censored_24h_outcome_rows,0)
    as left_censored_24h_outcome_rows,
  coalesce(pc.completed_paper_economics_rows,0)
    as completed_paper_economics_rows,
  coalesce(pc.contaminated_pre_baseline_economics_rows,0)
    as contaminated_pre_baseline_economics_rows,
  coalesce(pc.duplicate_economics_episode_rows,0)
    as duplicate_economics_episode_rows,
  coalesce(d.duplicate_24h_outcome_rows,0)
    as duplicate_24h_outcome_rows,
  (
    coalesce(pc.contaminated_pre_baseline_economics_rows,0)=0
    and coalesce(pc.duplicate_economics_episode_rows,0)=0
    and coalesce(d.duplicate_24h_outcome_rows,0)=0
  ) as sealed_sample_integrity_ok,
  case
    when s.started_at_utc is null then 'WAITING_FOR_BASELINE'
    when coalesce(pc.contaminated_pre_baseline_economics_rows,0)>0
      then 'FAIL_PRE_BASELINE_CONTAMINATION'
    when coalesce(pc.duplicate_economics_episode_rows,0)>0
      or coalesce(d.duplicate_24h_outcome_rows,0)>0
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
left join episode_counts ec on ec.spec_id=s.spec_id
left join candidate_observations co on co.spec_id=s.spec_id
left join forward_counts fc on fc.spec_id=s.spec_id
left join economics_counts pc on pc.spec_id=s.spec_id
left join duplicate_outcomes d on d.spec_id=s.spec_id;

revoke all on public.alpha_hunter_profitability_sample_integrity_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profitability_sample_integrity_v01
  to service_role;
