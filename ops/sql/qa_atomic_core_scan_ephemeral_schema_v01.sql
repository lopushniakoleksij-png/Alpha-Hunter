-- Ephemeral PostgreSQL 17 only: local synthetic subset matching live core table columns.
-- Never run against Supabase. No credentials, orders, or production data.
create role anon;
create role authenticated;
create role service_role;
create table public.alpha_hunter_snapshots (
  run_id text not null,
  collected_at_utc timestamptz not null,
  version text not null,
  product_type text not null,
  symbol_count int4 not null,
  error_count int4 default 0 not null,
  payload jsonb not null,
  created_at timestamptz default now() not null,
  primary key (run_id)
);
create table public.alpha_hunter_symbol_snapshots (
  run_id text not null,
  symbol text not null,
  collected_at_utc timestamptz not null,
  state text,
  previous_state text,
  state_changed bool default false not null,
  trade_permission bool default false not null,
  direction text,
  reward_risk float8,
  last_price float8,
  open_interest float8,
  funding_rate float8,
  data_integrity_score int4,
  error text,
  payload jsonb not null,
  created_at timestamptz default now() not null,
  primary key (run_id, symbol)
);
create table public.alpha_hunter_signals (
  signal_id text not null,
  run_id text not null,
  symbol text not null,
  detected_at_utc timestamptz not null,
  state text,
  direction text,
  trade_permission bool default false not null,
  huge_rr_score float8,
  confidence_estimate_pct float8,
  reward_risk float8,
  entry_price float8,
  stop_loss float8,
  take_profit float8,
  reference_price float8 not null,
  payload jsonb not null,
  created_at timestamptz default now() not null,
  primary key (signal_id)
);
create table public.alpha_hunter_signal_features (
  signal_id text not null,
  run_id text not null,
  symbol text not null,
  captured_at_utc timestamptz not null,
  state text,
  direction text,
  trade_permission bool default false not null,
  trend_15m text,
  trend_1h text,
  trend_4h text,
  btc_regime text,
  sector text,
  session text,
  weekday int2,
  hour_utc int2,
  huge_rr_score float8,
  confidence_estimate_pct float8,
  reward_risk float8,
  volume_ratio float8,
  volume_expansion bool,
  volatility_pct float8,
  compression_score float8,
  funding_rate float8,
  open_interest float8,
  open_interest_change_pct float8,
  relative_strength_btc float8,
  rsi_15m float8,
  rsi_1h float8,
  rsi_4h float8,
  distance_to_support_pct float8,
  distance_to_resistance_pct float8,
  ema_alignment_15m text,
  ema_alignment_1h text,
  ema_alignment_4h text,
  liquidity_state text,
  features jsonb default '{}'::jsonb not null,
  source_payload jsonb default '{}'::jsonb not null,
  created_at timestamptz default now() not null,
  primary key (signal_id)
);
create table public.alpha_hunter_readiness_observations_v01 (
  run_id text not null,
  symbol text not null,
  observed_at_utc timestamptz not null,
  state text,
  direction text,
  trade_permission bool default false not null,
  v7_trade_ready bool default false not null,
  reference_price float8,
  entry_price float8,
  stop_loss float8,
  take_profit float8,
  reward_risk float8,
  lifecycle_id text,
  t1_id text,
  lifecycle_stage text,
  archetype text,
  capital_risk_status text,
  created_at timestamptz default clock_timestamp() not null,
  primary key (run_id, symbol)
);
alter table public.alpha_hunter_symbol_snapshots add foreign key (run_id) references public.alpha_hunter_snapshots(run_id) on delete cascade;
create table public.qa_atomic_trigger_events (event_id bigserial primary key, source_table text not null, run_id text not null);
create or replace function public.qa_track_atomic_side_effects()
returns trigger language plpgsql as $qa$
begin
  insert into public.qa_atomic_trigger_events(source_table,run_id)
  values (tg_table_name,new.run_id);
  if tg_table_name='alpha_hunter_symbol_snapshots' then
    if current_setting('qa.fail_symbol',true)='on' and new.symbol='ETHUSDT' then
      raise exception 'INJECTED_SYMBOL_TRIGGER_TIMEOUT';
    end if;
  end if;
  if tg_table_name='alpha_hunter_signal_features' and
    current_setting('qa.fail_feature',true)='on' then
    raise exception 'INJECTED_FEATURE_TRIGGER_FAILURE';
  end if;
  if tg_table_name='alpha_hunter_signal_features' and tg_when='BEFORE' then
    -- Model the real feature enrichment trigger: mutate the inserted payload.
    new.source_payload := coalesce(new.source_payload, '{}'::jsonb)
      || pg_catalog.jsonb_build_object(
        'timeframes', pg_catalog.jsonb_build_object('15m','QA_CONTEXT'),
        '_geometry_context_version','geometry-context-v0.1',
        '_geometry_context_source','CANONICAL_SYMBOL_SNAPSHOT_EXACT_RUN_SYMBOL'
      );
  end if;
  return new;
end;
$qa$;
create trigger qa_atomic_parent_after after insert or update on public.alpha_hunter_snapshots
for each row execute function public.qa_track_atomic_side_effects();
create trigger qa_atomic_symbol_after after insert or update on public.alpha_hunter_symbol_snapshots
for each row execute function public.qa_track_atomic_side_effects();
create trigger qa_atomic_signal_after after insert or update on public.alpha_hunter_signals
for each row execute function public.qa_track_atomic_side_effects();
-- Production has a BEFORE INSERT feature enrichment trigger. Cover replay semantics.
create trigger qa_atomic_feature_before before insert on public.alpha_hunter_signal_features
for each row execute function public.qa_track_atomic_side_effects();
create trigger qa_atomic_feature_after after insert or update on public.alpha_hunter_signal_features
for each row execute function public.qa_track_atomic_side_effects();
create trigger qa_atomic_readiness_after after insert or update on public.alpha_hunter_readiness_observations_v01
for each row execute function public.qa_track_atomic_side_effects();
