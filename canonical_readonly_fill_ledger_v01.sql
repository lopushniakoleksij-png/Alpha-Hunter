begin;

-- Alpha Hunter canonical read-only Bitget fill evidence v0.1.
-- Evidence only: no order path, no slippage claim, no execution authority.

create table if not exists public.alpha_hunter_fill_traceability_runs (
  traceability_run_id text primary key,
  source_run_id text not null,
  observed_at_utc timestamptz not null,
  window_start_utc timestamptz not null,
  window_end_utc timestamptz not null,
  endpoint text not null,
  status text not null,
  complete boolean not null default false,
  schema_validated boolean not null default false,
  pages_fetched integer not null default 0 check (pages_fetched >= 0),
  fill_count integer not null default 0 check (fill_count >= 0),
  oldest_fill_at_utc timestamptz,
  newest_fill_at_utc timestamptz,
  detail text,
  evidence jsonb not null default '{}'::jsonb,
  model_version text not null,
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default now(),
  check (window_end_utc >= window_start_utc)
);

create table if not exists public.alpha_hunter_fill_evidence (
  fill_evidence_id text primary key,
  traceability_run_id text not null references public.alpha_hunter_fill_traceability_runs(traceability_run_id),
  source_run_id text not null,
  observed_at_utc timestamptz not null,
  fill_time_utc timestamptz not null,
  trade_id text not null unique,
  order_id text not null,
  symbol text not null,
  side text not null check (side in ('BUY','SELL')),
  trade_side text,
  position_mode text,
  trade_scope text not null check (trade_scope in ('MAKER','TAKER')),
  price double precision not null check (price > 0),
  base_volume double precision not null check (base_volume > 0),
  quote_volume double precision,
  profit double precision,
  fee_amount double precision,
  fee_coin text,
  enter_point_source text,
  cost_fields_complete boolean not null default false,
  evidence jsonb not null default '{}'::jsonb,
  model_version text not null,
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default now()
);

create index if not exists idx_ah_fill_traceability_source_run
  on public.alpha_hunter_fill_traceability_runs(source_run_id, observed_at_utc desc);
create index if not exists idx_ah_fill_evidence_symbol_time
  on public.alpha_hunter_fill_evidence(symbol, fill_time_utc desc);
create index if not exists idx_ah_fill_evidence_order
  on public.alpha_hunter_fill_evidence(order_id);

alter table public.alpha_hunter_fill_traceability_runs enable row level security;
alter table public.alpha_hunter_fill_evidence enable row level security;

revoke all on table public.alpha_hunter_fill_traceability_runs from public, anon, authenticated;
revoke all on table public.alpha_hunter_fill_evidence from public, anon, authenticated;

-- Both tables are immutable evidence. Reuse the project's existing append-only guard.
drop trigger if exists trg_ah_fill_traceability_append_only on public.alpha_hunter_fill_traceability_runs;
create trigger trg_ah_fill_traceability_append_only
before update or delete on public.alpha_hunter_fill_traceability_runs
for each row execute function private.alpha_hunter_block_append_only_mutation();

drop trigger if exists trg_ah_fill_evidence_append_only on public.alpha_hunter_fill_evidence;
create trigger trg_ah_fill_evidence_append_only
before update or delete on public.alpha_hunter_fill_evidence
for each row execute function private.alpha_hunter_block_append_only_mutation();

commit;
