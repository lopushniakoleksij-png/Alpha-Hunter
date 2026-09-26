-- Alpha Hunter profitability activation cadence v0.2
--
-- Purpose:
--   Re-check the already sealed, latest-spec-only profitability activation gate
--   every 10 minutes instead of only once per hour.
--
-- This changes only operational check cadence. It does not alter eligibility,
-- scientific thresholds, strategy logic, trade permission, or order authority.

do $$
declare
  v_jobid bigint;
begin
  select jobid
    into strict v_jobid
  from cron.job
  where jobname='alpha-hunter-profitability-test-activation-v01-hourly';

  perform cron.alter_job(
    v_jobid,
    schedule := '7,17,27,37,47,57 * * * *'
  );
end
$$;
