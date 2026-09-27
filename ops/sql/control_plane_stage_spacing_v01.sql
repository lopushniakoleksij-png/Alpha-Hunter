-- Alpha Hunter control-plane stage spacing v0.1
--
-- Production orchestration repair only. Lives under ops/sql and is outside
-- the sealed V14 scientific fingerprint.
--
-- Root cause:
-- ANSWER_KEY can run for ~118s and PARENT_DIRECTION ~40s. The old minute-by-
-- minute schedule (:10/:11/:12/...) allowed MONEY_ENTRY_BRIDGE to start while
-- PARENT_DIRECTION was still running, so the fail-closed predecessor gate
-- correctly skipped all downstream stages.
--
-- This migration preserves every existing stage command and predecessor gate.
-- It changes only pg_cron timing to provide observed-runtime margin.

do $outer$
declare
  r record;
begin
  for r in
    select jobid
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
    perform cron.unschedule(r.jobid);
  end loop;

  perform cron.schedule(
    'alpha-hunter-big-mover-shadow-hourly',
    '10 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('ANSWER_KEY',clock_timestamp());$cmd$
  );

  perform cron.schedule(
    'alpha-hunter-big-mover-parent-direction-hourly',
    '13 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('PARENT_DIRECTION',clock_timestamp());$cmd$
  );

  perform cron.schedule(
    'alpha-hunter-big-mover-money-entry-bridge-hourly',
    '14 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('MONEY_ENTRY_BRIDGE',clock_timestamp());$cmd$
  );

  perform cron.schedule(
    'alpha-hunter-money-entry-stage-hourly',
    '15 * * * *',
    $cmd$select private.alpha_hunter_run_money_entry_stage_with_geometry(clock_timestamp());$cmd$
  );

  perform cron.schedule(
    'alpha-hunter-big-mover-money-scorecard-hourly',
    '16 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('MONEY_SCORECARD',clock_timestamp());$cmd$
  );

  perform cron.schedule(
    'alpha-hunter-execution-cost-evidence-hourly',
    '17 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('COST_EVIDENCE',clock_timestamp());$cmd$
  );

  perform cron.schedule(
    'alpha-hunter-portfolio-risk-veto-hourly',
    '18 * * * *',
    $cmd$select private.alpha_hunter_run_controlled_stage('PORTFOLIO_RISK',clock_timestamp());$cmd$
  );

  perform cron.schedule(
    'alpha-hunter-control-plane-finalize-hourly',
    '20 * * * *',
    $cmd$select private.alpha_hunter_finalize_control_plane_hour(clock_timestamp());$cmd$
  );
end;
$outer$;
