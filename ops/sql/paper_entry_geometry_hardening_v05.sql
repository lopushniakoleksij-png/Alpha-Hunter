begin;

-- Paper entry-geometry hardening v0.5.
-- Purpose:
-- 1) prevent delayed limit reconciliation from contaminating the paper sample;
-- 2) enforce stop/entry/target geometry against the cumulative modeled entry;
-- 3) quarantine pre-fix invalid geometry append-only;
-- 4) expose a valid completed-trade view for economic/scientific counting.
--
-- No exchange authority, trade permission, or live order path is added.

alter table public.alpha_hunter_paper_exit_quarantine_v04
  drop constraint if exists alpha_hunter_paper_exit_quarantine_v04_reason_check;

alter table public.alpha_hunter_paper_exit_quarantine_v04
  add constraint alpha_hunter_paper_exit_quarantine_v04_reason_check
  check (
    reason in (
      'PRE_EXIT_RECONCILIATION_GAP',
      'INVALID_ENTRY_GEOMETRY_PRE_FIX'
    )
  );

create or replace function private.alpha_hunter_validate_protective_after_full_fill_v03()
returns trigger
language plpgsql
security invoker
set search_path=''
as $$
declare
  ordered numeric;
  filled numeric;
  expected_decision text;
  expected_direction text;
  expected_stop numeric;
  expected_target numeric;
  average_fill_price numeric;
  fill_matches boolean;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'alpha-hunter-paper-order:' || new.entry_order_id,
      0
    )
  );

  select o.quantity,o.decision_id,o.direction,d.stop_price,d.target_price
    into ordered,expected_decision,expected_direction,expected_stop,expected_target
  from public.alpha_hunter_paper_orders_v02 o
  join public.alpha_hunter_paper_decisions_v01 d
    on d.decision_id=o.decision_id
  where o.order_id=new.entry_order_id;

  select
    coalesce(sum(f.quantity),0),
    sum(f.quantity*f.fill_price)/nullif(sum(f.quantity),0),
    bool_or(f.fill_id=new.activated_by_fill_id)
    into filled,average_fill_price,fill_matches
  from public.alpha_hunter_paper_fills_v02 f
  where f.order_id=new.entry_order_id;

  if ordered is null or expected_decision<>new.decision_id then
    raise exception 'protective order does not match an existing entry order';
  end if;
  if not coalesce(fill_matches,false) then
    raise exception 'protective activation fill does not belong to entry order';
  end if;
  if filled < ordered-0.000000000001 then
    raise exception 'protective order forbidden before complete entry fill';
  end if;
  if new.quantity > filled+0.000000000001 then
    raise exception 'protective quantity exceeds cumulative entry fill';
  end if;
  if average_fill_price is null then
    raise exception 'protective order missing cumulative entry average';
  end if;
  if (
    expected_direction='LONG'
    and not (
      expected_stop < average_fill_price
      and average_fill_price < expected_target
    )
  ) or (
    expected_direction='SHORT'
    and not (
      expected_target < average_fill_price
      and average_fill_price < expected_stop
    )
  ) then
    raise exception
      'protective order geometry invalid relative to cumulative entry fill';
  end if;

  return new;
end;
$$;

revoke all on function private.alpha_hunter_validate_protective_after_full_fill_v03()
  from public,anon,authenticated;

create or replace view public.alpha_hunter_paper_reconciliation_open_v03
with (security_invoker=true,security_barrier=true)
as
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
    when coalesce(x.filled_quantity,0)>0 then 'PARTIALLY_FILLED'
    else 'SUBMITTED'
  end as execution_state,
  coalesce(x.fill_count,0)::integer as fill_count,
  coalesce(e.event_sequence,3)::integer as event_sequence,
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
from public.alpha_hunter_paper_orders_v02 o
join public.alpha_hunter_paper_decisions_v01 d using (decision_id)
left join lateral (
  select
    sum(f.quantity) as filled_quantity,
    sum(f.quantity*f.fill_price)/nullif(sum(f.quantity),0)
      as average_fill_price,
    count(*) as fill_count
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

revoke all on public.alpha_hunter_paper_reconciliation_open_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_reconciliation_open_v03 to service_role;

with entry_fill as (
  select
    f.order_id,
    sum(f.quantity*f.fill_price)/nullif(sum(f.quantity),0) as average_fill_price
  from public.alpha_hunter_paper_fills_v02 f
  group by f.order_id
),
protection as (
  select
    p.entry_order_id,
    p.decision_id,
    p.symbol,
    min(p.created_at_utc) as protection_created_at_utc,
    max(p.trigger_price) filter(where p.protection_type='STOP_LOSS')
      as stop_price,
    max(p.trigger_price) filter(where p.protection_type='TAKE_PROFIT')
      as target_price,
    max(p.direction) as direction
  from public.alpha_hunter_paper_protective_orders_v03 p
  group by p.entry_order_id,p.decision_id,p.symbol
)
insert into public.alpha_hunter_paper_exit_quarantine_v04 (
  entry_order_id,
  decision_id,
  symbol,
  protection_created_at_utc,
  reason,
  evidence,
  paper_only,
  exchange_authority,
  trade_permission,
  order_path
)
select
  p.entry_order_id,
  p.decision_id,
  p.symbol,
  p.protection_created_at_utc,
  'INVALID_ENTRY_GEOMETRY_PRE_FIX',
  pg_catalog.jsonb_build_object(
    'quarantine_version','paper-entry-geometry-v0.5',
    'average_entry_fill_price',ef.average_fill_price,
    'stop_price',p.stop_price,
    'target_price',p.target_price,
    'direction',p.direction,
    'historical_rows_deleted',false
  ),
  true,false,false,'NONE'
from protection p
join entry_fill ef on ef.order_id=p.entry_order_id
where
  (
    p.direction='LONG'
    and not (
      p.stop_price < ef.average_fill_price
      and ef.average_fill_price < p.target_price
    )
  )
  or
  (
    p.direction='SHORT'
    and not (
      p.target_price < ef.average_fill_price
      and ef.average_fill_price < p.stop_price
    )
  )
on conflict(entry_order_id) do nothing;

create or replace view public.alpha_hunter_paper_completed_trades_valid_v05
with (security_invoker=true,security_barrier=true)
as
with protection as (
  select
    p.entry_order_id,
    max(p.trigger_price) filter(where p.protection_type='STOP_LOSS')
      as stop_price,
    max(p.trigger_price) filter(where p.protection_type='TAKE_PROFIT')
      as target_price
  from public.alpha_hunter_paper_protective_orders_v03 p
  group by p.entry_order_id
)
select c.*
from public.alpha_hunter_paper_completed_trades_v04 c
join protection p using(entry_order_id)
left join public.alpha_hunter_paper_exit_quarantine_v04 q
  on q.entry_order_id=c.entry_order_id
where q.entry_order_id is null
  and (
    (
      c.direction='LONG'
      and p.stop_price < c.entry_average_fill_price
      and c.entry_average_fill_price < p.target_price
    )
    or
    (
      c.direction='SHORT'
      and p.target_price < c.entry_average_fill_price
      and c.entry_average_fill_price < p.stop_price
    )
  );

revoke all on public.alpha_hunter_paper_completed_trades_valid_v05
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trades_valid_v05
  to service_role;

commit;
