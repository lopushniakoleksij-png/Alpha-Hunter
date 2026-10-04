begin;
-- Successor to R8; Issue #323. Install without activation before runtime deploy.
-- No existing activation, order, fill, event or outcome is rewritten.
create table public.alpha_hunter_paper_execution_activation_v09 (
 activation_id text primary key check(activation_id='PAPER_EXECUTION_R9'),
 spec_id text not null unique references public.alpha_hunter_profitability_test_specs_v01(spec_id),
 protocol_version text not null check(protocol_version='paper-horizon-24h-v0.1'),
 activated_at_utc timestamptz not null,
 runtime_verified_at_utc timestamptz not null,
 admission_cutoff_at_utc timestamptz not null,
 release_git_commit text not null check(release_git_commit ~ '^[a-f0-9]{40}$'),
 scientific_fingerprint_sha256 text not null check(scientific_fingerprint_sha256 ~ '^[a-f0-9]{64}$'),
 maximum_entry_age_minutes integer not null default 35 check(maximum_entry_age_minutes=35),
 maximum_monitoring_gap_minutes integer not null default 35 check(maximum_monitoring_gap_minutes=35),
 horizon_hours integer not null default 24 check(horizon_hours=24),
 maximum_horizon_lag_minutes integer not null default 35 check(maximum_horizon_lag_minutes=35),
 required_run_source text not null default 'RENDER_CRON' check(required_run_source='RENDER_CRON'),
 required_runtime_role text not null default 'RENDER_CRON' check(required_runtime_role='RENDER_CRON'),
 evidence jsonb not null,
 paper_only boolean not null default true check(paper_only),
 exchange_authority boolean not null default false check(not exchange_authority),
 trade_permission boolean not null default false check(not trade_permission),
 production_promotion_permitted boolean not null default false check(not production_promotion_permitted),
 order_path text not null default 'NONE' check(order_path='NONE'),
 check(activated_at_utc>runtime_verified_at_utc),
 check(admission_cutoff_at_utc=activated_at_utc+interval '30 days')
);
alter table public.alpha_hunter_paper_execution_activation_v09 enable row level security;
revoke all on public.alpha_hunter_paper_execution_activation_v09 from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_execution_activation_v09 to service_role;
create trigger trg_ah_r9_activation_append_only before update or delete
 on public.alpha_hunter_paper_execution_activation_v09
 for each row execute function private.alpha_hunter_block_append_only_mutation();

-- Append-only emergency admission halt: monitoring and protection stay active.
create table public.alpha_hunter_paper_admission_halts_v09 (
 activation_id text primary key references public.alpha_hunter_paper_execution_activation_v09(activation_id),
 halted_at_utc timestamptz not null default clock_timestamp(),
 reason text not null check(length(reason)>0)
);
alter table public.alpha_hunter_paper_admission_halts_v09 enable row level security;
revoke all on public.alpha_hunter_paper_admission_halts_v09 from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_admission_halts_v09 to service_role;
create trigger trg_ah_r9_halts_append_only before update or delete on public.alpha_hunter_paper_admission_halts_v09
 for each row execute function private.alpha_hunter_block_append_only_mutation();
create view public.alpha_hunter_paper_admission_open_v09
with(security_invoker=true,security_barrier=true) as
select a.* from public.alpha_hunter_paper_execution_activation_v09 a
where not exists(select 1 from public.alpha_hunter_paper_admission_halts_v09 h
 where h.activation_id=a.activation_id);
revoke all on public.alpha_hunter_paper_admission_open_v09 from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_admission_open_v09 to service_role;

alter table public.alpha_hunter_paper_events_v01
 drop constraint alpha_hunter_paper_events_v01_state_check;
alter table public.alpha_hunter_paper_events_v01
 add constraint alpha_hunter_paper_events_v01_state_check check(state in
 ('CREATED','AUTHORIZED','WATCHING','BLOCKED','SUBMITTED','PARTIALLY_FILLED',
  'FILLED','CANCELLED','EXPIRED','STOPPED','TARGETED','RECONCILIATION_REQUIRED','HORIZON_CLOSED'));
