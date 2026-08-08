create table if not exists public.alpha_hunter_signals (
  signal_id text primary key,
  run_id text not null,
  symbol text not null,
  detected_at_utc timestamptz not null,
  state text,
  direction text,
  trade_permission boolean not null default false,
  huge_rr_score double precision,
  confidence_estimate_pct double precision,
  reward_risk double precision,
  entry_price double precision,
  stop_loss double precision,
  take_profit double precision,
  reference_price double precision not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.alpha_hunter_signal_outcomes (
  signal_id text not null references public.alpha_hunter_signals(signal_id) on delete cascade,
  horizon_hours integer not null,
  evaluated_at_utc timestamptz not null,
  evaluation_price double precision not null,
  return_pct double precision,
  direction_adjusted_return_pct double precision,
  target_hit boolean,
  stop_hit boolean,
  outcome_class text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (signal_id, horizon_hours)
);

create index if not exists idx_ah_signals_symbol_time
  on public.alpha_hunter_signals(symbol, detected_at_utc desc);
create index if not exists idx_ah_signals_score_time
  on public.alpha_hunter_signals(huge_rr_score desc, detected_at_utc desc);
create index if not exists idx_ah_signals_permission_time
  on public.alpha_hunter_signals(trade_permission, detected_at_utc desc);
create index if not exists idx_ah_outcomes_horizon_class
  on public.alpha_hunter_signal_outcomes(horizon_hours, outcome_class);

alter table public.alpha_hunter_signals enable row level security;
alter table public.alpha_hunter_signal_outcomes enable row level security;
