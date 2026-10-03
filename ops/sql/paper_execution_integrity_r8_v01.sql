begin;

-- Alpha Hunter paper execution integrity R8 v0.1.
--
-- Purpose:
--   Create a clean, explicit paper-execution cohort after the known R7 defects.
--
-- R8 guarantees:
-- - no paper order before explicit R8 activation;
-- - canonical RENDER_CRON paper authority only;
-- - one active/resting exposure per symbol + strategy + direction;
-- - R8 entry reconciliation only for post-activation orders;
-- - entry freshness contract: <=35 minutes;
-- - all-or-none entry fill contract (enforced in runtime, verified here);
-- - completed-trade monitoring cadence <=35 minutes;
-- - runtime scientific fingerprint must match the R8 activation fingerprint;
-- - historical/pre-R8 evidence is preserved but excluded from the clean cohort;
-- - paper/shadow only; no exchange order authority.

create table if not exists public.alpha_hunter_paper_execution_integrity_activation_v08 (
  activation_id text primary key,
  activated_at_utc timestamptz not null,
  release_git_commit text not null,
  scientific_fingerprint_sha256 text not null,
  maximum_entry_age_minutes integer not null default 35
    check(maximum_entry_age_minutes=35),
  maximum_monitoring_gap_minutes integer not null default 35
    check(maximum_monitoring_gap_minutes=35),
  required_run_source text not null default 'RENDER_CRON'
    check(required_run_source='RENDER_CRON'),
  required_runtime_role text not null default 'RENDER_CRON'
    check(required_runtime_role='RENDER_CRON'),
  evidence jsonb not null default '{}'::jsonb,
  scientific_role text not null default 'PAPER_EXECUTION_R8_INTEGRITY_ACTIVATION',
  paper_only boolean not null default true check(paper_only=true),
  exchange_authority boolean not null default false check(exchange_authority=false),
  trade_permission boolean not null default false check(trade_permission=false),
  production_promotion_permitted boolean not null default false
    check(production_promotion_permitted=false),
  order_path text not null default 'NONE' check(order_path='NONE'),
  created_at timestamptz not null default clock_timestamp()
);

alter table public.alpha_hunter_paper_execution_integrity_activation_v08
  enable row level security;

revoke all on public.alpha_hunter_paper_execution_integrity_activation_v08
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_execution_integrity_activation_v08
  to service_role;

drop trigger if exists trg_ah_paper_execution_r8_activation_append_only
  on public.alpha_hunter_paper_execution_integrity_activation_v08;
