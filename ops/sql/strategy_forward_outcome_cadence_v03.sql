-- Alpha Hunter strategy forward-outcome cadence v0.3
--
-- Operational cadence only. The scientific collector function, horizon
-- definitions, candle rules, outcome classes, thresholds and permissions are
-- unchanged.
--
-- Evidence before this change:
--   recent optimized collector runtime: ~4.9-6.0 seconds
--   due 24H episodes: 45
--   due 12H episodes: 1009
--
-- Change:
--   every 6 hours -> every 3 hours at :53.
--
-- Safety:
--   keeps bounded collector (max 120 due episodes/run);
--   no trading or production authority;
--   no scanner/runtime Git change because this is DB-only ops deployment.

select cron.alter_job(
  job_id := (
    select jobid
    from cron.job
    where jobname='alpha-hunter-strategy-forward-outcome-v01-hourly'
  ),
  schedule := '53 */3 * * *',
  active := true
);
