create table if not exists public.alpha_hunter_snapshots (
  run_id text primary key,
  collected_at_utc timestamptz not null,
  version text not null,
  product_type text not null,
  symbol_count integer not null,
  error_count integer not null default 0,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.alpha_hunter_symbol_snapshots (
  run_id text not null references public.alpha_hunter_snapshots(run_id) on delete cascade,
  symbol text not null,
  collected_at_utc timestamptz not null,
  state text,
  previous_state text,
  state_changed boolean not null default false,
  trade_permission boolean not null default false,
  direction text,
  reward_risk double precision,
  last_price double precision,
  open_interest double precision,
  funding_rate double precision,
  data_integrity_score integer,
  error text,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  primary key (run_id, symbol)
);

create index if not exists idx_ah_symbol_time
  on public.alpha_hunter_symbol_snapshots(symbol, collected_at_utc desc);
create index if not exists idx_ah_permission_time
  on public.alpha_hunter_symbol_snapshots(trade_permission, collected_at_utc desc);
create index if not exists idx_ah_state_time
  on public.alpha_hunter_symbol_snapshots(state, collected_at_utc desc);

alter table public.alpha_hunter_snapshots enable row level security;
alter table public.alpha_hunter_symbol_snapshots enable row level security;
-- The collector should use SUPABASE_SERVICE_ROLE_KEY on a trusted machine only.
-- Never expose that key in a browser, dashboard, repository or client application.
