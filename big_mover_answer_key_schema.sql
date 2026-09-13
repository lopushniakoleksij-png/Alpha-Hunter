create table if not exists public.alpha_hunter_big_mover_answer_key (
  event_id text primary key,
  observed_at_utc timestamptz not null,
  hour_bucket_utc timestamptz not null,
  symbol text not null,
  product_type text not null,
  direction text not null check (direction in ('UP', 'DOWN')),
  threshold_pct double precision not null check (threshold_pct in (5.0, 10.0, 20.0)),
  current_24h_move_pct double precision not null,
  last_price double precision not null,
  quote_volume_24h double precision not null,
  strategy_eligible boolean not null,
  liquidity_pass boolean not null,
  source text not null,
  model_version text not null,
  shadow_only boolean not null default true check (shadow_only = true),
  trade_permission boolean not null default false check (trade_permission = false),
  created_at timestamptz not null default now()
);

create index if not exists idx_ah_big_mover_answer_key_time
  on public.alpha_hunter_big_mover_answer_key(hour_bucket_utc desc, threshold_pct desc);

create index if not exists idx_ah_big_mover_answer_key_symbol_time
  on public.alpha_hunter_big_mover_answer_key(symbol, hour_bucket_utc desc);

alter table public.alpha_hunter_big_mover_answer_key enable row level security;
revoke all on table public.alpha_hunter_big_mover_answer_key from anon, authenticated;
grant select, insert on table public.alpha_hunter_big_mover_answer_key to service_role;
