-- Alpha Hunter account funding bill evidence v0.1
--
-- Purpose:
--   Persist sanitized, append-only Bitget Classic account funding cashflows and
--   bind them to reconstructed flat-to-flat episodes only when attribution is
--   unambiguous.
--
-- Source:
--   GET /api/v2/mix/account/bill
--   businessType=contract_settle_fee
--
-- Safety / claim ceiling:
--   * read-only evidence only
--   * raw bill IDs are hashed, not persisted
--   * no transfers / order writes / leverage changes
--   * funding is bound only when exactly one same-symbol complete episode is
--     active at the bill timestamp
--   * ambiguous or unmatched funding stays unbound
--   * full economic PnL is permitted only for episodes fully covered by a
--     complete 90-day funding run and with no ambiguous funding attribution

create table if not exists public.alpha_hunter_funding_bill_runs_v01 (
  funding_run_id text primary key,
  observed_at_utc timestamptz not null,
  window_start_utc timestamptz not null,
  window_end_utc timestamptz not null,
  requested_window_days integer not null check(requested_window_days=90),
  window_count integer not null check(window_count=3),
  pages_fetched integer not null default 0,
  funding_bill_count integer not null default 0,
  status text not null check(
    status in (
      'CONNECTED',
      'ZERO_FUNDING_BILLS',
      'FAILED',
      'INVALID_SCHEMA',
      'NOT_CONFIGURED',
      'BLOCKED_ACCOUNT_API_FAMILY_UNVERIFIED'
    )
  ),
  complete boolean not null default false,
  schema_validated boolean not null default false,
  source_endpoint text not null
    check(source_endpoint='/api/v2/mix/account/bill'),
  read_only_get boolean not null default true check(read_only_get=true),
  no_order_write_path boolean not null default true
    check(no_order_write_path=true),
  detail text,
  model_version text not null default 'funding-bill-evidence-v0.1',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);


create table if not exists public.alpha_hunter_funding_bill_evidence_v01 (
  funding_bill_evidence_id text primary key,
  bill_identity_sha256 text not null unique
    check(bill_identity_sha256 ~ '^[0-9a-f]{64}$'),
  bill_time_utc timestamptz not null,
  symbol text,
  business_type text not null
    check(business_type='contract_settle_fee'),
  amount double precision not null,
  fee double precision,
  fee_by_coupon double precision,
  coin text not null,
  funding_account_effect double precision not null,
  source_endpoint text not null
    check(source_endpoint='/api/v2/mix/account/bill'),
  raw_bill_id_persisted boolean not null default false
    check(raw_bill_id_persisted=false),
  scientific_role text not null default
    'ACCOUNT_OBSERVED_FUNDING_CASHFLOW',
  model_version text not null default 'funding-bill-evidence-v0.1',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  created_at timestamptz not null default clock_timestamp()
);


create table if not exists public.alpha_hunter_funding_bill_links_v01 (
  funding_run_id text not null
    references public.alpha_hunter_funding_bill_runs_v01(funding_run_id),
  funding_bill_evidence_id text not null
    references public.alpha_hunter_funding_bill_evidence_v01(
      funding_bill_evidence_id
    ),
  linked_at_utc timestamptz not null default clock_timestamp(),
  model_version text not null default 'funding-bill-evidence-v0.1',
  shadow_only boolean not null default true check(shadow_only=true),
  trade_permission boolean not null default false check(trade_permission=false),
  primary key(funding_run_id,funding_bill_evidence_id)
);


alter table public.alpha_hunter_funding_bill_runs_v01 enable row level security;
alter table public.alpha_hunter_funding_bill_evidence_v01 enable row level security;
alter table public.alpha_hunter_funding_bill_links_v01 enable row level security;

revoke all on table public.alpha_hunter_funding_bill_runs_v01
  from public,anon,authenticated;
revoke all on table public.alpha_hunter_funding_bill_evidence_v01
  from public,anon,authenticated;
revoke all on table public.alpha_hunter_funding_bill_links_v01
  from public,anon,authenticated;

grant select,insert on table public.alpha_hunter_funding_bill_runs_v01
  to service_role;
grant select,insert on table public.alpha_hunter_funding_bill_evidence_v01
  to service_role;
grant select,insert on table public.alpha_hunter_funding_bill_links_v01
  to service_role;


drop trigger if exists trg_ah_funding_bill_runs_append_only
  on public.alpha_hunter_funding_bill_runs_v01;
create trigger trg_ah_funding_bill_runs_append_only
before update or delete on public.alpha_hunter_funding_bill_runs_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_funding_bill_evidence_append_only
  on public.alpha_hunter_funding_bill_evidence_v01;
create trigger trg_ah_funding_bill_evidence_append_only
before update or delete on public.alpha_hunter_funding_bill_evidence_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_funding_bill_links_append_only
  on public.alpha_hunter_funding_bill_links_v01;
