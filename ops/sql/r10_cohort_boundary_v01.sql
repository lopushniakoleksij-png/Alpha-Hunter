begin;

-- R10 cohort boundary + activation interlock v0.1.
--
-- INACTIVE SCAFFOLD ONLY:
-- - does not insert an R10 profitability spec;
-- - does not insert an R10 paper-execution activation;
-- - does not reopen R9 admission;
-- - does not authorize exchange/live orders;
-- - does not rewrite historical R9/R8 evidence.
--
-- Future successor membership is bound to the immutable paper order at the
-- original admission event. Fill time can never move an order between cohorts.

alter table public.alpha_hunter_paper_orders_v02
  add column if not exists successor_activation_id text,
  add column if not exists successor_spec_id text,
  add column if not exists successor_scientific_fingerprint_sha256 text,
  add column if not exists successor_source_run_id text;

alter table public.alpha_hunter_paper_orders_v02
  drop constraint if exists alpha_hunter_paper_orders_v02_successor_identity_check;
alter table public.alpha_hunter_paper_orders_v02
  add constraint alpha_hunter_paper_orders_v02_successor_identity_check check (
    (
      successor_activation_id is null
      and successor_spec_id is null
      and successor_scientific_fingerprint_sha256 is null
      and successor_source_run_id is null
    )
    or
    (
      successor_activation_id='PAPER_EXECUTION_R10'
      and successor_spec_id is not null
      and length(successor_spec_id)>0
      and successor_scientific_fingerprint_sha256 ~ '^[a-f0-9]{64}$'
      and successor_source_run_id is not null
      and length(successor_source_run_id)>0
    )
  );

create table public.alpha_hunter_paper_execution_activation_v10 (
  activation_id text primary key check(activation_id='PAPER_EXECUTION_R10'),
  spec_id text not null unique
    references public.alpha_hunter_profitability_test_specs_v01(spec_id),
  protocol_version text not null check(protocol_version='paper-horizon-24h-v0.1'),
  activated_at_utc timestamptz not null,
  runtime_verified_at_utc timestamptz not null,
  admission_cutoff_at_utc timestamptz not null,
  release_git_commit text not null check(release_git_commit ~ '^[a-f0-9]{40}$'),
  scientific_fingerprint_sha256 text not null
    check(scientific_fingerprint_sha256 ~ '^[a-f0-9]{64}$'),
  maximum_entry_age_minutes integer not null default 35
    check(maximum_entry_age_minutes=35),
  maximum_monitoring_gap_minutes integer not null default 35
    check(maximum_monitoring_gap_minutes=35),
  horizon_hours integer not null default 24 check(horizon_hours=24),
  maximum_horizon_lag_minutes integer not null default 35
    check(maximum_horizon_lag_minutes=35),
  required_run_source text not null default 'RENDER_CRON'
    check(required_run_source='RENDER_CRON'),
  required_runtime_role text not null default 'RENDER_CRON'
    check(required_runtime_role='RENDER_CRON'),
  evidence jsonb not null check(jsonb_typeof(evidence)='object'),
  paper_only boolean not null default true check(paper_only),
  exchange_authority boolean not null default false check(not exchange_authority),
  trade_permission boolean not null default false check(not trade_permission),
  production_promotion_permitted boolean not null default false
    check(not production_promotion_permitted),
  order_path text not null default 'NONE' check(order_path='NONE'),
  check(activated_at_utc>runtime_verified_at_utc),
  check(admission_cutoff_at_utc=activated_at_utc+interval '30 days')
);

alter table public.alpha_hunter_paper_execution_activation_v10 enable row level security;
revoke all on public.alpha_hunter_paper_execution_activation_v10
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_execution_activation_v10 to service_role;
create trigger trg_ah_r10_activation_append_only
before update or delete on public.alpha_hunter_paper_execution_activation_v10
for each row execute function private.alpha_hunter_block_append_only_mutation();

create table public.alpha_hunter_paper_admission_halts_v10 (
  activation_id text primary key
    references public.alpha_hunter_paper_execution_activation_v10(activation_id),
  halted_at_utc timestamptz not null default clock_timestamp(),
  reason text not null check(length(reason)>0)
);
alter table public.alpha_hunter_paper_admission_halts_v10 enable row level security;
revoke all on public.alpha_hunter_paper_admission_halts_v10
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_admission_halts_v10 to service_role;
create trigger trg_ah_r10_halts_append_only
before update or delete on public.alpha_hunter_paper_admission_halts_v10
for each row execute function private.alpha_hunter_block_append_only_mutation();

create view public.alpha_hunter_paper_admission_open_v10
with(security_invoker=true,security_barrier=true) as
select a.*
from public.alpha_hunter_paper_execution_activation_v10 a
where not exists (
  select 1
  from public.alpha_hunter_paper_admission_halts_v10 h
  where h.activation_id=a.activation_id
);
revoke all on public.alpha_hunter_paper_admission_open_v10
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_admission_open_v10 to service_role;

