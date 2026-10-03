-- Alpha Hunter R8 reconciliation-required containment v0.1
--
-- Issue #320.
--
-- Defect:
--   Initial all-or-none paper execution can append RECONCILIATION_REQUIRED when
--   fill evidence is incomplete (for example insufficient top-of-book capacity).
--   The R8 reconciliation view previously admitted only SUBMITTED and
--   PARTIALLY_FILLED, which stranded zero-fill entries outside both the frozen
--   35-minute expiry path and the active-exposure key guard.
--
-- Repair contract:
--   - expose ONLY zero-fill, initial PAPER_FILL_EVIDENCE_INCOMPLETE
--     RECONCILIATION_REQUIRED rows;
--   - preserve their true lifecycle state;
--   - allow reconciliation evidence to record that prior state;
--   - Python runtime permits only RECONCILIATION_REQUIRED -> EXPIRED;
--   - never create a delayed fill from this recovery path.
--
-- Safety:
--   paper-only containment; no threshold, sizing, RR, strategy, scientific
--   fingerprint, live permission, production promotion, or exchange-order path.

alter table public.alpha_hunter_paper_reconciliation_attempts_v03
  drop constraint if exists
    alpha_hunter_paper_reconciliation_attempts_v0_prior_state_check;

alter table public.alpha_hunter_paper_reconciliation_attempts_v03
  add constraint alpha_hunter_paper_reconciliation_attempts_v0_prior_state_check
  check (
    prior_state in (
      'SUBMITTED',
      'PARTIALLY_FILLED',
      'RECONCILIATION_REQUIRED'
    )
  );


create or replace view public.alpha_hunter_paper_reconciliation_open_v08
with (security_invoker=true,security_barrier=true)
as
with activation as (
  select a.*
  from public.alpha_hunter_paper_execution_integrity_activation_v08 a
  where a.activation_id='PAPER_EXECUTION_R8'
  order by a.activated_at_utc desc
  limit 1
),
latest_event as (
  select distinct on (e.decision_id)
    e.decision_id,
    e.sequence,
    e.state,
    e.event_type,
    e.occurred_at_utc
  from public.alpha_hunter_paper_events_v01 e
  order by e.decision_id,e.sequence desc,e.created_at desc
),
fill_state as (
  select
    f.order_id,
    sum(f.quantity) as filled_quantity,
    sum(f.quantity*f.fill_price)/nullif(sum(f.quantity),0)
      as average_fill_price,
    count(*)::integer as fill_count
  from public.alpha_hunter_paper_fills_v02 f
  group by f.order_id
)
select
  o.order_id,
  o.decision_id,
  o.symbol,
  o.direction,
  o.order_type,
  o.limit_price,
  o.quantity as ordered_quantity,
  coalesce(x.filled_quantity,0) as filled_quantity,
  o.quantity-coalesce(x.filled_quantity,0) as remaining_quantity,
  case
    when le.state='RECONCILIATION_REQUIRED'
      then 'RECONCILIATION_REQUIRED'
    when coalesce(x.filled_quantity,0)>0
      then 'PARTIALLY_FILLED'
    else 'SUBMITTED'
  end as execution_state,
  coalesce(x.fill_count,0) as fill_count,
  le.sequence as event_sequence,
  d.stop_price,
  d.target_price,
  o.public_maker_fee_bps,
  o.public_taker_fee_bps,
  o.paper_only,
  o.exchange_authority,
  o.trade_permission,
  o.order_path,
  o.submitted_at_utc,
  x.average_fill_price
from activation a
join public.alpha_hunter_paper_orders_v02 o
  on o.submitted_at_utc>=a.activated_at_utc
join public.alpha_hunter_paper_decisions_v01 d using(decision_id)
join latest_event le using(decision_id)
left join fill_state x on x.order_id=o.order_id
left join public.alpha_hunter_paper_entry_quarantine_v06 q
  on q.order_id=o.order_id
