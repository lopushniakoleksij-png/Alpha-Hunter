-- Alpha Hunter sealed cadence staleness v0.3
--
-- Conservative audit-only fix: cadence integrity must fail when the
-- source-isolated production scanner itself becomes stale, even if there is
-- no later scan from which an excessive interval could be computed.
--
-- No strategy, RR, execution, profitability, or promotion threshold changes.

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
),
agg as (
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
      as maximum_observed_interval_minutes
  from contract c
  left join classified x on x.spec_id=c.spec_id
  group by
    c.spec_id,c.baseline_not_before_utc,c.started_at_utc,
    c.expected_frequency_minutes,c.minimum_interval_minutes,
    c.maximum_interval_minutes,c.expected_schedule
)
select
  a.spec_id,
  a.baseline_not_before_utc,
  a.started_at_utc,
  a.expected_frequency_minutes,
  a.minimum_interval_minutes,
  a.maximum_interval_minutes,
  a.expected_schedule,
  a.post_baseline_scan_count,
  a.first_counted_scan_at_utc,
  a.latest_counted_scan_at_utc,
  a.too_frequent_scan_intervals,
  a.excessive_gap_intervals,
  a.identity_mismatch_scan_count,
  a.minimum_observed_interval_minutes,
  a.maximum_observed_interval_minutes,
  (
    a.started_at_utc is not null
    and a.started_at_utc>=a.baseline_not_before_utc
    and a.latest_counted_scan_at_utc is not null
    and clock_timestamp()-a.latest_counted_scan_at_utc
      <= a.maximum_interval_minutes*interval '1 minute'
    and a.too_frequent_scan_intervals=0
    and a.excessive_gap_intervals=0
    and a.identity_mismatch_scan_count=0
  ) as cadence_integrity_ok,
  case
    when a.started_at_utc is null then 'WAITING_FOR_BASELINE'
    when a.started_at_utc<a.baseline_not_before_utc
      then 'FAIL_BASELINE_BEFORE_NOT_BEFORE'
    when a.too_frequent_scan_intervals>0
      then 'FAIL_EXTRA_SCAN_FREQUENCY'
    when a.excessive_gap_intervals>0
      then 'FAIL_SCAN_GAP'
    when a.identity_mismatch_scan_count>0
      then 'FAIL_BUILD_OR_CONFIG_IDENTITY'
    when a.latest_counted_scan_at_utc is null
      then 'FAIL_NO_SOURCE_SCANS_AFTER_BASELINE'
    when clock_timestamp()-a.latest_counted_scan_at_utc
      > a.maximum_interval_minutes*interval '1 minute'
      then 'FAIL_SCAN_STALE'
    else 'PASS'
  end as cadence_integrity_status,
  true as audit_only,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from agg a;

revoke all on public.alpha_hunter_profitability_cadence_integrity_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profitability_cadence_integrity_v01
  to service_role;