create trigger trg_ah_funding_bill_links_append_only
before update or delete on public.alpha_hunter_funding_bill_links_v01
for each row execute function private.alpha_hunter_block_append_only_mutation();


create index if not exists idx_ah_funding_bill_symbol_time
  on public.alpha_hunter_funding_bill_evidence_v01(symbol,bill_time_utc);

create index if not exists idx_ah_funding_bill_links_run
  on public.alpha_hunter_funding_bill_links_v01(funding_run_id);


create or replace view public.alpha_hunter_roundtrip_funding_binding_v01
with (security_invoker=true,security_barrier=true)
as
with candidate_counts as (
  select
    b.funding_bill_evidence_id,
    b.bill_time_utc,
    b.symbol,
    b.funding_account_effect,
    b.coin,
    count(e.roundtrip_episode_id)::bigint as candidate_episode_count,
    min(e.roundtrip_episode_id) as sole_candidate_episode_id
  from public.alpha_hunter_funding_bill_evidence_v01 b
  left join public.alpha_hunter_roundtrip_episodes_v01 e
    on e.reconstruction_status='COMPLETE_FLAT_TO_FLAT'
   and e.symbol=b.symbol
   and b.bill_time_utc>=e.opened_or_first_seen_at_utc
   and b.bill_time_utc<=e.closed_at_utc
  group by
    b.funding_bill_evidence_id,
    b.bill_time_utc,
    b.symbol,
    b.funding_account_effect,
    b.coin
)
select
  c.funding_bill_evidence_id,
  c.bill_time_utc,
  c.symbol,
  c.funding_account_effect,
  c.coin,
  c.candidate_episode_count,
  case
    when c.candidate_episode_count=1
      then c.sole_candidate_episode_id
  end as roundtrip_episode_id,
  case
    when c.candidate_episode_count=1 then 'BOUND_UNAMBIGUOUS'
    when c.candidate_episode_count=0 then 'UNMATCHED'
    else 'AMBIGUOUS_OVERLAP'
  end as binding_status,
  false as inferred_direction,
  false as alpha_hunter_execution_claim_permitted,
  true as shadow_only,
  false as trade_permission
from candidate_counts c;


create or replace view public.alpha_hunter_roundtrip_funding_summary_v01
with (security_invoker=true,security_barrier=true)
as
select
  e.roundtrip_episode_id,
  e.symbol,
  e.direction,
  e.opened_or_first_seen_at_utc,
  e.closed_at_utc,
  count(b.funding_bill_evidence_id) filter(
    where b.binding_status='BOUND_UNAMBIGUOUS'
  )::bigint as bound_funding_bill_count,
  sum(b.funding_account_effect) filter(
    where b.binding_status='BOUND_UNAMBIGUOUS'
  ) as bound_funding_account_effect,
  count(b.funding_bill_evidence_id) filter(
    where b.binding_status='AMBIGUOUS_OVERLAP'
  )::bigint as ambiguous_funding_bill_count,
  count(b.funding_bill_evidence_id) filter(
    where b.binding_status='UNMATCHED'
  )::bigint as unmatched_funding_bill_count
from public.alpha_hunter_roundtrip_episodes_v01 e
left join public.alpha_hunter_roundtrip_funding_binding_v01 b
  on b.roundtrip_episode_id=e.roundtrip_episode_id
where e.reconstruction_status='COMPLETE_FLAT_TO_FLAT'
group by
  e.roundtrip_episode_id,
  e.symbol,
  e.direction,
  e.opened_or_first_seen_at_utc,
  e.closed_at_utc;