alter table public.alpha_hunter_paper_exit_attempts_v04
 drop constraint alpha_hunter_paper_exit_attempts_v04_outcome_check;
alter table public.alpha_hunter_paper_exit_attempts_v04
 add constraint alpha_hunter_paper_exit_attempts_v04_outcome_check check(outcome in
 ('INPUT_MISSING','NO_TRIGGER','STOP_TRIGGERED','TARGET_TRIGGERED','AMBIGUOUS',
  'HORIZON_CLOSED','HORIZON_FAILED'));
alter table public.alpha_hunter_paper_exit_fills_v04
 alter column triggered_protective_order_id drop not null;
alter table public.alpha_hunter_paper_exit_fills_v04
 drop constraint alpha_hunter_paper_exit_fills_v04_protection_type_check;
alter table public.alpha_hunter_paper_exit_fills_v04
 add constraint alpha_hunter_paper_exit_fills_v04_protection_type_check check(
   (protection_type in ('STOP_LOSS','TAKE_PROFIT') and triggered_protective_order_id is not null)
   or (protection_type='HORIZON_24H' and triggered_protective_order_id is null));

-- Prior failure evidence survives restart; a later profitable observation cannot erase it.
create view public.alpha_hunter_paper_horizon_history_v09
with(security_invoker=true,security_barrier=true) as
select a.entry_order_id,max(a.observed_at_utc) as previous_exit_observed_at_utc,
 bool_or(coalesce((a.evidence->>'horizon_integrity_failed')::boolean,false)) as horizon_integrity_failed,
 bool_or(a.outcome='AMBIGUOUS' or
   (a.triggered_protection_type is not null and a.outcome='INPUT_MISSING')) as unresolved_protective_evidence
from public.alpha_hunter_paper_exit_attempts_v04 a group by a.entry_order_id;

-- Preserve ALL legacy protected positions. Only successor orders gain timeout policy.
create view public.alpha_hunter_paper_protection_horizon_open_v09
with(security_invoker=true,security_barrier=true) as
select p.*,a.protocol_version as horizon_protocol,
 a.scientific_fingerprint_sha256 as horizon_scientific_fingerprint_sha256,
 h.previous_exit_observed_at_utc,coalesce(h.horizon_integrity_failed,false) as horizon_integrity_failed,
 coalesce(h.unresolved_protective_evidence,false) as unresolved_protective_evidence
from public.alpha_hunter_paper_protection_open_v04 p
join public.alpha_hunter_paper_orders_v02 o on o.order_id=p.entry_order_id
left join public.alpha_hunter_paper_execution_activation_v09 a
 on o.submitted_at_utc>a.activated_at_utc
left join public.alpha_hunter_paper_horizon_history_v09 h using(entry_order_id);

revoke all on public.alpha_hunter_paper_horizon_history_v09,
 public.alpha_hunter_paper_protection_horizon_open_v09 from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_horizon_history_v09,
 public.alpha_hunter_paper_protection_horizon_open_v09 to service_role;