-- Freeze R9 membership at its immutable admission boundary. A future successor
-- order submitted after the R9 halt can no longer be counted as R9 merely
-- because it happened after the R9 activation timestamp.
create or replace view public.alpha_hunter_paper_cohort_members_v09
with(security_invoker=true,security_barrier=true) as
select a.spec_id,o.order_id,o.decision_id,o.symbol,o.direction,o.submitted_at_utc,
 le.state as latest_state,f.entry_completed_at_utc,x.filled_at_utc as closed_at_utc,
 q.net_r_ex_funding,q.paper_net_pnl_ex_funding,
 coalesce(q.entry_order_id is not null,false) as completed_quality_valid,
 (coalesce(hh.horizon_integrity_failed,false)
  or (f.entry_completed_at_utc is not null and
      coalesce(x.filled_at_utc,clock_timestamp())>f.entry_completed_at_utc+interval '24 hours 35 minutes')
  or o.submitted_at_utc>a.admission_cutoff_at_utc
 ) as horizon_integrity_failed,
 (le.state in ('EXPIRED','CANCELLED') and coalesce(f.filled_quantity,0)=0)
   or x.exit_fill_id is not null as terminal_reconciled
from public.alpha_hunter_paper_execution_activation_v09 a
left join public.alpha_hunter_paper_admission_halts_v09 ah
  on ah.activation_id=a.activation_id
join public.alpha_hunter_paper_orders_v02 o
  on o.submitted_at_utc>a.activated_at_utc
 and o.submitted_at_utc<=least(
   a.admission_cutoff_at_utc,
   coalesce(ah.halted_at_utc,a.admission_cutoff_at_utc)
 )
left join lateral (
 select e.state
 from public.alpha_hunter_paper_events_v01 e
 where e.decision_id=o.decision_id
 order by e.sequence desc,e.created_at desc
 limit 1
) le on true
left join lateral (
 select max(v.filled_at_utc) as entry_completed_at_utc,
        sum(v.quantity) as filled_quantity
 from public.alpha_hunter_paper_fills_v02 v
 where v.order_id=o.order_id
) f on true
left join public.alpha_hunter_paper_exit_fills_v04 x
  on x.entry_order_id=o.order_id
left join public.alpha_hunter_paper_completed_trades_valid_v09 q
  on q.entry_order_id=o.order_id
left join public.alpha_hunter_paper_horizon_history_v09 hh
  on hh.entry_order_id=o.order_id;
revoke all on public.alpha_hunter_paper_cohort_members_v09
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_cohort_members_v09 to service_role;

-- Explicit R10 membership comes from immutable order-admission fields, not from
-- fill time or a broad "submitted after activation" inference.
create view public.alpha_hunter_paper_cohort_membership_v10
with(security_invoker=true,security_barrier=true) as
select
  a.activation_id,
  a.spec_id,
  o.order_id,
  o.decision_id,
  o.symbol,
  o.direction,
  o.submitted_at_utc as admitted_at_utc,
  o.successor_source_run_id as source_run_id,
  o.successor_scientific_fingerprint_sha256 as scientific_fingerprint_sha256,
  d.observed_at_utc as decision_observed_at_utc,
  true as explicit_membership,
  'IMMUTABLE_ORDER_ADMISSION'::text as membership_source,
  true as paper_only,
  false as exchange_authority,
  false as trade_permission,
  false as production_promotion_permitted,
  'NONE'::text as order_path
from public.alpha_hunter_paper_execution_activation_v10 a
join public.alpha_hunter_paper_orders_v02 o
  on o.successor_activation_id=a.activation_id
 and o.successor_spec_id=a.spec_id
 and o.successor_scientific_fingerprint_sha256=a.scientific_fingerprint_sha256
join public.alpha_hunter_paper_decisions_v01 d
  on d.decision_id=o.decision_id
 and d.run_id=o.successor_source_run_id
 and d.observed_at_utc=o.submitted_at_utc
where o.submitted_at_utc>a.activated_at_utc
  and o.submitted_at_utc<=a.admission_cutoff_at_utc;
revoke all on public.alpha_hunter_paper_cohort_membership_v10
  from public,anon,authenticated,service_role;
grant select on public.alpha_hunter_paper_cohort_membership_v10 to service_role;

-- Generic profitability activation must remain closed for an R10-role spec until
-- a matching owner-written R10 paper-execution activation row already exists.
create or replace function private.alpha_hunter_guard_r10_profitability_activation_v01()
returns trigger
language plpgsql
security invoker
set search_path=''
as $$
declare
  role_name text;
  exec_row public.alpha_hunter_paper_execution_activation_v10%rowtype;
begin
  select s.scientific_role into role_name
  from public.alpha_hunter_profitability_test_specs_v01 s
  where s.spec_id=new.spec_id;

  if role_name is distinct from 'SUCCESSOR_EXECUTED_PAPER_24H_R10' then
    return new;
  end if;

  select e.* into exec_row
  from public.alpha_hunter_paper_execution_activation_v10 e
  where e.spec_id=new.spec_id
  limit 1;

  if exec_row.activation_id is null then
    return null;
  end if;

  if new.started_at_utc is distinct from exec_row.activated_at_utc then
    raise exception 'R10 profitability activation timestamp must match paper execution activation';
  end if;

  if coalesce(new.baseline_scientific_fingerprint_sha256,'')
     <>exec_row.scientific_fingerprint_sha256 then
    raise exception 'R10 profitability activation fingerprint must match paper execution activation';
  end if;

  return new;
end;
$$;
revoke all on function private.alpha_hunter_guard_r10_profitability_activation_v01()
  from public,anon,authenticated,service_role;

drop trigger if exists trg_ah_r10_profitability_activation_interlock_v01
  on public.alpha_hunter_profitability_test_activations_v01;
create trigger trg_ah_r10_profitability_activation_interlock_v01
before insert on public.alpha_hunter_profitability_test_activations_v01
for each row execute function private.alpha_hunter_guard_r10_profitability_activation_v01();

commit;
