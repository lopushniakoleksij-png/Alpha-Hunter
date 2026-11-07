-- ISOLATED PG17 TEST FIXTURE ONLY — never execute on production.
-- Deliberately constructs three histories with zero upstream scan errors:
-- complete parent+children, parent-only, and last-stage readiness missing.
create table public.alpha_hunter_snapshots (
  run_id text primary key, collected_at_utc timestamptz not null,
  symbol_count integer not null, error_count integer not null,
  payload jsonb not null
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
  ('QA_COMPLETE','2026-11-07T12:02:00Z',1,0,'{"_storage_contract":"snapshot-parent-v0.2","validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON"}}'::jsonb),
  ('QA_READY_MISSING','2026-11-07T12:01:00Z',1,0,'{"legacy":true}'::jsonb),
  ('QA_PARENT_ONLY','2026-11-07T12:00:00Z',1,0,'{"_storage_contract":"snapshot-parent-v0.2","validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON"}}'::jsonb);
insert into public.alpha_hunter_symbol_snapshots values
  ('QA_COMPLETE','BTCUSDT'),('QA_READY_MISSING','ETHUSDT');
insert into public.alpha_hunter_signals values
  ('QA_COMPLETE','BTCUSDT','QA_SIGNAL_COMPLETE'),
  ('QA_READY_MISSING','ETHUSDT','QA_SIGNAL_READY_MISSING');
insert into public.alpha_hunter_signal_features values
  ('QA_COMPLETE','BTCUSDT','QA_SIGNAL_COMPLETE'),
  ('QA_READY_MISSING','ETHUSDT','QA_SIGNAL_READY_MISSING');
insert into public.alpha_hunter_readiness_observations_v01 values
  ('QA_COMPLETE','BTCUSDT');