create or replace function public.alpha_hunter_commit_paper_exit_reconciliation_v04(
  attempt_rows jsonb,
  exit_fill_rows jsonb,
  event_rows jsonb
)
returns void
language plpgsql
security invoker
set search_path=''
as $$
begin
  if jsonb_typeof(attempt_rows)<>'array'
     or jsonb_typeof(exit_fill_rows)<>'array'
     or jsonb_typeof(event_rows)<>'array' then
    raise exception 'paper exit reconciliation payloads must be JSON arrays';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('alpha-hunter-paper-exit-reconciliation-v04',0)
  );

  select coalesce(pg_catalog.jsonb_agg(j),'[]'::jsonb)
    into attempt_rows
  from pg_catalog.jsonb_array_elements(attempt_rows) j
  where not exists (
    select 1
    from public.alpha_hunter_paper_exit_attempts_v04 a
    where a.attempt_id=j->>'attempt_id'
  );

  if pg_catalog.jsonb_array_length(attempt_rows)=0 then
    return;
  end if;

  if exists (
    select 1 from pg_catalog.jsonb_array_elements(exit_fill_rows) j
    where j->>'protection_type'='HORIZON_24H' and not exists (
      select 1 from public.alpha_hunter_paper_protection_horizon_open_v09 p
      join public.alpha_hunter_snapshots s on s.run_id=j->>'source_run_id'
      where p.entry_order_id=j->>'entry_order_id'
        and p.decision_id=j->>'decision_id'
        and p.horizon_protocol='paper-horizon-24h-v0.1'
        and not p.horizon_integrity_failed and not p.unresolved_protective_evidence
        and s.payload->'validation_identity'->>'run_source'='RENDER_CRON'
        and s.payload->'validation_identity'->>'runtime_role'='RENDER_CRON'
        and s.payload->'validation_identity'->>'scientific_fingerprint_sha256'
            =p.horizon_scientific_fingerprint_sha256
        and (j->>'filled_at_utc')::timestamptz between
            p.entry_completed_at_utc+interval '24 hours' and
            p.entry_completed_at_utc+interval '24 hours 35 minutes'
        and (j->>'filled_at_utc')::timestamptz>s.collected_at_utc-interval '1 microsecond'
        and (j->>'filled_at_utc')::timestamptz
            >coalesce(p.previous_exit_observed_at_utc,p.entry_completed_at_utc)
        and (j->>'filled_at_utc')::timestamptz
            <=coalesce(p.previous_exit_observed_at_utc,p.entry_completed_at_utc)+interval '35 minutes'
        and (j->>'quantity')::numeric=p.entry_quantity
        and j->>'triggered_protective_order_id' is null
        and exists (
          select 1 from pg_catalog.jsonb_array_elements(attempt_rows) a
          where a->>'entry_order_id'=j->>'entry_order_id'
            and a->>'source_run_id'=j->>'source_run_id'
            and a->>'outcome'='HORIZON_CLOSED'
            and a->'evidence'->>'horizon_integrity_failed'='false'
            and (a->>'observed_at_utc')::timestamptz=(j->>'filled_at_utc')::timestamptz
            and case when p.direction='LONG' then
              (a->>'best_bid_size')::numeric>=p.entry_quantity
              and (a->>'best_bid')::numeric>p.stop_trigger_price
              and (a->>'best_bid')::numeric<p.target_trigger_price
            else
              (a->>'best_ask_size')::numeric>=p.entry_quantity
              and (a->>'best_ask')::numeric<p.stop_trigger_price
              and (a->>'best_ask')::numeric>p.target_trigger_price end
        )
    )
  ) then raise exception 'Horizon fill violates frozen successor evidence contract'; end if;

  insert into public.alpha_hunter_paper_exit_attempts_v04 (
    attempt_id,entry_order_id,decision_id,source_run_id,observed_at_utc,
    symbol,direction,best_bid,best_ask,best_bid_size,best_ask_size,outcome,
    triggered_protection_type,blockers,evidence,paper_only,exchange_authority,
    trade_permission,order_path
  )
  select
    j->>'attempt_id',j->>'entry_order_id',j->>'decision_id',j->>'source_run_id',
    (j->>'observed_at_utc')::timestamptz,j->>'symbol',j->>'direction',
    (j->>'best_bid')::numeric,(j->>'best_ask')::numeric,
    (j->>'best_bid_size')::numeric,(j->>'best_ask_size')::numeric,
    j->>'outcome',j->>'triggered_protection_type',j->'blockers',j->'evidence',
    (j->>'paper_only')::boolean,(j->>'exchange_authority')::boolean,
    (j->>'trade_permission')::boolean,j->>'order_path'
  from pg_catalog.jsonb_array_elements(attempt_rows) j;

  insert into public.alpha_hunter_paper_exit_fills_v04 (
    exit_fill_id,entry_order_id,decision_id,source_run_id,
    triggered_protective_order_id,protection_type,filled_at_utc,symbol,
    direction,side,quantity,entry_average_fill_price,exit_price,notional_usdt,
    midpoint_reference,cross_price_reference,spread_cost_usdt,slippage_bps,
    slippage_cost_usdt,fee_bps,fee_usdt,entry_costs_usdt,exit_costs_usdt,
    gross_pnl_usdt,paper_net_pnl_ex_funding,planned_risk_usdt,gross_r,
    net_r_ex_funding,funding_bound,full_economic_pnl_claim_permitted,
    liquidity_source,model_quality,paper_only,exchange_authority,
    trade_permission,order_path
  )
  select
    j->>'exit_fill_id',j->>'entry_order_id',j->>'decision_id',
    j->>'source_run_id',j->>'triggered_protective_order_id',
    j->>'protection_type',(j->>'filled_at_utc')::timestamptz,
    j->>'symbol',j->>'direction',j->>'side',(j->>'quantity')::numeric,
    (j->>'entry_average_fill_price')::numeric,(j->>'exit_price')::numeric,
    (j->>'notional_usdt')::numeric,(j->>'midpoint_reference')::numeric,
    (j->>'cross_price_reference')::numeric,(j->>'spread_cost_usdt')::numeric,
    (j->>'slippage_bps')::numeric,(j->>'slippage_cost_usdt')::numeric,
    (j->>'fee_bps')::numeric,(j->>'fee_usdt')::numeric,
    (j->>'entry_costs_usdt')::numeric,(j->>'exit_costs_usdt')::numeric,
    (j->>'gross_pnl_usdt')::numeric,(j->>'paper_net_pnl_ex_funding')::numeric,
    (j->>'planned_risk_usdt')::numeric,(j->>'gross_r')::numeric,
    (j->>'net_r_ex_funding')::numeric,(j->>'funding_bound')::boolean,
    (j->>'full_economic_pnl_claim_permitted')::boolean,
    j->>'liquidity_source',j->>'model_quality',(j->>'paper_only')::boolean,
    (j->>'exchange_authority')::boolean,(j->>'trade_permission')::boolean,
    j->>'order_path'
  from pg_catalog.jsonb_array_elements(exit_fill_rows) j
  where exists (
    select 1
    from pg_catalog.jsonb_array_elements(attempt_rows) a
    where a->>'entry_order_id'=j->>'entry_order_id'
      and a->>'source_run_id'=j->>'source_run_id'
      and a->>'outcome' in ('STOP_TRIGGERED','TARGET_TRIGGERED','HORIZON_CLOSED')
  )
  on conflict(entry_order_id) do nothing;

  insert into public.alpha_hunter_paper_events_v01 (
    event_id,decision_id,sequence,occurred_at_utc,event_type,state,payload,
    paper_only,exchange_authority,trade_permission,order_path
  )
  select
    j->>'event_id',j->>'decision_id',(j->>'sequence')::integer,
    (j->>'occurred_at_utc')::timestamptz,j->>'event_type',j->>'state',
    j->'payload',(j->>'paper_only')::boolean,
    (j->>'exchange_authority')::boolean,(j->>'trade_permission')::boolean,
    j->>'order_path'
  from pg_catalog.jsonb_array_elements(event_rows) j
  where exists (
    select 1
    from public.alpha_hunter_paper_exit_fills_v04 x
    where x.exit_fill_id=j->'payload'->>'exit_fill_id'
      and x.decision_id=j->>'decision_id'
  )
  on conflict(event_id) do nothing;
