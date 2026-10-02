-- Alpha Hunter shadow profit-management challenger v0.1
--
-- Purpose:
--   Compare simple preregistered profit-management challengers against completed
--   flat-to-flat account outcomes using only canonical sampled position evidence.
--
-- Policy basis:
--   Alpha Hunter lifecycle.py already treats +3% and +5% expansion as canonical
--   lifecycle milestones. These challengers reuse those existing milestones and
--   are NOT tuned to any single trade.
--
-- Important limits:
--   * sampled position marks are not tick-level price paths;
--   * a shadow stop trigger is recognized only when an observed canonical mark
--     crosses the computed challenger stop before the actual exit;
--   * shadow trigger exits use that observed mark, not an invented stop fill;
--   * no fee/funding/net-PnL counterfactual is claimed;
--   * no live stop, target, order, leverage, threshold, or permission is changed.

create or replace view public.alpha_hunter_profit_management_shadow_v01
with (security_invoker=true,security_barrier=true)
as
with policies as (
  select *
  from (
    values
      (
        'BE_AFTER_3PCT'::text,
        3.0::double precision,
        0.0::double precision,
        'EXISTING_LIFECYCLE_3PCT_MILESTONE'::text
      ),
      (
        'LOCK_25_AFTER_5PCT'::text,
        5.0::double precision,
        0.25::double precision,
        'EXISTING_LIFECYCLE_5PCT_MILESTONE'::text
      ),
      (
        'LOCK_50_AFTER_5PCT'::text,
        5.0::double precision,
        0.50::double precision,
        'EXISTING_LIFECYCLE_5PCT_MILESTONE'::text
      )
  ) as p(policy_id,activation_favorable_pct,lock_fraction,threshold_basis)
),
episodes as (
  select
    r.roundtrip_episode_id,
    r.symbol,
    r.direction,
    r.opened_or_first_seen_at_utc,
    r.closed_at_utc,
    r.opening_vwap,
    r.closing_vwap,
    r.opened_qty,
    r.profit_field_sum as actual_gross_profit_field,
    r.signed_trading_fee_sum as actual_signed_trading_fee_sum,
    r.fee_adjusted_profit_ex_funding as actual_fee_adjusted_profit_ex_funding,
    r.funding_coverage_complete,
    r.funding_coverage_status,
    r.full_economic_pnl_claim_permitted,
    r.verified_alpha_hunter_execution,
    r.alpha_hunter_execution_claim_permitted
  from public.alpha_hunter_roundtrip_economic_outcome_v01 r
  where r.closed_at_utc is not null
    and r.direction in ('LONG','SHORT')
    and r.opening_vwap is not null
    and r.opened_qty is not null
    and r.opened_qty > 0
),
samples_base as (
  select
    e.*,
    p.position_snapshot_id,
    p.captured_at_utc,
    p.mark_price,
    p.unrealized_pnl_usdt,
    case
      when e.direction='LONG' then
        max(p.mark_price) over (
          partition by e.roundtrip_episode_id
          order by p.captured_at_utc,p.position_snapshot_id
          rows between unbounded preceding and current row
        )
      else
        min(p.mark_price) over (
          partition by e.roundtrip_episode_id
          order by p.captured_at_utc,p.position_snapshot_id
          rows between unbounded preceding and current row
        )
    end as running_favorable_mark
  from episodes e
  join public.alpha_hunter_open_position_snapshots p
    on p.symbol=e.symbol
   and p.direction=e.direction
   and p.captured_at_utc >= e.opened_or_first_seen_at_utc
   and p.captured_at_utc <= e.closed_at_utc
   and p.mark_price is not null
),
samples as (
  select
    s.*,
    case
      when s.opening_vwap=0 then null
      when s.direction='LONG' then
        100.0 * (s.running_favorable_mark-s.opening_vwap)/s.opening_vwap
      else
        100.0 * (s.opening_vwap-s.running_favorable_mark)/s.opening_vwap
    end as running_favorable_pct
  from samples_base s
),
episode_sampling as (
  select
    e.roundtrip_episode_id,
    count(s.position_snapshot_id)::bigint as position_sample_count,
    min(s.captured_at_utc) as first_position_sample_at_utc,
    max(s.captured_at_utc) as last_position_sample_at_utc,
    max(s.running_favorable_pct) as observed_max_favorable_pct
  from episodes e
  left join samples s using(roundtrip_episode_id)
  group by e.roundtrip_episode_id
),
candidate_samples as (
  select
    s.*,
    p.policy_id,
    p.activation_favorable_pct,
    p.lock_fraction,
    p.threshold_basis,
    (s.running_favorable_pct >= p.activation_favorable_pct) as policy_active,
    case
      when s.running_favorable_pct < p.activation_favorable_pct then null
      when s.direction='LONG' then
        s.opening_vwap
        + p.lock_fraction*(s.running_favorable_mark-s.opening_vwap)
      else
        s.opening_vwap
        - p.lock_fraction*(s.opening_vwap-s.running_favorable_mark)
    end as shadow_stop_price
  from samples s
  cross join policies p
),
crossings as (
  select
    c.*,
    case
      when not c.policy_active or c.shadow_stop_price is null then false
      when c.direction='LONG' then c.mark_price <= c.shadow_stop_price
      else c.mark_price >= c.shadow_stop_price
    end as stop_crossed_on_sample
  from candidate_samples c
),
activation as (
  select
    c.roundtrip_episode_id,
    c.policy_id,
    min(c.captured_at_utc) filter(where c.policy_active)
      as shadow_policy_activated_at_utc
  from crossings c
  group by c.roundtrip_episode_id,c.policy_id
),
first_trigger as (
  select distinct on (c.roundtrip_episode_id,c.policy_id)
    c.roundtrip_episode_id,
    c.policy_id,
    c.captured_at_utc as shadow_trigger_at_utc,
    c.mark_price as shadow_trigger_observed_mark,
    c.shadow_stop_price as shadow_stop_at_trigger,
    c.running_favorable_mark as running_favorable_mark_at_trigger,
    c.running_favorable_pct as running_favorable_pct_at_trigger
  from crossings c
  where c.stop_crossed_on_sample
  order by
    c.roundtrip_episode_id,
    c.policy_id,
    c.captured_at_utc,
    c.position_snapshot_id
),
outcomes as (
  select
    e.*,
    p.policy_id,
    p.activation_favorable_pct,
    p.lock_fraction,
    p.threshold_basis,
    es.position_sample_count,
    es.first_position_sample_at_utc,
    es.last_position_sample_at_utc,
    es.observed_max_favorable_pct,
    a.shadow_policy_activated_at_utc,
    t.shadow_trigger_at_utc,
    t.shadow_trigger_observed_mark,
    t.shadow_stop_at_trigger,
    t.running_favorable_mark_at_trigger,
    t.running_favorable_pct_at_trigger,
    (t.shadow_trigger_at_utc is not null) as shadow_trigger_observed,
    case
      when t.shadow_trigger_at_utc is not null
        then t.shadow_trigger_observed_mark
      else e.closing_vwap
    end as shadow_exit_price,
    case
      when t.shadow_trigger_at_utc is not null
        then 'OBSERVED_CANONICAL_MARK_CROSS'
      when a.shadow_policy_activated_at_utc is not null
        then 'ACTUAL_EXIT_NO_OBSERVED_SHADOW_CROSS'
      else 'POLICY_NEVER_ACTIVATED'
    end as shadow_exit_reason
  from episodes e
  cross join policies p
  left join episode_sampling es using(roundtrip_episode_id)
  left join activation a
    on a.roundtrip_episode_id=e.roundtrip_episode_id
   and a.policy_id=p.policy_id
  left join first_trigger t
    on t.roundtrip_episode_id=e.roundtrip_episode_id
   and t.policy_id=p.policy_id
)
select
  o.roundtrip_episode_id,
  o.symbol,
  o.direction,
  o.opened_or_first_seen_at_utc,
  o.closed_at_utc,
  o.opening_vwap,
  o.closing_vwap,
  o.opened_qty,

  o.policy_id,
  o.activation_favorable_pct,
  o.lock_fraction,
  o.threshold_basis,

  o.position_sample_count,
  o.first_position_sample_at_utc,
  o.last_position_sample_at_utc,
  o.observed_max_favorable_pct,
  (o.position_sample_count >= 2) as challenger_evidence_eligible,

  o.shadow_policy_activated_at_utc,
  o.shadow_trigger_at_utc,
  o.shadow_trigger_observed_mark,
  o.shadow_stop_at_trigger,
  o.running_favorable_mark_at_trigger,
  o.running_favorable_pct_at_trigger,
  o.shadow_trigger_observed,
  o.shadow_exit_price,
  o.shadow_exit_reason,

  o.actual_gross_profit_field,
  case
    when o.shadow_exit_price is null then null
    when o.direction='LONG' then
      (o.shadow_exit_price-o.opening_vwap)*o.opened_qty
    else
      (o.opening_vwap-o.shadow_exit_price)*o.opened_qty
  end as shadow_gross_pnl,

  case
    when o.shadow_exit_price is null then null
    when o.direction='LONG' then
      ((o.shadow_exit_price-o.opening_vwap)*o.opened_qty)
      - o.actual_gross_profit_field
    else
      ((o.opening_vwap-o.shadow_exit_price)*o.opened_qty)
      - o.actual_gross_profit_field
  end as shadow_gross_delta_vs_actual,

  o.actual_signed_trading_fee_sum,
  o.actual_fee_adjusted_profit_ex_funding,
  o.funding_coverage_complete,
  o.funding_coverage_status,
  o.full_economic_pnl_claim_permitted,

  true as sampled_path_limitation,
  (o.shadow_trigger_at_utc is not null) as sampled_mark_used_as_shadow_exit,
  false as counterfactual_fee_claim_permitted,
  false as counterfactual_funding_claim_permitted,
  false as counterfactual_net_pnl_claim_permitted,
  false as management_change_permitted,
  false as stop_change_permitted,
  false as target_change_permitted,
  false as promotion_permitted,
  o.verified_alpha_hunter_execution,
  o.alpha_hunter_execution_claim_permitted,
  'SHADOW_SAMPLED_PROFIT_MANAGEMENT_CHALLENGER'::text as scientific_role,
  'profit-management-shadow-challenger-v0.1'::text as model_version,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from outcomes o;