cross join public.alpha_hunter_paper_reconciliation_gate_v06 g
where coalesce(x.filled_quantity,0)<o.quantity
  and (
    le.state in ('SUBMITTED','PARTIALLY_FILLED')
    or (
      le.state='RECONCILIATION_REQUIRED'
      and le.event_type='PAPER_FILL_EVIDENCE_INCOMPLETE'
      and coalesce(x.filled_quantity,0)=0
    )
  )
  and q.order_id is null
  and g.entry_reconciliation_permitted=true;

revoke all on public.alpha_hunter_paper_reconciliation_open_v08
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_reconciliation_open_v08
  to service_role;


create or replace view public.alpha_hunter_paper_active_exposure_members_v08
with (security_invoker=true,security_barrier=true)
as
with activation as (
  select a.*
  from public.alpha_hunter_paper_execution_integrity_activation_v08 a
  where a.activation_id='PAPER_EXECUTION_R8'
  order by a.activated_at_utc desc
  limit 1
),
resting as (
  select
    r.order_id,
    r.decision_id,
    r.symbol,
    d.strategy_id,
    r.direction,
    r.submitted_at_utc as exposure_started_at_utc,
    'RESTING_ENTRY'::text as exposure_state
  from public.alpha_hunter_paper_reconciliation_open_v08 r
  join public.alpha_hunter_paper_decisions_v01 d using(decision_id)
  cross join activation a
  where r.filled_quantity=0
    and (
      r.execution_state='RECONCILIATION_REQUIRED'
      or r.submitted_at_utc
          >=clock_timestamp()-make_interval(
            mins=>a.maximum_entry_age_minutes
          )
    )
),
filled as (
  select
    p.entry_order_id as order_id,
    p.decision_id,
    p.symbol,
    d.strategy_id,
    p.direction,
    o.submitted_at_utc as exposure_started_at_utc,
    'FILLED_PROTECTED_POSITION'::text as exposure_state
  from public.alpha_hunter_paper_protection_open_v04 p
  join public.alpha_hunter_paper_orders_v02 o
    on o.order_id=p.entry_order_id
  join public.alpha_hunter_paper_decisions_v01 d
    on d.decision_id=p.decision_id
  cross join activation a
  where o.submitted_at_utc>=a.activated_at_utc
)
select * from resting
union all
select * from filled;

revoke all on public.alpha_hunter_paper_active_exposure_members_v08
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_active_exposure_members_v08
  to service_role;



create or replace view public.alpha_hunter_r8_reconciliation_required_status_v01
with (security_invoker=true,security_barrier=true)
as
select
  count(*) filter(
    where r.execution_state='RECONCILIATION_REQUIRED'
  )::bigint as reconciliation_required_zero_fill_orders,
  count(*) filter(
    where r.execution_state='RECONCILIATION_REQUIRED'
      and clock_timestamp()-r.submitted_at_utc>interval '35 minutes'
  )::bigint as reconciliation_required_over_frozen_entry_age,
  min(r.submitted_at_utc) filter(
    where r.execution_state='RECONCILIATION_REQUIRED'
  ) as oldest_reconciliation_required_submitted_at_utc,
  case
    when count(*) filter(
      where r.execution_state='RECONCILIATION_REQUIRED'
        and clock_timestamp()-r.submitted_at_utc>interval '35 minutes'
    )>0
      then 'EXPIRE_ON_NEXT_CANONICAL_RECONCILIATION'
    when count(*) filter(
      where r.execution_state='RECONCILIATION_REQUIRED'
    )>0
      then 'FAIL_CLOSED_UNTIL_FROZEN_35M_EXPIRY'
    else 'NO_RECONCILIATION_REQUIRED_ENTRY_DEFECT'
  end as containment_status,
  true as all_or_none_preserved,
  true as delayed_fill_forbidden,
  false as live_money_claim_permitted,
  true as paper_only,
  false as exchange_authority,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  'r8-reconciliation-required-containment-v0.1'::text as model_version
from public.alpha_hunter_paper_reconciliation_open_v08 r;

revoke all on public.alpha_hunter_r8_reconciliation_required_status_v01
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_r8_reconciliation_required_status_v01
  to service_role;
