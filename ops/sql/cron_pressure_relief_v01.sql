-- Alpha Hunter database cron pressure relief v0.1
--
-- Operational scheduling only. Lives under ops/sql and is intentionally
-- outside the sealed V14 scientific fingerprint.
--
-- Evidence before this change:
-- * the test-engine refresh and ANSWER_KEY both started at :10;
-- * multiple control-plane stages were only one minute apart;
-- * pg_cron reported job startup timeouts and Supabase control connections
--   timed out during the same window.
--
-- This migration changes schedules only. It does not change any stage command,
-- scientific threshold, candidate logic, trade permission, or order path.

do $outer$
declare
  r record;
begin
  -- The profitability test engine is a reporting/evaluation refresh. The
  -- forward evidence collectors continue independently. Once per hour is
  -- sufficient for the hourly profitability gate while removing six-way
  -- pressure from the :00/:10/:20/:30/:40/:50 cadence.
  for r in
    select jobid
    from cron.job
    where command ilike '%alpha_hunter_refresh_test_engine_v02%'
  loop
    perform cron.alter_job(
      r.jobid,
      schedule := '2 * * * *'
    );
  end loop;

  -- The current sealed spec is already activated; keep the activation checker
  -- available for future specs, but it no longer needs six checks per hour.
  for r in
    select jobid
    from cron.job
    where jobname='alpha-hunter-profitability-test-activation-v01-hourly'
  loop
    perform cron.alter_job(
      r.jobid,
      schedule := '6 * * * *'
    );
  end loop;

  -- Spread the existing control-plane commands across the hour. Only timing
  -- changes: each job keeps its existing command, database and username.
  for r in
    select
      jobid,
      jobname,
      case jobname
        when 'alpha-hunter-big-mover-shadow-hourly' then '10 * * * *'
        when 'alpha-hunter-big-mover-parent-direction-hourly' then '16 * * * *'
        when 'alpha-hunter-big-mover-money-entry-bridge-hourly' then '21 * * * *'
        when 'alpha-hunter-money-entry-stage-hourly' then '24 * * * *'
        when 'alpha-hunter-big-mover-money-scorecard-hourly' then '29 * * * *'
        when 'alpha-hunter-execution-cost-evidence-hourly' then '33 * * * *'
        when 'alpha-hunter-portfolio-risk-veto-hourly' then '39 * * * *'
        when 'alpha-hunter-control-plane-finalize-hourly' then '43 * * * *'
      end as new_schedule
    from cron.job
    where jobname in (
      'alpha-hunter-big-mover-shadow-hourly',
      'alpha-hunter-big-mover-parent-direction-hourly',
      'alpha-hunter-big-mover-money-entry-bridge-hourly',
      'alpha-hunter-money-entry-stage-hourly',
      'alpha-hunter-big-mover-money-scorecard-hourly',
      'alpha-hunter-execution-cost-evidence-hourly',
      'alpha-hunter-portfolio-risk-veto-hourly',
      'alpha-hunter-control-plane-finalize-hourly'
    )
  loop
    perform cron.alter_job(
      r.jobid,
      schedule := r.new_schedule
    );
  end loop;
end;
$outer$;
