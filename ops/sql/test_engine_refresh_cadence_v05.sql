-- Release 2.6 authoritative test-engine refresh cadence.
-- Keep the current 25-minute freshness gate; refresh direct-gates v0.4 every 20 minutes.

select cron.alter_job(
  job_id := (
    select jobid
    from cron.job
    where jobname='alpha-hunter-test-engine-db-refresh-v02'
  ),
  schedule := '5,25,45 * * * *',
  command := 'select private.alpha_hunter_refresh_test_engine_v04();',
  active := true
);
