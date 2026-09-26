-- Alpha Hunter sealed audit source-scope v0.2
--
-- DB-only audit correction. Cadence and sample-integrity views must ignore
-- foreign/legacy scanner rows exactly like the source-isolated profitability
-- cohort. Output column contracts are preserved.

create or replace view public.alpha_hunter_profitability_cadence_integrity_v01
with (security_invoker=true,security_barrier=true)
as
with contract as (
  select
    c.spec_id,
    c.baseline_not_before_utc,
    c.expected_frequency_minutes,
    c.minimum_interval_minutes,
    c.maximum_interval_minutes,
    c.expected_schedule,
    a.started_at_utc,
    a.baseline_git_commit,
    a.baseline_config_sha256,
    s.required_run_source
  from public.alpha_hunter_profitability_cadence_contract_v01 c
  join public.alpha_hunter_profitability_test_specs_v01 s
    on s.spec_id=c.spec_id
  left join public.alpha_hunter_profitability_test_activations_v01 a
    on a.spec_id=c.spec_id
),
scans as (
  select
    c.spec_id,
    p.run_id,
    p.collected_at_utc,
    lag(p.collected_at_utc) over(
      partition by c.spec_id
      order by p.collected_at_utc,p.run_id
    ) as prior_scan_at_utc,
    p.payload->'validation_identity'->>'git_commit' as git_commit,
    p.payload->'validation_identity'->>'config_sha256' as config_sha256,
    c.minimum_interval_minutes,
    c.maximum_interval_minutes,
    c.baseline_git_commit,
    c.baseline_config_sha256
  from contract c
  join public.alpha_hunter_snapshots p
    on c.started_at_utc is not null
   and p.collected_at_utc>=c.started_at_utc
   and p.payload->'validation_identity'->>'run_source'
      =c.required_run_source
),
classified as (
  select
    s.*,
    case
      when prior_scan_at_utc is null then null
      else extract(epoch from (collected_at_utc-prior_scan_at_utc))/60.0
    end as interval_minutes,
    (
      git_commit=baseline_git_commit
      and config_sha256=baseline_config_sha256
    ) as identity_matches_baseline
  from scans s
)
select
  c.spec_id,
  c.baseline_not_before_utc,
  c.started_at_utc,
  c.expected_frequency_minutes,
  c.minimum_interval_minutes,
  c.maximum_interval_minutes,
  c.expected_schedule,
  count(x.run_id) as post_baseline_scan_count,
  min(x.collected_at_utc) as first_counted_scan_at_utc,
  max(x.collected_at_utc) as latest_counted_scan_at_utc,
  count(*) filter(
    where x.interval_minutes is not null
      and x.interval_minutes<c.minimum_interval_minutes
  ) as too_frequent_scan_intervals,
  count(*) filter(
    where x.interval_minutes is not null
      and x.interval_minutes>c.maximum_interval_minutes
  ) as excessive_gap_intervals,
  count(*) filter(
    where x.run_id is not null
      and not coalesce(x.identity_matches_baseline,false)
  ) as identity_mismatch_scan_count,
  min(x.interval_minutes) filter(where x.interval_minutes is not null)
    as minimum_observed_interval_minutes,
  max(x.interval_minutes) filter(where x.interval_minutes is not null)
    as maximum_observed_interval_minutes,
  (
    c.started_at_utc is not null
    and c.started_at_utc>=c.baseline_not_before_utc
    and count(*) filter(
      where x.interval_minutes is not null
        and x.interval_minutes<c.minimum_interval_minutes
    )=0
    and count(*) filter(
      where x.interval_minutes is not null
        and x.interval_minutes>c.maximum_interval_minutes
    )=0
    and count(*) filter(
      where x.run_id is not null
        and not coalesce(x.identity_matches_baseline,false)
    )=0
  ) as cadence_integrity_ok,
  case
    when c.started_at_utc is null then 'WAITING_FOR_BASELINE'
    when c.started_at_utc<c.baseline_not_before_utc
      then 'FAIL_BASELINE_BEFORE_NOT_BEFORE'
    when count(*) filter(
      where x.interval_minutes is not null
        and x.interval_minutes<c.minimum_interval_minutes
    )>0 then 'FAIL_EXTRA_SCAN_FREQUENCY'
    when count(*) filter(
      where x.interval_minutes is not null
        and x.interval_minutes>c.maximum_interval_minutes
    )>0 then 'FAIL_SCAN_GAP'
    when count(*) filter(
      where x.run_id is not null
        and not coalesce(x.identity_matches_baseline,false)
    )>0 then 'FAIL_BUILD_OR_CONFIG_IDENTITY'
    else 'PASS'
  end as cadence_integrity_status,
  true as audit_only,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from contract c
