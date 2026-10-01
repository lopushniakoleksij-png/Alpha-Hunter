-- Alpha Hunter paper reconciliation gap cutoff v0.4
-- Prospective evidence only: orders created before the repair boundary are
-- preserved for audit but excluded from later quote-based fill modeling.

create or replace view public.alpha_hunter_paper_reconciliation_open_v03
with (security_invoker=true,security_barrier=true)
as
select
  o.order_id,o.decision_id,o.symbol,o.direction,o.order_type,o.limit_price,
  o.quantity as ordered_quantity,
  coalesce(x.filled_quantity,0) as filled_quantity,
  o.quantity-coalesce(x.filled_quantity,0) as remaining_quantity,
  case when coalesce(x.filled_quantity,0)>0 then 'PARTIALLY_FILLED' else 'SUBMITTED' end as execution_state,
  coalesce(x.fill_count,0)::integer as fill_count,
  coalesce(e.event_sequence,3)::integer as event_sequence,
  d.stop_price,d.target_price,o.public_maker_fee_bps,o.public_taker_fee_bps,
  o.paper_only,o.exchange_authority,o.trade_permission,o.order_path,
  o.submitted_at_utc
from public.alpha_hunter_paper_orders_v02 o
join public.alpha_hunter_paper_decisions_v01 d using (decision_id)
left join lateral (
  select sum(f.quantity) as filled_quantity,count(*) as fill_count
  from public.alpha_hunter_paper_fills_v02 f
  where f.order_id=o.order_id
) x on true
left join lateral (
  select max(pe.sequence) as event_sequence
  from public.alpha_hunter_paper_events_v01 pe
  where pe.decision_id=o.decision_id
) e on true
where coalesce(x.filled_quantity,0) < o.quantity
  and o.submitted_at_utc >= timestamptz '2026-10-01 15:00:00+00';

create or replace view public.alpha_hunter_paper_reconciliation_quarantine_current_v04
with (security_invoker=true,security_barrier=true)
as
select
  o.order_id,o.decision_id,o.symbol,o.direction,o.order_type,o.limit_price,
  o.quantity as ordered_quantity,
  coalesce(x.filled_quantity,0) as filled_quantity,
  o.quantity-coalesce(x.filled_quantity,0) as remaining_quantity,
  o.submitted_at_utc,
  'PRE_REPAIR_RECONCILIATION_GAP'::text as reason,
  true as retroactive_fill_forbidden
from public.alpha_hunter_paper_orders_v02 o
left join lateral (
  select coalesce(sum(f.quantity),0) as filled_quantity
  from public.alpha_hunter_paper_fills_v02 f
  where f.order_id=o.order_id
) x on true
where x.filled_quantity < o.quantity
  and o.submitted_at_utc < timestamptz '2026-10-01 15:00:00+00';

revoke all on public.alpha_hunter_paper_reconciliation_quarantine_current_v04
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_reconciliation_quarantine_current_v04
  to service_role;