end;
$$;

revoke all on function public.alpha_hunter_commit_paper_exit_reconciliation_v04(
  jsonb,jsonb,jsonb
) from public,anon,authenticated,service_role;
grant execute on function public.alpha_hunter_commit_paper_exit_reconciliation_v04(
  jsonb,jsonb,jsonb
) to service_role;

create or replace view public.alpha_hunter_paper_completed_trade_quality_v09
with (security_invoker=true,security_barrier=true)
as
with activation as (
  select a.*
  from public.alpha_hunter_paper_execution_activation_v09 a
  where a.activation_id='PAPER_EXECUTION_R9'
  order by a.activated_at_utc desc
  limit 1
),
base as (
  select
    c.*,
    o.submitted_at_utc,
    o.quantity as ordered_quantity,
    d.strategy_id,
    d.strategy_name,
    d.evidence as decision_evidence,
    a.activated_at_utc as r9_activated_at_utc,
    a.release_git_commit as r9_release_git_commit,
    a.scientific_fingerprint_sha256 as r9_scientific_fingerprint_sha256,
    a.maximum_entry_age_minutes,
    a.maximum_monitoring_gap_minutes,
    a.required_run_source,
    a.required_runtime_role
  from public.alpha_hunter_paper_completed_trades_valid_v05 c
  join public.alpha_hunter_paper_orders_v02 o
    on o.order_id=c.entry_order_id
  join public.alpha_hunter_paper_decisions_v01 d
    on d.decision_id=c.decision_id
  cross join activation a
  where o.submitted_at_utc>=a.activated_at_utc
),
fill_summary as (
  select
    f.order_id,
    count(*)::integer as entry_fill_count,
    sum(f.quantity) as total_entry_fill_quantity,
    min(f.filled_at_utc) as first_entry_fill_at_utc,
    max(f.filled_at_utc) as final_entry_fill_at_utc
  from public.alpha_hunter_paper_fills_v02 f
  group by f.order_id
),
partial_history as (
  select
    d.decision_id,
    count(*) filter(where e.state='PARTIALLY_FILLED')::integer
      as partial_fill_state_count
  from public.alpha_hunter_paper_decisions_v01 d
  left join public.alpha_hunter_paper_events_v01 e using(decision_id)
  group by d.decision_id
),
protection_start as (
  select
    p.entry_order_id,
    min(p.created_at_utc) as protection_created_at_utc
  from public.alpha_hunter_paper_protective_orders_v03 p
  group by p.entry_order_id
),
timeline as (
  select
    b.entry_order_id,
    ps.protection_created_at_utc as observed_at_utc
  from base b
  join protection_start ps using(entry_order_id)

  union all

  select
    b.entry_order_id,
    a.observed_at_utc
  from base b
  join public.alpha_hunter_paper_exit_attempts_v04 a using(entry_order_id)

  union all

  select
    b.entry_order_id,
    b.closed_at_utc
  from base b
),
gaps as (
  select
    entry_order_id,
    observed_at_utc,
    extract(epoch from (
      observed_at_utc
      - lag(observed_at_utc) over(
          partition by entry_order_id
          order by observed_at_utc
        )
    ))/60.0 as monitoring_gap_minutes
  from timeline
),
monitoring as (
  select
    entry_order_id,
    max(monitoring_gap_minutes) as maximum_monitoring_gap_minutes_observed
  from gaps
  group by entry_order_id
)
select
  b.*,
  fs.entry_fill_count,
  fs.total_entry_fill_quantity,
  fs.first_entry_fill_at_utc,
  fs.final_entry_fill_at_utc,
  ph.partial_fill_state_count,
  m.maximum_monitoring_gap_minutes_observed,
  extract(epoch from (
    fs.final_entry_fill_at_utc-b.submitted_at_utc
  ))/60.0 as entry_fill_age_minutes,

  (
    coalesce(
      (b.decision_evidence->'paper_authority_source_gate'->>'passed')::boolean,
      false
    )
    and coalesce(
      b.decision_evidence->'paper_authority_source_gate'->>'observed_run_source',
      ''
    )=b.required_run_source
    and coalesce(
      b.decision_evidence->'paper_authority_source_gate'->>'observed_runtime_role',
      ''
    )=b.required_runtime_role
  ) as canonical_paper_authority_source_valid,

  (
    coalesce(
      b.decision_evidence->'validation_identity'
        ->>'scientific_fingerprint_sha256',
      ''
    )=b.r9_scientific_fingerprint_sha256
  ) as scientific_fingerprint_match,

  (
    coalesce(fs.entry_fill_count,0)=1
    and abs(
      coalesce(fs.total_entry_fill_quantity,0)-b.ordered_quantity
    )<=0.000000000001
    and coalesce(ph.partial_fill_state_count,0)=0
  ) as all_or_none_entry_valid,

  (
    fs.final_entry_fill_at_utc is not null
    and extract(epoch from (
      fs.final_entry_fill_at_utc-b.submitted_at_utc
    ))/60.0<=b.maximum_entry_age_minutes
  ) as entry_freshness_valid,

  (
    m.maximum_monitoring_gap_minutes_observed is not null
    and m.maximum_monitoring_gap_minutes_observed
        <=b.maximum_monitoring_gap_minutes
  ) as monitoring_cadence_valid,

  false as live_money_claim_permitted,
  false as production_promotion_permitted