left join classified x on x.spec_id=c.spec_id
group by
  c.spec_id,c.baseline_not_before_utc,c.started_at_utc,
  c.expected_frequency_minutes,c.minimum_interval_minutes,
  c.maximum_interval_minutes,c.expected_schedule;

revoke all on public.alpha_hunter_profitability_cadence_integrity_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profitability_cadence_integrity_v01
  to service_role;


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
),
source_episodes as (
  select
    s.spec_id,
    e.*
  from specs s
  join public.alpha_hunter_strategy_episodes_v01 e
    on s.started_at_utc is not null
  join public.alpha_hunter_strategy_observations_v01 fo
    on fo.observation_id=e.first_observation_id
  join public.alpha_hunter_snapshots p
    on p.run_id=fo.run_id
   and p.payload->'validation_identity'->>'run_source'
      =s.required_run_source
),
episode_counts as (
  select
    s.spec_id,
    count(e.episode_id) filter(
      where e.first_observed_at_utc>=s.started_at_utc
    ) as post_baseline_episode_count
  from specs s
  left join source_episodes e on e.spec_id=s.spec_id
  group by s.spec_id
),
candidate_observations as (
  select
    s.spec_id,
    count(o.observation_id) filter(
      where o.observed_at_utc>=s.started_at_utc
        and o.status='SHADOW_CANDIDATE'
    ) as post_baseline_candidate_observation_count,
    count(o.observation_id) filter(
      where o.observed_at_utc>=s.started_at_utc
        and o.status='SHADOW_CANDIDATE'
        and coalesce(o.first_seen_at_utc,o.observed_at_utc)<s.started_at_utc
    ) as left_censored_candidate_observation_count,
    count(distinct o.strategy_instance_id) filter(
      where o.observed_at_utc>=s.started_at_utc
        and o.status='SHADOW_CANDIDATE'
        and o.strategy_instance_id is not null
        and coalesce(o.first_seen_at_utc,o.observed_at_utc)>=s.started_at_utc
    ) as post_baseline_candidate_episode_count
  from specs s
  left join public.alpha_hunter_strategy_observations_v01 o
    on s.started_at_utc is not null
   and o.observed_at_utc>=s.started_at_utc
  left join public.alpha_hunter_snapshots p
    on p.run_id=o.run_id
   and p.payload->'validation_identity'->>'run_source'
      =s.required_run_source
  where o.observation_id is null or p.run_id is not null
  group by s.spec_id
),
forward_counts as (
  select
    s.spec_id,
    count(f.episode_id) filter(
      where f.first_observed_at_utc>=s.started_at_utc
        and f.horizon_hours=24
    ) as post_baseline_24h_outcome_rows,
    count(f.episode_id) filter(
      where f.first_observed_at_utc>=s.started_at_utc
        and f.horizon_hours=24
        and f.entry_trigger_status in (
          'TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT'
        )
    ) as post_baseline_24h_triggered_rows,
    count(f.episode_id) filter(
      where f.first_observed_at_utc>=s.started_at_utc
        and f.horizon_hours=24
        and f.entry_trigger_status in (
          'TRIGGERED_EXECUTE_NOW','TRIGGERED_LIMIT'
        )
        and f.path_measurement_quality='COMPLETE_ENOUGH'
        and f.ordering_ambiguous=false
    ) as post_baseline_24h_economic_eligible_rows,
    count(f.episode_id) filter(
      where f.first_observed_at_utc<s.started_at_utc
        and f.evaluated_at_utc>=s.started_at_utc
        and f.horizon_hours=24
    ) as left_censored_24h_outcome_rows
  from specs s
  left join source_episodes ep on ep.spec_id=s.spec_id
  left join public.alpha_hunter_strategy_forward_outcomes_v01 f
    on f.episode_id=ep.episode_id
   and s.started_at_utc is not null
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
    coalesce(sum(x.duplicate_rows),0)::bigint
      as duplicate_24h_outcome_rows
  from specs s
  left join lateral (
    select greatest(count(*)-1,0)::bigint as duplicate_rows
    from source_episodes ep
    join public.alpha_hunter_strategy_forward_outcomes_v01 f
      on f.episode_id=ep.episode_id
    where ep.spec_id=s.spec_id
      and s.started_at_utc is not null
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
  coalesce(ec.post_baseline_episode_count,0)
    as post_baseline_episode_count,
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
