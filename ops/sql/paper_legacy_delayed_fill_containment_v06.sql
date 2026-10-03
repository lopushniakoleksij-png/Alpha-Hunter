begin;

-- Alpha Hunter stale paper-entry runtime containment v0.6.
--
-- Production defect contained:
-- a long-lived Render cron on a pre-v0.5 runtime can continue modeling
-- delayed resting LIMIT fills at a later quote even after the database
-- geometry hardening is installed.
--
-- This migration is deliberately fail-closed:
-- 1) entry reconciliation is hidden while the canonical runtime is DRIFT;
-- 2) the commit RPC silently accepts no new reconciliation evidence while
--    deployment is not MATCHED or the source run is not the latest canonical run;
-- 3) stale delayed fills observed after v0.5 activation are quarantined
--    append-only and excluded from valid lifecycle evidence.
--
-- No exchange authority is added. No historical rows are deleted or rewritten.

create table if not exists public.alpha_hunter_paper_entry_quarantine_v06 (
  order_id text primary key
    references public.alpha_hunter_paper_orders_v02(order_id) on delete restrict,
  decision_id text not null
    references public.alpha_hunter_paper_decisions_v01(decision_id) on delete restrict,
  symbol text not null,
  quarantined_at_utc timestamptz not null default clock_timestamp(),
  reason text not null check (
    reason='LEGACY_DELAYED_LIMIT_FILL_PRE_DEPLOY'
  ),
  evidence jsonb not null default '{}'::jsonb
    check (jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check (paper_only=true),
  exchange_authority boolean not null default false check (exchange_authority=false),
  trade_permission boolean not null default false check (trade_permission=false),
  order_path text not null default 'NONE' check (order_path='NONE')
);

alter table public.alpha_hunter_paper_entry_quarantine_v06
  enable row level security;

revoke all on public.alpha_hunter_paper_entry_quarantine_v06
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_entry_quarantine_v06
  to service_role;

drop trigger if exists trg_ah_paper_entry_quarantine_append_only_v06
  on public.alpha_hunter_paper_entry_quarantine_v06;
create trigger trg_ah_paper_entry_quarantine_append_only_v06
before update or delete on public.alpha_hunter_paper_entry_quarantine_v06
for each row execute function private.alpha_hunter_block_paper_lifecycle_mutation_v01();

alter table public.alpha_hunter_paper_exit_quarantine_v04
  drop constraint if exists alpha_hunter_paper_exit_quarantine_v04_reason_check;

alter table public.alpha_hunter_paper_exit_quarantine_v04
  add constraint alpha_hunter_paper_exit_quarantine_v04_reason_check
  check (
    reason in (
      'PRE_EXIT_RECONCILIATION_GAP',
      'INVALID_ENTRY_GEOMETRY_PRE_FIX',
      'LEGACY_DELAYED_LIMIT_FILL_PRE_DEPLOY'
    )
  );

with stale_delayed as (
  select
    o.order_id,
    o.decision_id,
    o.symbol,
    o.direction,
    o.limit_price,
    min(f.filled_at_utc) as first_stale_fill_at_utc,
    max(f.filled_at_utc) as last_stale_fill_at_utc,
    min(f.source_run_id) as example_source_run_id,
    min(
      s.payload->'validation_identity'->>'git_commit'
    ) as example_git_commit,
    min(
      s.payload->'validation_identity'->>'scientific_fingerprint_sha256'
    ) as example_scientific_fingerprint,
    sum(f.quantity) as stale_fill_quantity,
    sum(f.quantity*f.fill_price)/nullif(sum(f.quantity),0)
      as stale_average_fill_price
  from public.alpha_hunter_paper_orders_v02 o
  join public.alpha_hunter_paper_fills_v02 f
    on f.order_id=o.order_id
  join public.alpha_hunter_snapshots s
    on s.run_id=f.source_run_id
  where o.order_type='LIMIT'
    and f.filled_at_utc>o.submitted_at_utc
    and f.filled_at_utc>=timestamptz '2026-10-03 00:07:44+00'
    and coalesce(
      s.payload->'validation_identity'->>'scientific_fingerprint_sha256',
      ''
    )<>'a69cfb66c070640238d2ff480988c02c7da7f6955b43d4f1a12f10c4fc6095db'
  group by
    o.order_id,o.decision_id,o.symbol,o.direction,o.limit_price
)
insert into public.alpha_hunter_paper_entry_quarantine_v06 (
  order_id,decision_id,symbol,reason,evidence,
  paper_only,exchange_authority,trade_permission,order_path
)
select
  x.order_id,
  x.decision_id,
  x.symbol,
  'LEGACY_DELAYED_LIMIT_FILL_PRE_DEPLOY',
  pg_catalog.jsonb_build_object(
    'containment_version','paper-entry-runtime-containment-v0.6',
    'direction',x.direction,
    'limit_price',x.limit_price,
    'first_stale_fill_at_utc',x.first_stale_fill_at_utc,
    'last_stale_fill_at_utc',x.last_stale_fill_at_utc,
    'example_source_run_id',x.example_source_run_id,
    'example_git_commit',x.example_git_commit,
    'example_scientific_fingerprint',x.example_scientific_fingerprint,
    'stale_fill_quantity',x.stale_fill_quantity,
    'stale_average_fill_price',x.stale_average_fill_price,
    'historical_rows_deleted',false,
    'historical_rows_rewritten',false
  ),
  true,false,false,'NONE'
from stale_delayed x
on conflict(order_id) do nothing;

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
  q.order_id,
  q.decision_id,
  q.symbol,
  min(p.created_at_utc),
  'LEGACY_DELAYED_LIMIT_FILL_PRE_DEPLOY',
  q.evidence || pg_catalog.jsonb_build_object(
    'protective_exit_excluded',true
  ),
  true,false,false,'NONE'
from public.alpha_hunter_paper_entry_quarantine_v06 q
join public.alpha_hunter_paper_protective_orders_v03 p
  on p.entry_order_id=q.order_id
group by q.order_id,q.decision_id,q.symbol,q.evidence
on conflict(entry_order_id) do nothing;

create or replace view public.alpha_hunter_paper_reconciliation_gate_v06
with (security_invoker=true,security_barrier=true)
as
select
  d.checked_at_utc,
  d.latest_canonical_run_id,
  d.latest_canonical_scan_at_utc,
  d.target_git_commit,
  d.live_runtime_git_commit,
  d.target_runtime_fingerprint_sha256,
  d.live_runtime_fingerprint_sha256,
  d.deployment_status,
  (d.deployment_status='MATCHED') as entry_reconciliation_permitted,
  true as paper_only,
  false as exchange_authority,
  false as trade_permission,
  'NONE'::text as order_path
from public.alpha_hunter_production_deployment_runtime_status_v03 d;

revoke all on public.alpha_hunter_paper_reconciliation_gate_v06
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_reconciliation_gate_v06
  to service_role;

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
left join public.alpha_hunter_paper_entry_quarantine_v06 q
  on q.order_id=o.order_id
cross join public.alpha_hunter_paper_reconciliation_gate_v06 g
where coalesce(x.filled_quantity,0) < o.quantity
  and o.submitted_at_utc >= timestamptz '2026-10-01 15:00:00+00'
  and q.order_id is null
  and g.entry_reconciliation_permitted=true;

revoke all on public.alpha_hunter_paper_reconciliation_open_v03
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_reconciliation_open_v03
  to service_role;

create or replace function public.alpha_hunter_commit_paper_reconciliation_v03(
  attempt_rows jsonb,
  fill_rows jsonb,
  event_rows jsonb,
  protective_rows jsonb
)
returns void
language plpgsql
security invoker
set search_path=''
as $$
declare
  v_deployment_status text;
  v_latest_canonical_run_id text;
begin
  if jsonb_typeof(attempt_rows)<>'array'
     or jsonb_typeof(fill_rows)<>'array'
     or jsonb_typeof(event_rows)<>'array'
     or jsonb_typeof(protective_rows)<>'array' then
    raise exception 'paper reconciliation payloads must be JSON arrays';
  end if;

  select g.deployment_status,g.latest_canonical_run_id
    into v_deployment_status,v_latest_canonical_run_id
  from public.alpha_hunter_paper_reconciliation_gate_v06 g
  limit 1;

  if v_deployment_status is distinct from 'MATCHED'
     or v_latest_canonical_run_id is null then
    return;
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_array_elements(attempt_rows) j
    where j->>'source_run_id' is distinct from v_latest_canonical_run_id
  ) then
    return;
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('alpha-hunter-paper-reconciliation-v03',0)
  );

  select coalesce(pg_catalog.jsonb_agg(j),'[]'::jsonb)
    into attempt_rows
  from pg_catalog.jsonb_array_elements(attempt_rows) j
  where not exists (
    select 1
    from public.alpha_hunter_paper_reconciliation_attempts_v03 a
    where a.attempt_id=j->>'attempt_id'
  )
  and not exists (
    select 1
    from public.alpha_hunter_paper_entry_quarantine_v06 q
    where q.order_id=j->>'order_id'
  );

  if pg_catalog.jsonb_array_length(attempt_rows)=0 then
    return;
  end if;

  insert into public.alpha_hunter_paper_reconciliation_attempts_v03 (
    attempt_id,order_id,decision_id,source_run_id,observed_at_utc,symbol,
    prior_state,prior_filled_quantity,prior_remaining_quantity,best_bid,best_ask,
    best_bid_size,best_ask_size,outcome,blockers,evidence,paper_only,
    exchange_authority,trade_permission,order_path
  )
  select
    j->>'attempt_id',j->>'order_id',j->>'decision_id',j->>'source_run_id',
    (j->>'observed_at_utc')::timestamptz,j->>'symbol',j->>'prior_state',
    (j->>'prior_filled_quantity')::numeric,(j->>'prior_remaining_quantity')::numeric,
    (j->>'best_bid')::numeric,(j->>'best_ask')::numeric,
    (j->>'best_bid_size')::numeric,(j->>'best_ask_size')::numeric,
    j->>'outcome',j->'blockers',j->'evidence',(j->>'paper_only')::boolean,
    (j->>'exchange_authority')::boolean,(j->>'trade_permission')::boolean,
    j->>'order_path'
  from pg_catalog.jsonb_array_elements(attempt_rows) j;

  insert into public.alpha_hunter_paper_fills_v02 (
    fill_id,order_id,decision_id,source_run_id,fill_sequence,filled_at_utc,
    quantity,fill_price,notional_usdt,midpoint_reference,cross_price_reference,
    spread_cost_usdt,slippage_bps,slippage_cost_usdt,fee_bps,fee_usdt,
    funding_rate_snapshot,projected_next_funding_usdt,accrued_funding_usdt,
    funding_status,liquidity_source,model_quality,paper_only,exchange_authority,
    trade_permission,order_path
  )
  select
    j->>'fill_id',j->>'order_id',j->>'decision_id',j->>'source_run_id',
    (j->>'fill_sequence')::integer,(j->>'filled_at_utc')::timestamptz,
    (j->>'quantity')::numeric,(j->>'fill_price')::numeric,
    (j->>'notional_usdt')::numeric,(j->>'midpoint_reference')::numeric,
    (j->>'cross_price_reference')::numeric,(j->>'spread_cost_usdt')::numeric,
    (j->>'slippage_bps')::numeric,(j->>'slippage_cost_usdt')::numeric,
    (j->>'fee_bps')::numeric,(j->>'fee_usdt')::numeric,
    (j->>'funding_rate_snapshot')::numeric,
    (j->>'projected_next_funding_usdt')::numeric,
    (j->>'accrued_funding_usdt')::numeric,j->>'funding_status',
    j->>'liquidity_source',j->>'model_quality',(j->>'paper_only')::boolean,
    (j->>'exchange_authority')::boolean,(j->>'trade_permission')::boolean,
    j->>'order_path'
  from pg_catalog.jsonb_array_elements(fill_rows) j
  where exists (
    select 1 from pg_catalog.jsonb_array_elements(attempt_rows) a
    where a->>'order_id'=j->>'order_id'
      and a->>'source_run_id'=j->>'source_run_id'
  );

  insert into public.alpha_hunter_paper_events_v01 (
    event_id,decision_id,sequence,occurred_at_utc,event_type,state,payload,
    paper_only,exchange_authority,trade_permission,order_path
  )
  select
    j->>'event_id',j->>'decision_id',(j->>'sequence')::integer,
    (j->>'occurred_at_utc')::timestamptz,j->>'event_type',j->>'state',j->'payload',
    (j->>'paper_only')::boolean,(j->>'exchange_authority')::boolean,
    (j->>'trade_permission')::boolean,j->>'order_path'
  from pg_catalog.jsonb_array_elements(event_rows) j
  where exists (
    select 1 from pg_catalog.jsonb_array_elements(attempt_rows) a
    where a->>'decision_id'=j->>'decision_id'
      and a->>'source_run_id'=j->'payload'->>'source_run_id'
  );

  insert into public.alpha_hunter_paper_protective_orders_v03 (
    protective_order_id,entry_order_id,decision_id,activated_by_fill_id,
    created_at_utc,symbol,direction,protection_type,side,trigger_price,quantity,
    reduce_only,status,evidence,paper_only,exchange_authority,trade_permission,order_path
  )
  select
    j->>'protective_order_id',j->>'entry_order_id',j->>'decision_id',
    j->>'activated_by_fill_id',(j->>'created_at_utc')::timestamptz,j->>'symbol',
    j->>'direction',j->>'protection_type',j->>'side',(j->>'trigger_price')::numeric,
    (j->>'quantity')::numeric,(j->>'reduce_only')::boolean,j->>'status',j->'evidence',
    (j->>'paper_only')::boolean,(j->>'exchange_authority')::boolean,
    (j->>'trade_permission')::boolean,j->>'order_path'
  from pg_catalog.jsonb_array_elements(protective_rows) j
  where exists (
    select 1 from pg_catalog.jsonb_array_elements(attempt_rows) a
    where a->>'order_id'=j->>'entry_order_id'
      and a->>'source_run_id'=j->'evidence'->>'source_run_id'
  );
end;
$$;

revoke all on function public.alpha_hunter_commit_paper_reconciliation_v03(
  jsonb,jsonb,jsonb,jsonb
) from public,anon,authenticated,service_role;
grant execute on function public.alpha_hunter_commit_paper_reconciliation_v03(
  jsonb,jsonb,jsonb,jsonb
) to service_role;

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
left join public.alpha_hunter_paper_entry_quarantine_v06 eq
  on eq.order_id=c.entry_order_id
where q.entry_order_id is null
  and eq.order_id is null
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
