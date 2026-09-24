-- Alpha Hunter canonical universe scan persistence v0.2
--
-- The production scanner now observes the market multiple times per hour.
-- The legacy table constraint UNIQUE(symbol,hour_bucket_utc) silently discarded
-- :20/:40 universe rows even though each canonical scanner run was distinct.
--
-- Keep hour_bucket_utc for backwards-compatible hourly aggregation, but make
-- selection_run_id the scan identity so every canonical scan is preserved.

alter table public.alpha_hunter_universe_hourly
  drop constraint if exists
    alpha_hunter_universe_hourly_symbol_hour_bucket_utc_key;

create unique index if not exists
  uq_ah_universe_symbol_selection_run_v02
  on public.alpha_hunter_universe_hourly(symbol,selection_run_id)
  where selection_run_id is not null;

create index if not exists
  idx_ah_universe_observed_at_v02
  on public.alpha_hunter_universe_hourly(observed_at_utc desc);

comment on table public.alpha_hunter_universe_hourly is
  'Canonical full-universe ticker ledger. Name retained for compatibility; '
  'v0.2 permits multiple immutable scanner observations inside one UTC hour. '
  'hour_bucket_utc remains an aggregation field, while selection_run_id is the '
  'canonical scan identity. Never grants trade permission.';