create trigger trg_ah_paper_execution_r8_activation_append_only
before update or delete on public.alpha_hunter_paper_execution_integrity_activation_v08
for each row execute function private.alpha_hunter_block_append_only_mutation();


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
    e.decision_id,e.sequence,e.state,e.occurred_at_utc
  from public.alpha_hunter_paper_events_v01 e
  order by e.decision_id,e.sequence desc,e.created_at desc
),
fill_state as (
  select
    f.order_id,
    sum(f.quantity) as filled_quantity,
    sum(f.quantity*f.fill_price)/nullif(sum(f.quantity),0) as average_fill_price,
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
    when coalesce(x.filled_quantity,0)>0 then 'PARTIALLY_FILLED'
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
  and le.state in ('SUBMITTED','PARTIALLY_FILLED')
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
    and r.submitted_at_utc
        >=clock_timestamp()-make_interval(mins=>a.maximum_entry_age_minutes)
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


create or replace view public.alpha_hunter_paper_active_exposure_keys_v08
with (security_invoker=true,security_barrier=true)
as
select distinct
  symbol,
  strategy_id,
  direction
from public.alpha_hunter_paper_active_exposure_members_v08
where nullif(symbol,'') is not null
  and nullif(strategy_id,'') is not null
  and direction in ('LONG','SHORT');

revoke all on public.alpha_hunter_paper_active_exposure_keys_v08
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_active_exposure_keys_v08
  to service_role;


create or replace view public.alpha_hunter_paper_completed_trade_quality_v08
with (security_invoker=true,security_barrier=true)
as
with activation as (
  select a.*
  from public.alpha_hunter_paper_execution_integrity_activation_v08 a
  where a.activation_id='PAPER_EXECUTION_R8'
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
    a.activated_at_utc as r8_activated_at_utc,
    a.release_git_commit as r8_release_git_commit,
    a.scientific_fingerprint_sha256 as r8_scientific_fingerprint_sha256,
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
    )=b.r8_scientific_fingerprint_sha256
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

  true as paper_only,
  false as live_money_claim_permitted,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from base b
left join fill_summary fs on fs.order_id=b.entry_order_id
left join partial_history ph on ph.decision_id=b.decision_id
left join monitoring m on m.entry_order_id=b.entry_order_id;

revoke all on public.alpha_hunter_paper_completed_trade_quality_v08
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trade_quality_v08
  to service_role;


create or replace view public.alpha_hunter_paper_completed_trades_valid_v08
with (security_invoker=true,security_barrier=true)
as
select *
from public.alpha_hunter_paper_completed_trade_quality_v08
where canonical_paper_authority_source_valid=true
  and scientific_fingerprint_match=true
  and all_or_none_entry_valid=true
  and entry_freshness_valid=true
  and monitoring_cadence_valid=true;

revoke all on public.alpha_hunter_paper_completed_trades_valid_v08
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trades_valid_v08
  to service_role;


create or replace view public.alpha_hunter_paper_completed_trades_quarantine_v08
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
from public.alpha_hunter_paper_completed_trade_quality_v08 q
where not (
  canonical_paper_authority_source_valid
  and scientific_fingerprint_match
  and all_or_none_entry_valid
  and entry_freshness_valid
  and monitoring_cadence_valid
);

revoke all on public.alpha_hunter_paper_completed_trades_quarantine_v08
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_completed_trades_quarantine_v08
  to service_role;


create or replace view public.alpha_hunter_paper_execution_integrity_status_v08
with (security_invoker=true,security_barrier=true)
as
with activation as (
  select a.*
  from public.alpha_hunter_paper_execution_integrity_activation_v08 a
  where a.activation_id='PAPER_EXECUTION_R8'
  order by a.activated_at_utc desc
  limit 1
),
duplicates as (
  select count(*)::bigint as duplicate_active_exposure_groups
  from (
    select symbol,strategy_id,direction
    from public.alpha_hunter_paper_active_exposure_members_v08
    group by symbol,strategy_id,direction
    having count(*)>1
  ) x
),
valid as (
  select
    count(*)::bigint as clean_completed_trades,
    count(*) filter(where paper_net_pnl_ex_funding>0)::bigint as clean_wins,
    count(*) filter(where paper_net_pnl_ex_funding<=0)::bigint as clean_nonwins,
    sum(paper_net_pnl_ex_funding) as clean_net_pnl_ex_funding_usdt,
    avg(paper_net_pnl_ex_funding) as clean_expectancy_usdt_per_trade,
    sum(net_r_ex_funding) as clean_total_net_r_ex_funding,
    avg(net_r_ex_funding) as clean_avg_net_r_ex_funding
  from public.alpha_hunter_paper_completed_trades_valid_v08
),
quarantine as (
  select count(*)::bigint as quarantined_completed_trades
  from public.alpha_hunter_paper_completed_trades_quarantine_v08
),
active as (
  select
    count(*)::bigint as active_exposure_members,
    count(distinct (symbol,strategy_id,direction))::bigint
      as active_exposure_keys
  from public.alpha_hunter_paper_active_exposure_members_v08
)
select
  a.activation_id,
  a.activated_at_utc,
  a.release_git_commit,
  a.scientific_fingerprint_sha256,
  a.maximum_entry_age_minutes,
  a.maximum_monitoring_gap_minutes,
  v.clean_completed_trades,
  v.clean_wins,
  v.clean_nonwins,
  case
    when v.clean_completed_trades>0
      then 100.0*v.clean_wins::double precision/v.clean_completed_trades
    else null
  end as clean_win_rate_pct,
  v.clean_net_pnl_ex_funding_usdt,
  v.clean_expectancy_usdt_per_trade,
  v.clean_total_net_r_ex_funding,
  v.clean_avg_net_r_ex_funding,
  q.quarantined_completed_trades,
  x.active_exposure_members,
  x.active_exposure_keys,
  d.duplicate_active_exposure_groups,
  (d.duplicate_active_exposure_groups=0) as one_exposure_guard_integrity_ok,
  true as all_or_none_entry_required,
  true as canonical_render_cron_required,
  true as evidence_collection_active,
  true as paper_only,
  false as live_money_claim_permitted,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path,
  'paper-execution-integrity-r8-v0.1'::text as model_version
from activation a
cross join valid v
cross join quarantine q
cross join active x
cross join duplicates d;

revoke all on public.alpha_hunter_paper_execution_integrity_status_v08
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_execution_integrity_status_v08
  to service_role;

commit;
