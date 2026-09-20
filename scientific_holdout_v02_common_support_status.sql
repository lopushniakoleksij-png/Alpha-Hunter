-- Alpha Hunter scientific holdout v0.2 common-support monitor
--
-- Non-binding health surface only.
-- Uses candidate-time covariates and assignment labels; does NOT read outcomes,
-- does NOT freeze pairs, and does NOT alter the preregistered matching rule.
--
-- Frozen v0.2 exact support requirements:
--   direction, lifecycle, liquidity_state, candidate_quality_status
--   + absolute decision-time gap <= 24 hours.
--
-- The view reports whether each current TEST/CONTROL row has at least one
-- compatible counterpart. "Exact-stratum upper bound" ignores the 24h caliper
-- and is deliberately labelled an upper bound, not a matched-pair count.

create or replace view public.alpha_hunter_scientific_holdout_v02_common_support_status
with (security_invoker=true,security_barrier=true)
as
with b as (
  select
    binding_id,
    group_name,
    direction,
    lifecycle,
    liquidity_state,
    candidate_quality_status,
    decision_available_at_utc,
    symbol
  from public.alpha_hunter_scientific_holdout_bindings
  where spec_id='AH-EARLY-DIRECTION-GEOMETRY-HOLDOUT-V02'
    and group_name in ('TEST','CONTROL_POOL')
    and direction is not null
    and lifecycle is not null
    and liquidity_state is not null
    and candidate_quality_status is not null
),
support as (
  select
    x.binding_id,
    x.group_name,
    x.direction,
    x.symbol,
    x.decision_available_at_utc,
    exists (
      select 1
      from b y
      where y.group_name<>x.group_name
        and y.direction=x.direction
        and y.lifecycle=x.lifecycle
        and y.liquidity_state=x.liquidity_state
        and y.candidate_quality_status=x.candidate_quality_status
        and abs(extract(epoch from (x.decision_available_at_utc-y.decision_available_at_utc)))
              <= 24*3600
    ) as has_24h_common_support
  from b x
),
strata as (
  select
    direction,lifecycle,liquidity_state,candidate_quality_status,
    count(*) filter(where group_name='TEST') as test_n,
    count(*) filter(where group_name='CONTROL_POOL') as control_n
  from b
  group by 1,2,3,4
),
strata_by_direction as (
  select
    direction,
    coalesce(sum(least(test_n,control_n)),0)::bigint
      as exact_stratum_upper_bound_pairs
  from strata
  group by direction
),
strata_all as (
  select
    coalesce(sum(least(test_n,control_n)),0)::bigint
      as exact_stratum_upper_bound_pairs
  from strata
),
rows_by_direction as (
  select
    direction,
    count(*) filter(where group_name='TEST')::bigint as test_rows,
    count(*) filter(where group_name='CONTROL_POOL')::bigint as control_rows,
    count(*) filter(
      where group_name='TEST' and has_24h_common_support
    )::bigint as test_rows_with_24h_common_support,
    count(*) filter(
      where group_name='CONTROL_POOL' and has_24h_common_support
    )::bigint as control_rows_with_24h_common_support,
    count(distinct symbol)::bigint as symbols,
    count(distinct decision_available_at_utc::date)::bigint as utc_days
  from support
  group by direction
),
rows_all as (
  select
    count(*) filter(where group_name='TEST')::bigint as test_rows,
    count(*) filter(where group_name='CONTROL_POOL')::bigint as control_rows,
    count(*) filter(
      where group_name='TEST' and has_24h_common_support
    )::bigint as test_rows_with_24h_common_support,
    count(*) filter(
      where group_name='CONTROL_POOL' and has_24h_common_support
    )::bigint as control_rows_with_24h_common_support,
    count(distinct symbol)::bigint as symbols,
    count(distinct decision_available_at_utc::date)::bigint as utc_days
  from support
)
select
  r.direction as scope,
  r.test_rows,
  r.control_rows,
  r.test_rows_with_24h_common_support,
  r.control_rows_with_24h_common_support,
  s.exact_stratum_upper_bound_pairs,
  r.symbols,
  r.utc_days,
  case
    when r.test_rows=0 or r.control_rows=0 then 'WAITING_FOR_BOTH_ARMS'
    when r.test_rows_with_24h_common_support=0
      or r.control_rows_with_24h_common_support=0
      then 'NO_CURRENT_24H_COMMON_SUPPORT'
    else 'COMMON_SUPPORT_PRESENT'
  end as support_status,
  false as matched_pairs_frozen,
  false as outcomes_read,
  false as confirmatory_analysis_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NON_BINDING_CANDIDATE_TIME_COMMON_SUPPORT_ONLY'::text as claim_ceiling,
  'scientific-holdout-v02-common-support-v0.1'::text as model_version
from rows_by_direction r
left join strata_by_direction s using(direction)

union all

select
  'ALL'::text as scope,
  r.test_rows,
  r.control_rows,
  r.test_rows_with_24h_common_support,
  r.control_rows_with_24h_common_support,
  s.exact_stratum_upper_bound_pairs,
  r.symbols,
  r.utc_days,
  case
    when r.test_rows=0 or r.control_rows=0 then 'WAITING_FOR_BOTH_ARMS'
    when r.test_rows_with_24h_common_support=0
      or r.control_rows_with_24h_common_support=0
      then 'NO_CURRENT_24H_COMMON_SUPPORT'
    else 'COMMON_SUPPORT_PRESENT'
  end as support_status,
  false as matched_pairs_frozen,
  false as outcomes_read,
  false as confirmatory_analysis_permitted,
  false as production_promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NON_BINDING_CANDIDATE_TIME_COMMON_SUPPORT_ONLY'::text as claim_ceiling,
  'scientific-holdout-v02-common-support-v0.1'::text as model_version
from rows_all r
cross join strata_all s;

revoke all on public.alpha_hunter_scientific_holdout_v02_common_support_status
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_scientific_holdout_v02_common_support_status
  to service_role;
