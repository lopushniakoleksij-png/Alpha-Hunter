create table if not exists public.alpha_hunter_big_mover_shadow (
  observation_id text primary key,
  run_id text not null,
  captured_at_utc timestamptz not null,
  symbol text not null,
  direction text not null check (direction in ('LONG', 'SHORT')),
  similarity_score double precision,
  feature_coverage double precision not null,
  lifecycle text not null,
  research_status text not null,
  current_move_pct double precision,
  model_version text not null,
  mover_examples integer not null,
  control_examples integer not null,
  training_end_utc timestamptz not null,
  latest_audit_utc timestamptz not null,
  audit_staleness_hours double precision not null,
  blockers jsonb not null default '[]'::jsonb,
  contributions jsonb not null default '[]'::jsonb,
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default now()
);

create index if not exists idx_ah_big_mover_shadow_run_rank
  on public.alpha_hunter_big_mover_shadow(run_id, research_status, similarity_score desc);

create index if not exists idx_ah_big_mover_shadow_symbol_time
  on public.alpha_hunter_big_mover_shadow(symbol, captured_at_utc desc);

alter table public.alpha_hunter_big_mover_shadow enable row level security;

revoke all on table public.alpha_hunter_big_mover_shadow from anon, authenticated;
grant select, insert, update on table public.alpha_hunter_big_mover_shadow to service_role;