create or replace view public.alpha_hunter_roundtrip_economic_outcome_v01
with (security_invoker=true,security_barrier=true)
as
with latest_complete_run as (
  select r.*
  from public.alpha_hunter_funding_bill_runs_v01 r
  where r.complete=true
    and r.schema_validated=true
    and r.status in ('CONNECTED','ZERO_FUNDING_BILLS')
  order by r.observed_at_utc desc
  limit 1
),
ambiguity_by_episode as (
  select
    e.roundtrip_episode_id,
    count(*) filter(
      where b.binding_status='AMBIGUOUS_OVERLAP'
        and b.symbol=e.symbol
        and b.bill_time_utc>=e.opened_or_first_seen_at_utc
        and b.bill_time_utc<=e.closed_at_utc
    )::bigint as ambiguous_in_episode_window
  from public.alpha_hunter_roundtrip_episodes_v01 e
  left join public.alpha_hunter_roundtrip_funding_binding_v01 b
    on b.symbol=e.symbol
  where e.reconstruction_status='COMPLETE_FLAT_TO_FLAT'
  group by e.roundtrip_episode_id
)
select
  e.roundtrip_episode_id,
  e.symbol,
  e.direction,
  e.opened_or_first_seen_at_utc,
  e.closed_at_utc,
  e.opening_vwap,
  e.closing_vwap,
  e.opened_qty,
  e.profit_field_sum,
  e.signed_trading_fee_sum,
  e.fee_adjusted_profit_ex_funding,
  coalesce(f.bound_funding_bill_count,0) as bound_funding_bill_count,
  coalesce(f.bound_funding_account_effect,0) as bound_funding_account_effect,
  e.fee_adjusted_profit_ex_funding
    +coalesce(f.bound_funding_account_effect,0)
    as economic_pnl_after_fees_and_bound_funding,
  case
    when r.funding_run_id is null then false
    when e.opened_or_first_seen_at_utc<r.window_start_utc then false
    when e.closed_at_utc>r.window_end_utc then false
    when coalesce(a.ambiguous_in_episode_window,0)>0 then false
    else true
  end as funding_coverage_complete,
  case
    when r.funding_run_id is null then 'NO_COMPLETE_FUNDING_RUN'
    when e.opened_or_first_seen_at_utc<r.window_start_utc
      then 'EPISODE_STARTS_BEFORE_FUNDING_WINDOW'
    when e.closed_at_utc>r.window_end_utc
      then 'EPISODE_ENDS_AFTER_FUNDING_WINDOW'
    when coalesce(a.ambiguous_in_episode_window,0)>0
      then 'AMBIGUOUS_FUNDING_ATTRIBUTION'
    else 'COMPLETE'
  end as funding_coverage_status,
  (
    r.funding_run_id is not null
    and e.opened_or_first_seen_at_utc>=r.window_start_utc
    and e.closed_at_utc<=r.window_end_utc
    and coalesce(a.ambiguous_in_episode_window,0)=0
  ) as full_economic_pnl_claim_permitted,
  false as realistic_net_r_claim_permitted,
  false as verified_alpha_hunter_execution,
  false as alpha_hunter_execution_claim_permitted,
  'ACCOUNT_OUTCOME_WITH_TRADING_FEES_AND_BOUND_FUNDING_ONLY'::text
    as scientific_role,
  true as shadow_only,
  false as trade_permission
from public.alpha_hunter_roundtrip_episodes_v01 e
left join public.alpha_hunter_roundtrip_funding_summary_v01 f
  on f.roundtrip_episode_id=e.roundtrip_episode_id
left join ambiguity_by_episode a
  on a.roundtrip_episode_id=e.roundtrip_episode_id
left join latest_complete_run r
  on true
where e.reconstruction_status='COMPLETE_FLAT_TO_FLAT';


create or replace view public.alpha_hunter_funding_bill_status_v01
with (security_invoker=true,security_barrier=true)
as
with latest_run as (
  select *
  from public.alpha_hunter_funding_bill_runs_v01
  order by observed_at_utc desc
  limit 1
)
select
  r.funding_run_id,
  r.observed_at_utc,
  r.window_start_utc,
  r.window_end_utc,
  r.status,
  r.complete,
  r.schema_validated,
  r.pages_fetched,
  r.funding_bill_count,
  count(l.funding_bill_evidence_id)::bigint as linked_bill_count,
  (
    count(l.funding_bill_evidence_id)=r.funding_bill_count
  ) as linkage_count_match,
  (
    select count(*)
    from public.alpha_hunter_roundtrip_funding_binding_v01 b
    where b.binding_status='BOUND_UNAMBIGUOUS'
  )::bigint as unambiguously_bound_funding_bills,
  (
    select count(*)
    from public.alpha_hunter_roundtrip_funding_binding_v01 b
    where b.binding_status='AMBIGUOUS_OVERLAP'
  )::bigint as ambiguous_funding_bills,
  (
    select count(*)
    from public.alpha_hunter_roundtrip_funding_binding_v01 b
    where b.binding_status='UNMATCHED'
  )::bigint as unmatched_funding_bills,
  r.shadow_only,
  r.trade_permission
from latest_run r
left join public.alpha_hunter_funding_bill_links_v01 l
  on l.funding_run_id=r.funding_run_id
group by
  r.funding_run_id,
  r.observed_at_utc,
  r.window_start_utc,
  r.window_end_utc,
  r.status,
  r.complete,
  r.schema_validated,
  r.pages_fetched,
  r.funding_bill_count,
  r.shadow_only,
  r.trade_permission;


revoke all on public.alpha_hunter_roundtrip_funding_binding_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_roundtrip_funding_summary_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_roundtrip_economic_outcome_v01
  from public,anon,authenticated,service_role;
revoke all on public.alpha_hunter_funding_bill_status_v01
  from public,anon,authenticated,service_role;

grant select on public.alpha_hunter_roundtrip_funding_binding_v01
  to service_role;
grant select on public.alpha_hunter_roundtrip_funding_summary_v01
  to service_role;
grant select on public.alpha_hunter_roundtrip_economic_outcome_v01
  to service_role;
grant select on public.alpha_hunter_funding_bill_status_v01
  to service_role;
