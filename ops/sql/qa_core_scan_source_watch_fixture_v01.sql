-- Synthetic-only isolated PG17 read-only watch fixture.
-- NEVER run this fixture against production or any existing populated DB.
-- Independent axes: source custody and atomic core evidence completeness.
create table public.alpha_hunter_snapshots (
 run_id text primary key, collected_at_utc timestamptz not null,
 created_at timestamptz not null, symbol_count integer not null,
 error_count integer not null, payload jsonb not null
);
create table public.alpha_hunter_symbol_snapshots (
 run_id text not null, symbol text not null, primary key(run_id,symbol)
);
create table public.alpha_hunter_signals (
 run_id text not null, symbol text not null, signal_id text primary key
);
create table public.alpha_hunter_signal_features (
 run_id text not null, symbol text not null, signal_id text not null
);
create table public.alpha_hunter_readiness_observations_v01 (
 run_id text not null, symbol text not null, primary key(run_id,symbol)
);
insert into public.alpha_hunter_snapshots values
 ('QA_WATCH_MODERN_OK',now()-interval '10 minutes',now()-interval '10 minutes',1,0,
  '{"_storage_contract":"snapshot-parent-v0.2","validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON","git_commit":"synthetic"}}'::jsonb),
 ('QA_WATCH_LEGACY_COMPLETE',now()-interval '9 minutes',now()-interval '9 minutes',1,0,
  '{"symbols":[{"symbol":"SOLUSDT","intelligence":{"synthetic":true}}]}'::jsonb),
 ('QA_WATCH_READINESS_MISSING',now()-interval '8 minutes',now()-interval '8 minutes',1,0,
  '{"_storage_contract":"snapshot-parent-v0.2","validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON"}}'::jsonb),
 ('QA_WATCH_SOURCE_MISSING',now()-interval '7 minutes',now()-interval '7 minutes',1,0,
  '{"_storage_contract":"snapshot-parent-v0.2","validation_identity":{"run_source":"RENDER_CRON"}}'::jsonb),
 ('QA_WATCH_PARENT_STALE',now()-interval '6 minutes',now()-interval '6 minutes',1,0,
  '{"_storage_contract":"snapshot-parent-v0.2","validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON"}}'::jsonb),
 ('QA_WATCH_PARENT_PUBLISHING',now()-interval '1 minutes',now()-interval '1 minutes',1,0,
  '{"_storage_contract":"snapshot-parent-v0.2","validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON"}}'::jsonb);
insert into public.alpha_hunter_symbol_snapshots values
 ('QA_WATCH_MODERN_OK','BTCUSDT'),('QA_WATCH_LEGACY_COMPLETE','SOLUSDT'),
 ('QA_WATCH_READINESS_MISSING','ETHUSDT'),('QA_WATCH_SOURCE_MISSING','LTCUSDT');
insert into public.alpha_hunter_signals values
 ('QA_WATCH_MODERN_OK','BTCUSDT','QA_SIG_MODERN'),
 ('QA_WATCH_LEGACY_COMPLETE','SOLUSDT','QA_SIG_LEGACY'),
 ('QA_WATCH_READINESS_MISSING','ETHUSDT','QA_SIG_NO_READY'),
 ('QA_WATCH_SOURCE_MISSING','LTCUSDT','QA_SIG_NO_RUNTIME');
insert into public.alpha_hunter_signal_features values
 ('QA_WATCH_MODERN_OK','BTCUSDT','QA_SIG_MODERN'),
 ('QA_WATCH_LEGACY_COMPLETE','SOLUSDT','QA_SIG_LEGACY'),
 ('QA_WATCH_READINESS_MISSING','ETHUSDT','QA_SIG_NO_READY'),
 ('QA_WATCH_SOURCE_MISSING','LTCUSDT','QA_SIG_NO_RUNTIME');
insert into public.alpha_hunter_readiness_observations_v01 values
 ('QA_WATCH_MODERN_OK','BTCUSDT'),('QA_WATCH_LEGACY_COMPLETE','SOLUSDT'),
 ('QA_WATCH_SOURCE_MISSING','LTCUSDT');
