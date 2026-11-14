-- Ephemeral PostgreSQL 17 fixture. Never execute against production.
-- Real-time relative dates keep the 48h audit window valid on later CI runs.
CREATE TABLE public.alpha_hunter_snapshots (
 run_id text PRIMARY KEY,
 collected_at_utc timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 symbol_count integer NOT NULL,
 payload jsonb NOT NULL
);
CREATE TABLE public.alpha_hunter_readiness_observations_v01 (
 run_id text NOT NULL,
 symbol text NOT NULL,
 PRIMARY KEY (run_id, symbol)
);
INSERT INTO public.alpha_hunter_snapshots (run_id, collected_at_utc, symbol_count, payload)
VALUES
 ('QA_LEGACY_FULL', now()-interval '3 minutes', 1,
  '{"symbols":[{"symbol":"ETHUSDT","intelligence":{"sample":1},"execution_setup":{}}]}'::jsonb),
 ('QA_MODERN_COMPACT', now()-interval '2 minutes', 1,
  '{"_storage_contract":"snapshot-parent-v0.2","validation_identity":{"run_source":"RENDER_CRON","runtime_role":"RENDER_CRON"},"symbols":[{"symbol":"BTCUSDT","execution_setup":{},"state":"WATCH"}]}'::jsonb),
 ('QA_UNKNOWN_OTHER', now()-interval '1 minute', 1,
  '{"symbols":[{"symbol":"LTCUSDT","state":"WATCH"}]}'::jsonb);
INSERT INTO public.alpha_hunter_readiness_observations_v01 VALUES
 ('QA_MODERN_COMPACT', 'BTCUSDT');