create or replace view public.alpha_hunter_profit_management_shadow_status_v01
with (security_invoker=true,security_barrier=true)
as
with policy_rollup as (
  select
    policy_id,
    activation_favorable_pct,
    lock_fraction,
    threshold_basis,
    count(*) filter(where challenger_evidence_eligible)::bigint
      as eligible_episode_count,
    count(*) filter(
      where challenger_evidence_eligible and direction='LONG'
    )::bigint as eligible_long_count,
    count(*) filter(
      where challenger_evidence_eligible and direction='SHORT'
    )::bigint as eligible_short_count,
    count(*) filter(
      where challenger_evidence_eligible
        and shadow_policy_activated_at_utc is not null
    )::bigint as activated_episode_count,
    count(*) filter(
      where challenger_evidence_eligible
        and shadow_trigger_observed
    )::bigint as observed_trigger_count,
    sum(shadow_gross_delta_vs_actual) filter(
      where challenger_evidence_eligible
    ) as total_shadow_gross_delta_vs_actual,
    avg(shadow_gross_delta_vs_actual) filter(
      where challenger_evidence_eligible
    ) as avg_shadow_gross_delta_vs_actual,
    count(*) filter(
      where challenger_evidence_eligible
        and shadow_gross_delta_vs_actual > 1e-12
    )::bigint as positive_delta_episode_count,
    count(*) filter(
      where challenger_evidence_eligible
        and shadow_gross_delta_vs_actual < -1e-12
    )::bigint as negative_delta_episode_count,
    count(*) filter(
      where challenger_evidence_eligible
        and abs(shadow_gross_delta_vs_actual) <= 1e-12
    )::bigint as unchanged_episode_count
  from public.alpha_hunter_profit_management_shadow_v01
  group by policy_id,activation_favorable_pct,lock_fraction,threshold_basis
)
select
  p.*,
  30::bigint as minimum_total_episode_gate,
  10::bigint as minimum_per_direction_gate,
  (
    p.eligible_episode_count >= 30
    and p.eligible_long_count >= 10
    and p.eligible_short_count >= 10
  ) as minimum_operational_cohort_gate_met,
  case
    when p.eligible_episode_count < 30 then 'INSUFFICIENT_TOTAL_COHORT'
    when p.eligible_long_count < 10 then 'INSUFFICIENT_LONG_COHORT'
    when p.eligible_short_count < 10 then 'INSUFFICIENT_SHORT_COHORT'
    else 'MINIMUM_COHORT_MET_REQUIRES_FORWARD_VALIDATION'
  end as promotion_gate_status,
  false as statistical_validation_claim_permitted,
  false as production_superiority_claim_permitted,
  false as management_change_permitted,
  false as stop_change_permitted,
  false as target_change_permitted,
  false as promotion_permitted,
  true as shadow_only,
  false as trade_permission,
  'NONE'::text as order_path
from policy_rollup p;


revoke all on public.alpha_hunter_profit_management_shadow_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_profit_management_shadow_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_profit_management_shadow_v01
  to service_role;
grant select on public.alpha_hunter_profit_management_shadow_status_v01
  to service_role;
