-- Alpha Hunter R8 executed-paper horizon integrity observability v0.1
--
-- Issue #318.
--
-- Purpose:
--   Make the active R8 executed-paper cohort's relationship to the frozen
--   24-hour profitability-test horizon explicit without changing the active
--   paper execution policy or mutating the scientific sample.
--
-- Important:
--   R8 paper positions currently close by protective SL/TP observation.
--   This layer DOES NOT invent a terminal 24h exit and DOES NOT exclude,
--   quarantine, rewrite, or reclassify any completed trade.
--
-- Safety:
--   read-only views only;
--   no execution-policy mutation;
--   no profitability-sample mutation;
--   no threshold/R8 fingerprint change;
--   no trade permission or exchange order path.

create or replace view public.alpha_hunter_r8_horizon_position_status_v01
with (security_invoker=true,security_barrier=true)
as
with spec as (
  select
    s.spec_id,
    s.evaluation_horizon_hours,
    a.started_at_utc
  from public.alpha_hunter_profitability_test_specs_v01 s
  join public.alpha_hunter_profitability_test_activations_v01 a
    on a.spec_id=s.spec_id
  where s.spec_id='SEALED-ARCH-V14R8-EXEC-PAPER-FP-20M-20261003'
  limit 1
),
active as (
  select
    'ACTIVE'::text as row_class,
    m.order_id as entry_order_id,
    m.decision_id,
    m.symbol,
    m.strategy_id,
    m.direction,
    m.exposure_started_at_utc as submitted_or_exposure_at_utc,
    p.entry_completed_at_utc,
    null::timestamptz as closed_at_utc,
    extract(epoch from (
      clock_timestamp()-m.exposure_started_at_utc
    ))/3600.0 as hours_from_submission_or_exposure,
    case when p.entry_completed_at_utc is not null then
      extract(epoch from (
        clock_timestamp()-p.entry_completed_at_utc
      ))/3600.0
    end as hours_from_completed_entry
  from public.alpha_hunter_paper_active_exposure_members_v08 m
  left join public.alpha_hunter_paper_protection_open_v04 p
    on p.entry_order_id=m.order_id
  where m.exposure_state='FILLED_PROTECTED_POSITION'
),
completed as (
  select
    'COMPLETED'::text as row_class,
    c.entry_order_id,
    c.decision_id,
    c.symbol,
    c.strategy_id,
    c.direction,
    c.submitted_at_utc as submitted_or_exposure_at_utc,
    c.final_entry_fill_at_utc as entry_completed_at_utc,
    c.closed_at_utc,
    extract(epoch from (
      c.closed_at_utc-c.submitted_at_utc
    ))/3600.0 as hours_from_submission_or_exposure,
    case when c.final_entry_fill_at_utc is not null then
      extract(epoch from (
        c.closed_at_utc-c.final_entry_fill_at_utc
      ))/3600.0
    end as hours_from_completed_entry
  from public.alpha_hunter_paper_completed_trades_valid_v08 c
),
rows as (
  select * from active
  union all
  select * from completed
)
select
  s.spec_id,
  s.started_at_utc as r8_started_at_utc,
  s.evaluation_horizon_hours as frozen_evaluation_horizon_hours,
  r.*,
  case
    when r.row_class='ACTIVE'
      then r.submitted_or_exposure_at_utc
        +make_interval(hours=>s.evaluation_horizon_hours)
    else null
  end as active_submission_horizon_at_utc,
  case
    when r.row_class='ACTIVE' and r.entry_completed_at_utc is not null
      then r.entry_completed_at_utc
        +make_interval(hours=>s.evaluation_horizon_hours)
    else null
  end as active_completed_entry_horizon_at_utc,
  (
    r.hours_from_submission_or_exposure>s.evaluation_horizon_hours
  ) as over_horizon_from_submission_or_exposure,
  (
    r.hours_from_completed_entry is not null
    and r.hours_from_completed_entry>s.evaluation_horizon_hours
  ) as over_horizon_from_completed_entry,
  case
    when r.row_class='ACTIVE'
      and (
        r.hours_from_submission_or_exposure>s.evaluation_horizon_hours
        or coalesce(
          r.hours_from_completed_entry>s.evaluation_horizon_hours,
          false
        )
      )
      then 'ACTIVE_OVER_FROZEN_24H_HORIZON'
    when r.row_class='COMPLETED'
      and (
        r.hours_from_submission_or_exposure>s.evaluation_horizon_hours
        or coalesce(
          r.hours_from_completed_entry>s.evaluation_horizon_hours,
          false
        )
      )
      then 'COMPLETED_OVER_FROZEN_24H_HORIZON'
    else 'WITHIN_FROZEN_24H_HORIZON'
  end as horizon_observation_status,
  false as sample_mutation_permitted,
  false as exit_model_change_permitted,
  false as profitability_claim_permitted,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  'r8-horizon-integrity-observability-v0.1'::text as model_version
from rows r
cross join spec s;

revoke all on public.alpha_hunter_r8_horizon_position_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r8_horizon_position_status_v01
  to service_role;


create or replace view public.alpha_hunter_r8_horizon_integrity_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  max(frozen_evaluation_horizon_hours)::integer
    as frozen_evaluation_horizon_hours,
  count(*) filter(where row_class='ACTIVE')::bigint
    as active_filled_positions,
  count(*) filter(
    where row_class='ACTIVE'
      and horizon_observation_status='ACTIVE_OVER_FROZEN_24H_HORIZON'
  )::bigint as active_over_horizon_positions,
  count(*) filter(where row_class='COMPLETED')::bigint
    as clean_completed_r8_trades,
  count(*) filter(
    where row_class='COMPLETED'
      and horizon_observation_status='COMPLETED_OVER_FROZEN_24H_HORIZON'
  )::bigint as completed_over_horizon_trades,
  min(active_submission_horizon_at_utc) filter(
    where row_class='ACTIVE'
  ) as earliest_active_submission_horizon_at_utc,
  min(active_completed_entry_horizon_at_utc) filter(
    where row_class='ACTIVE'
  ) as earliest_active_completed_entry_horizon_at_utc,
  case
    when count(*) filter(
      where row_class='COMPLETED'
        and horizon_observation_status='COMPLETED_OVER_FROZEN_24H_HORIZON'
    )>0
      then 'COMPLETED_HORIZON_BREACH_OBSERVED_REVIEW_PROTOCOL'
    when count(*) filter(
      where row_class='ACTIVE'
        and horizon_observation_status='ACTIVE_OVER_FROZEN_24H_HORIZON'
    )>0
      then 'ACTIVE_HORIZON_BREACH_OBSERVED_REVIEW_PROTOCOL'
    else 'NO_R8_HORIZON_BREACH_OBSERVED'
  end as horizon_integrity_status,
  'OBSERVABILITY_ONLY_NO_RETROACTIVE_SAMPLE_OR_EXIT_POLICY_CHANGE'::text
    as required_action_boundary,
  false as sample_mutation_permitted,
  false as exit_model_change_permitted,
  false as profitability_claim_permitted,
  true as paper_only,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  'r8-horizon-integrity-observability-v0.1'::text as model_version
from public.alpha_hunter_r8_horizon_position_status_v01;

revoke all on public.alpha_hunter_r8_horizon_integrity_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r8_horizon_integrity_status_v01
  to service_role;
