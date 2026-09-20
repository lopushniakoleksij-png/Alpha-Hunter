begin;

-- Alpha Hunter fill traceability membership ledger v0.1.
--
-- A canonical Bitget fill is immutable and globally deduplicated by trade_id.
-- The same fill may be observed by many complete read-only traceability runs.
-- This append-only membership table records that many-to-many relationship
-- without rewriting the original fill evidence row.

create table if not exists public.alpha_hunter_fill_traceability_links (
  traceability_run_id text not null
    references public.alpha_hunter_fill_traceability_runs(traceability_run_id),
  fill_evidence_id text not null
    references public.alpha_hunter_fill_evidence(fill_evidence_id),

  source_run_id text not null,
  trade_id text not null,
  observed_at_utc timestamptz not null,
  fill_time_utc timestamptz not null,

  model_version text not null,

  shadow_only boolean not null default true
    check (shadow_only = true),
  trade_permission boolean not null default false
    check (trade_permission = false),

  created_at timestamptz not null default now(),

  primary key (traceability_run_id, fill_evidence_id),
  unique (traceability_run_id, trade_id)
);

create index if not exists idx_ah_fill_trace_links_source_run
  on public.alpha_hunter_fill_traceability_links(
    source_run_id,
    observed_at_utc desc
  );

create index if not exists idx_ah_fill_trace_links_fill
  on public.alpha_hunter_fill_traceability_links(fill_evidence_id);

alter table public.alpha_hunter_fill_traceability_links
  enable row level security;

revoke all on table public.alpha_hunter_fill_traceability_links
  from public, anon, authenticated;

drop trigger if exists trg_ah_fill_trace_links_append_only
  on public.alpha_hunter_fill_traceability_links;

create trigger trg_ah_fill_trace_links_append_only
before update or delete on public.alpha_hunter_fill_traceability_links
for each row execute function private.alpha_hunter_block_append_only_mutation();


create or replace view public.alpha_hunter_fill_traceability_linkage_status
with (security_invoker=true, security_barrier=true)
as
select
  r.traceability_run_id,
  r.source_run_id,
  r.observed_at_utc,
  r.status,
  r.complete,
  r.schema_validated,
  r.fill_count,
  count(l.fill_evidence_id)::integer as linked_fill_count,
  (
    count(l.fill_evidence_id)::integer = r.fill_count
  ) as linkage_count_match,
  case
    when r.status='CONNECTED'
      and r.complete=true
      and r.schema_validated=true
      and r.fill_count>0
      and count(l.fill_evidence_id)::integer=r.fill_count
      then 'PASS'
    when r.fill_count=0
      and count(l.fill_evidence_id)=0
      then 'NO_FILLS'
    else 'INCOMPLETE'
  end as linkage_status,
  r.shadow_only,
  r.trade_permission
from public.alpha_hunter_fill_traceability_runs r
left join public.alpha_hunter_fill_traceability_links l
  on l.traceability_run_id=r.traceability_run_id
group by
  r.traceability_run_id,
  r.source_run_id,
  r.observed_at_utc,
  r.status,
  r.complete,
  r.schema_validated,
  r.fill_count,
  r.shadow_only,
  r.trade_permission;

revoke all on public.alpha_hunter_fill_traceability_linkage_status
  from public, anon, authenticated;

grant select on public.alpha_hunter_fill_traceability_linkage_status
  to service_role;

commit;
