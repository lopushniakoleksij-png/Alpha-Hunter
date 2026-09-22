-- Alpha Hunter sealed profitability scan-cadence contract v0.1
--
-- Additive scientific infrastructure. It freezes the real-time sampling cadence
-- for a sealed profitability cohort without changing strategy logic.
--
-- The final hourly cohort is expected to run from the scheduled GitHub workflow
-- (cron: 0 * * * *). Manual reruns before baseline are diagnostic only; after
-- baseline, short-interval extra scans are surfaced as cadence violations.

create table if not exists public.alpha_hunter_profitability_cadence_contract_v01 (
  spec_id text primary key
    references public.alpha_hunter_profitability_test_specs_v01(spec_id),
  baseline_not_before_utc timestamptz not null,
  expected_frequency_minutes integer not null default 60
    check(expected_frequency_minutes=60),
  minimum_interval_minutes integer not null default 45
    check(minimum_interval_minutes>=1),
  maximum_interval_minutes integer not null default 90
    check(maximum_interval_minutes>=60),
  expected_schedule text not null default '0 * * * *',
  no_manual_scans_after_baseline boolean not null default true
    check(no_manual_scans_after_baseline=true),
  scientific_role text not null default 'SEALED_SCAN_CADENCE_CONTRACT',
  created_at timestamptz not null default clock_timestamp(),
  frozen boolean not null default true check(frozen=true),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE')
);

alter table public.alpha_hunter_profitability_cadence_contract_v01
  enable row level security;
revoke all on public.alpha_hunter_profitability_cadence_contract_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_profitability_cadence_contract_v01
  to service_role;

drop trigger if exists trg_ah_profitability_cadence_append_only_v01
  on public.alpha_hunter_profitability_cadence_contract_v01;
create trigger trg_ah_profitability_cadence_append_only_v01
before update or delete on public.alpha_hunter_profitability_cadence_contract_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace view public.alpha_hunter_profitability_cadence_integrity_v01
with (security_invoker=true,security_barrier=true)
as
with contract as (
  select
    c.*,
    a.started_at_utc,
    a.baseline_git_commit,
    a.baseline_config_sha256
  from public.alpha_hunter_profitability_cadence_contract_v01 c
  left join public.alpha_hunter_profitability_test_activations_v01 a
    on a.spec_id=c.spec_id
),
scans as (
  select
    c.spec_id,
    p.run_id,
    p.collected_at_utc,
    lag(p.collected_at_utc) over(
      partition by c.spec_id order by p.collected_at_utc,p.run_id
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
),
classified as (
  select
    s.*,
    case when prior_scan_at_utc is null then null
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
