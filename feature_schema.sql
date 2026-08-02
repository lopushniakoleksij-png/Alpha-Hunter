create table if not exists public.alpha_hunter_signal_features (
  signal_id text primary key references public.alpha_hunter_signals(signal_id) on delete cascade,
  run_id text not null,
  symbol text not null,
  captured_at_utc timestamptz not null,
  state text,
  direction text,
  trade_permission boolean not null default false,
  trend_15m text,
  trend_1h text,
  trend_4h text,
  btc_regime text,
  sector text,
  session text,
  weekday smallint,
  hour_utc smallint,
  huge_rr_score double precision,
  confidence_estimate_pct double precision,
  reward_risk double precision,
  volume_ratio double precision,
  volume_expansion boolean,
  volatility_pct double precision,
  compression_score double precision,
  funding_rate double precision,
  open_interest double precision,
  open_interest_change_pct double precision,
  relative_strength_btc double precision,
  rsi_15m double precision,
  rsi_1h double precision,
  rsi_4h double precision,
  distance_to_support_pct double precision,
  distance_to_resistance_pct double precision,
  ema_alignment_15m text,
  ema_alignment_1h text,
  ema_alignment_4h text,
  liquidity_state text,
  features jsonb not null default '{}'::jsonb,
  source_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_ah_features_symbol_time
  on public.alpha_hunter_signal_features(symbol, captured_at_utc desc);
create index if not exists idx_ah_features_state_time
  on public.alpha_hunter_signal_features(state, captured_at_utc desc);
create index if not exists idx_ah_features_btc_regime
  on public.alpha_hunter_signal_features(btc_regime, captured_at_utc desc);
create index if not exists idx_ah_features_sector
  on public.alpha_hunter_signal_features(sector, captured_at_utc desc);
create index if not exists idx_ah_features_session
  on public.alpha_hunter_signal_features(session, captured_at_utc desc);

alter table public.alpha_hunter_signal_features enable row level security;