from base b
left join fill_summary fs on fs.order_id=b.entry_order_id
left join partial_history ph on ph.decision_id=b.decision_id
left join monitoring m on m.entry_order_id=b.entry_order_id;

revoke all on public.alpha_hunter_paper_completed_trade_quality_v09
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trade_quality_v09
  to service_role;


create or replace view public.alpha_hunter_paper_completed_trades_valid_v09
with (security_invoker=true,security_barrier=true)
as
select *
from public.alpha_hunter_paper_completed_trade_quality_v09
where canonical_paper_authority_source_valid=true
  and scientific_fingerprint_match=true
  and all_or_none_entry_valid=true
  and entry_freshness_valid=true
  and monitoring_cadence_valid=true;

revoke all on public.alpha_hunter_paper_completed_trades_valid_v09
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trades_valid_v09
  to service_role;


create or replace view public.alpha_hunter_paper_completed_trades_quarantine_v09
with (security_invoker=true,security_barrier=true)
as
select
  q.*,
  array_remove(array[
    case when not canonical_paper_authority_source_valid
      then 'NON_CANONICAL_PAPER_AUTHORITY_SOURCE' end,
    case when not scientific_fingerprint_match
      then 'SCIENTIFIC_FINGERPRINT_MISMATCH' end,
    case when not all_or_none_entry_valid
      then 'ENTRY_NOT_ALL_OR_NONE' end,
    case when not entry_freshness_valid
      then 'ENTRY_STALE_OVER_35M' end,
    case when not monitoring_cadence_valid
      then 'PROTECTIVE_MONITORING_GAP_OVER_35M' end
  ],null) as quarantine_reasons
