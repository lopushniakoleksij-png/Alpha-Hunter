begin;

-- R8 active-position integrity observability v0.1.
-- Read-only status view for filled/protected R8 paper positions.
-- This does not change paper execution, thresholds, cadence, strategy logic,
-- scientific identity, trade permission, promotion, or any exchange path.

create or replace view public.alpha_hunter_r8_active_position_integrity_v01
with (security_invoker=true,security_barrier=true)
as
with activation as (
  select maximum_monitoring_gap_minutes
  from public.alpha_hunter_paper_execution_integrity_activation_v08
  where activation_id='PAPER_EXECUTION_R8'
  order by activated_at_utc desc
  limit 1
),
active as (
  select *
  from public.alpha_hunter_paper_active_exposure_members_v08
  where exposure_state='FILLED_PROTECTED_POSITION'
),
protection as (
  select
    decision_id,
    count(*) filter(
      where protection_type='STOP_LOSS' and status='ACTIVE_PAPER'
    )::integer as active_stop_count,
    count(*) filter(
      where protection_type='TAKE_PROFIT' and status='ACTIVE_PAPER'
    )::integer as active_target_count,
    sum(quantity) filter(
      where protection_type='STOP_LOSS' and status='ACTIVE_PAPER'
    ) as active_stop_quantity,
    sum(quantity) filter(
      where protection_type='TAKE_PROFIT' and status='ACTIVE_PAPER'
    ) as active_target_quantity
  from public.alpha_hunter_paper_protective_orders_v03
  group by decision_id
),
latest_exit_observation as (
  select distinct on (decision_id)
    decision_id,
    observed_at_utc,
    outcome,
    triggered_protection_type,
    blockers
  from public.alpha_hunter_paper_exit_attempts_v04
  order by decision_id,observed_at_utc desc,created_at desc
)
select
  clock_timestamp() as checked_at_utc,
  a.order_id,
  a.decision_id,
  a.symbol,
  a.strategy_id,
  a.direction,
  a.exposure_started_at_utc,
  round(
    (
      extract(epoch from (clock_timestamp()-a.exposure_started_at_utc))
      /60.0
    )::numeric,
    3
  ) as exposure_age_minutes,
  coalesce(p.active_stop_count,0) as active_stop_count,
  coalesce(p.active_target_count,0) as active_target_count,
  p.active_stop_quantity,
  p.active_target_quantity,
  x.observed_at_utc as latest_exit_observed_at_utc,
  x.outcome as latest_exit_outcome,
  x.triggered_protection_type,
  x.blockers as latest_exit_blockers,
  round(
    (
      extract(
        epoch from (
          clock_timestamp()
          - coalesce(x.observed_at_utc,a.exposure_started_at_utc)
        )
      )/60.0
    )::numeric,
    3
  ) as monitoring_gap_minutes,
  act.maximum_monitoring_gap_minutes,
  (
    coalesce(p.active_stop_count,0)=1
    and coalesce(p.active_target_count,0)=1
  ) as protection_complete,
  (
    extract(
      epoch from (
        clock_timestamp()
        - coalesce(x.observed_at_utc,a.exposure_started_at_utc)
      )
    )/60.0
    <= act.maximum_monitoring_gap_minutes
  ) as monitoring_within_contract,
  case
    when coalesce(p.active_stop_count,0)<>1
      or coalesce(p.active_target_count,0)<>1
      then 'PROTECTION_DEFECT'
    when (
      extract(
        epoch from (
          clock_timestamp()
          - coalesce(x.observed_at_utc,a.exposure_started_at_utc)
        )
      )/60.0
    ) > act.maximum_monitoring_gap_minutes
      then 'MONITORING_GAP_DEFECT'
    when x.outcome='AMBIGUOUS'
      then 'AWAITING_NEXT_CANONICAL_OBSERVATION'
    else 'PASS'
  end as integrity_status,
  true as paper_only,
  false as exchange_authority,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from active a
cross join activation act
left join protection p using(decision_id)
left join latest_exit_observation x using(decision_id);

revoke all on public.alpha_hunter_r8_active_position_integrity_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r8_active_position_integrity_v01
  to service_role;

commit;