from public.alpha_hunter_paper_completed_trade_quality_v09 q
where not (
  canonical_paper_authority_source_valid
  and scientific_fingerprint_match
  and all_or_none_entry_valid
  and entry_freshness_valid
  and monitoring_cadence_valid
);

revoke all on public.alpha_hunter_paper_completed_trades_quarantine_v09
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trades_quarantine_v09
  to service_role;



-- All admitted orders remain visible, including failed, pending and unfilled orders.
create view public.alpha_hunter_paper_cohort_members_v09
with(security_invoker=true,security_barrier=true) as
select a.spec_id,o.order_id,o.decision_id,o.symbol,o.direction,o.submitted_at_utc,
 le.state as latest_state,f.entry_completed_at_utc,x.filled_at_utc as closed_at_utc,
 q.net_r_ex_funding,q.paper_net_pnl_ex_funding,
 coalesce(q.entry_order_id is not null,false) as completed_quality_valid,
 (coalesce(h.horizon_integrity_failed,false)
  or (f.entry_completed_at_utc is not null and
      coalesce(x.filled_at_utc,clock_timestamp())>f.entry_completed_at_utc+interval '24 hours 35 minutes')
  or o.submitted_at_utc>a.admission_cutoff_at_utc
 ) as horizon_integrity_failed,
 (le.state in ('EXPIRED','CANCELLED') and coalesce(f.filled_quantity,0)=0)
   or x.exit_fill_id is not null as terminal_reconciled
from public.alpha_hunter_paper_execution_activation_v09 a
join public.alpha_hunter_paper_orders_v02 o on o.submitted_at_utc>a.activated_at_utc
left join lateral (
 select e.state from public.alpha_hunter_paper_events_v01 e
 where e.decision_id=o.decision_id order by e.sequence desc,e.created_at desc limit 1
) le on true
left join lateral (
 select max(v.filled_at_utc) as entry_completed_at_utc,sum(v.quantity) as filled_quantity
 from public.alpha_hunter_paper_fills_v02 v where v.order_id=o.order_id
) f on true
left join public.alpha_hunter_paper_exit_fills_v04 x on x.entry_order_id=o.order_id
left join public.alpha_hunter_paper_completed_trades_valid_v09 q on q.entry_order_id=o.order_id
left join public.alpha_hunter_paper_horizon_history_v09 h on h.entry_order_id=o.order_id;

create view public.alpha_hunter_paper_profitability_status_v09
with(security_invoker=true,security_barrier=true) as
with totals as (
 select a.spec_id,a.activated_at_utc,a.admission_cutoff_at_utc,
 count(m.order_id) as admitted_orders,
 count(*) filter(where m.order_id is not null and not coalesce(m.terminal_reconciled,false)) as unresolved_orders,
 count(*) filter(where m.horizon_integrity_failed or
   (m.closed_at_utc is not null and not m.completed_quality_valid)) as integrity_failed_orders,
 count(*) filter(where m.closed_at_utc is not null and m.completed_quality_valid
   and not m.horizon_integrity_failed) as completed_paper_trades,
 avg(m.net_r_ex_funding) filter(where m.completed_quality_valid and not m.horizon_integrity_failed) as avg_net_r,
 stddev_samp(m.net_r_ex_funding) filter(where m.completed_quality_valid and not m.horizon_integrity_failed) as sd_net_r,
 sum(m.net_r_ex_funding) filter(where m.net_r_ex_funding>0)/
   nullif(abs(sum(m.net_r_ex_funding) filter(where m.net_r_ex_funding<0)),0) as net_profit_factor
 from public.alpha_hunter_paper_execution_activation_v09 a
 left join public.alpha_hunter_paper_cohort_members_v09 m using(spec_id)
 group by a.spec_id,a.activated_at_utc,a.admission_cutoff_at_utc
), runtime as (
 select a.spec_id,count(p.run_id) as real_scans_since_registration,
 max(p.collected_at_utc) as latest_live_scan_at_utc,
 count(*) filter(where p.run_id is not null and
 (p.payload->'validation_identity'->>'scientific_fingerprint_sha256'
    is distinct from a.scientific_fingerprint_sha256
  or p.payload->'validation_identity'->>'runtime_role' is distinct from 'RENDER_CRON')) as identity_drift_scans
 from public.alpha_hunter_paper_execution_activation_v09 a
 left join public.alpha_hunter_snapshots p on p.collected_at_utc>a.activated_at_utc
   and p.collected_at_utc<=a.admission_cutoff_at_utc
   and p.payload->'validation_identity'->>'run_source'='RENDER_CRON'
 group by a.spec_id
), stats as (
 select t.*,r.real_scans_since_registration,r.latest_live_scan_at_utc,r.identity_drift_scans,extract(epoch from(clock_timestamp()-activated_at_utc))/86400 as test_days_elapsed,
 avg_net_r-1.96*sd_net_r/nullif(sqrt(completed_paper_trades::double precision),0) as net_r_lower_bound,
 coalesce(c.full_cost_validation_evidence_complete,false)
   and coalesce(c.cost_model_activation_permitted,false)
   and coalesce(c.realistic_net_r_claim_permitted,false) as cost_validated
 from totals t join runtime r using(spec_id)
 left join public.alpha_hunter_execution_cost_validation_readiness_v04 c on true
), verdict as (
 select s.*,case
 when exists(select 1 from public.alpha_hunter_paper_admission_halts_v09) then 'BLOCKED_ADMISSION_HALTED'
 when integrity_failed_orders>0 then 'BLOCKED_SUCCESSOR_INTEGRITY'
 when identity_drift_scans>0 then 'BLOCKED_SUCCESSOR_IDENTITY_DRIFT'
 when clock_timestamp()<=admission_cutoff_at_utc and (latest_live_scan_at_utc is null
   or latest_live_scan_at_utc<clock_timestamp()-interval '35 minutes') then 'BLOCKED_CANONICAL_SCAN_STALE'
 when clock_timestamp()<=admission_cutoff_at_utc then 'RUNNING_MINIMUM_DURATION_NOT_MET'
 when unresolved_orders>0 then 'RUNNING_ADMITTED_ORDERS_UNRESOLVED'
 when completed_paper_trades<100 then 'INSUFFICIENT_COMPLETED_SAMPLE_AT_FROZEN_CUT'
 when not cost_validated then 'BLOCKED_VALIDATED_COST_MODEL_MISSING'
 when net_r_lower_bound>0 and coalesce(net_profit_factor,0)>1 then 'PAPER_EVIDENCE_PASS'
 else 'PAPER_PROFITABILITY_NOT_DEMONSTRATED' end as profitability_status
 from stats s
)
select v.*,30 as minimum_test_days,100 as minimum_completed_paper_trades,
 clock_timestamp() as evaluated_at_utc,
 case when profitability_status like 'BLOCKED_%' then 'BLOCKED' else 'EVIDENCE_COLLECTION' end as operational_status,
 profitability_status as verdict,
 array_remove(array[
  case when not cost_validated then 'VALIDATED_EXECUTION_COST_MODEL_MISSING' end,
  case when integrity_failed_orders>0 then 'SUCCESSOR_INTEGRITY_FAILURE' end,
  case when unresolved_orders>0 then 'ADMITTED_ORDERS_UNRESOLVED' end,
  case when identity_drift_scans>0 then 'SUCCESSOR_SCIENTIFIC_IDENTITY_DRIFT' end,
  case when profitability_status='BLOCKED_CANONICAL_SCAN_STALE' then 'LIVE_SCAN_STALE' end
 ],null) as blockers,
 true as paper_only,false as trade_permission,false as production_promotion_permitted,'NONE'::text as order_path,
 'realtime-test-engine-r9-horizon-v0.1'::text as engine_version,
 false as live_money_claim_permitted,
 jsonb_build_object('all_admitted_orders',admitted_orders,'unresolved_orders',unresolved_orders,
 'integrity_failed_orders',integrity_failed_orders,'admission_cutoff_at_utc',admission_cutoff_at_utc) as source_status
from verdict v;

revoke all on public.alpha_hunter_paper_cohort_members_v09,
 public.alpha_hunter_paper_profitability_status_v09 from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_cohort_members_v09,
 public.alpha_hunter_paper_profitability_status_v09 to service_role;

-- Independent diagnostics: no activation or changes to active R8 outcomes.
create view public.alpha_hunter_paper_repair_status_v01
with(security_invoker=true,security_barrier=true) as
select
 (select count(*) from public.alpha_hunter_paper_reconciliation_inventory_v08
   where execution_state='RECONCILIATION_REQUIRED') as unresolved_entry_orders,
 (select count(*) from public.alpha_hunter_paper_protection_open_v04 p
   join public.alpha_hunter_paper_orders_v02 o on o.order_id=p.entry_order_id
   join public.alpha_hunter_paper_execution_integrity_activation_v08 a
     on a.activation_id='PAPER_EXECUTION_R8' and o.submitted_at_utc>=a.activated_at_utc
   where clock_timestamp()>p.entry_completed_at_utc+interval '24 hours') as open_positions_over_24h,
 (select count(*) from public.alpha_hunter_paper_execution_activation_v09)>0 as successor_activated,
 clock_timestamp() as checked_at_utc,
 true as paper_only,false as trade_permission,'NONE'::text as order_path;
revoke all on public.alpha_hunter_paper_repair_status_v01 from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_repair_status_v01 to service_role;
commit;
